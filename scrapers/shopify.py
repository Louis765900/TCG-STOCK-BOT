"""
Scraper générique pour les boutiques **Shopify** via leur API JSON publique.

Beaucoup de boutiques TCG spécialisées tournent sur Shopify, qui expose sans
anti-bot :
  - recherche : /search/suggest.json?q=<mot>&resources[type]=product
  - fiche     : /products/<handle>.js  (prix en CENTIMES, dispo par variante)

Une instance = une boutique (ex: LudiJeux, RelicTCG). Pour en ajouter une, il
suffit d'une ligne dans config.SHOPIFY_SHOPS — pas de nouveau code.
"""

import asyncio
import logging
from urllib.parse import quote_plus

import config
from scrapers.base_scraper import BaseScraper
from http_fetch import http_get_json

logger = logging.getLogger(__name__)

_SUGGEST = ("{base}/search/suggest.json?q={q}"
            "&resources[type]=product&resources[limit]=10")


class ShopifyScraper(BaseScraper):

    def __init__(self, enseigne: str, domaine: str, browser):
        super().__init__(enseigne, browser)
        self.domaine = domaine
        self.base = f"https://www.{domaine}"

    # parse_page est exigée par la classe de base mais inutile (on passe par l'API).
    def parse_page(self, soup) -> list[dict]:
        return []

    @staticmethod
    def _https(image: str) -> str:
        """Les images Shopify sont en '//cdn.shopify.com/...' -> on préfixe https:."""
        if isinstance(image, str) and image.startswith("//"):
            return "https:" + image
        return image or ""

    # ---------- Recherche (découverte) : /search/suggest.json ----------
    def _produit_depuis_suggest(self, p: dict) -> dict | None:
        handle = p.get("handle")
        titre = p.get("title")
        if not (handle and titre):
            return None
        url = f"{self.base}/products/{handle}"
        prix = "N/A"
        try:
            prix = f"{float(p.get('price')):.2f}"  # suggest.json -> euros (chaîne)
        except (TypeError, ValueError):
            pass
        return {
            "url": url,
            "titre": titre,
            "prix": prix,
            "image_url": self._https(p.get("featured_image") or p.get("image") or ""),
            "en_stock": bool(p.get("available")),
            "brand": p.get("vendor", ""),
            "seller": self.enseigne,
            "country": "FR",
            "direct_links": {self.enseigne: url},
        }

    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Recherche Shopify %d mots-clés...",
                    self.enseigne, len(config.SEARCH_KEYWORDS))
        sem = asyncio.Semaphore(config.SEARCH_CONCURRENCY)
        statuts: list[str] = []

        async def chercher(mot: str) -> list[dict]:
            url = _SUGGEST.format(base=self.base, q=quote_plus(mot))
            async with sem:
                data, statut, blocage = await http_get_json(
                    url, timeout_ms=config.REQUEST_TIMEOUT_MS)
            statuts.append(statut)
            if statut != "ok" or not isinstance(data, dict):
                if blocage:
                    logger.warning("[%s] '%s' bloqué/échec (%s).", self.enseigne, mot, blocage)
                return []
            items = (data.get("resources", {}).get("results", {}).get("products", []))
            produits = []
            for p in items:
                try:
                    prod = self._produit_depuis_suggest(p)
                    if prod:
                        produits.append(prod)
                except Exception as e:
                    logger.debug("[%s] item ignoré: %s", self.enseigne, e)
            return produits

        resultats = await asyncio.gather(*(chercher(m) for m in config.SEARCH_KEYWORDS))
        produits, vus = [], set()
        for lot in resultats:
            for p in lot:
                if p["url"] not in vus:
                    vus.add(p["url"])
                    produits.append(p)

        if "ok" in statuts:
            self._last_status = "ok"
        elif "blocked" in statuts:
            self._last_status = "blocked"
        else:
            self._last_status = "timeout"

        logger.info("[%s] %d produits uniques (statut: %s).",
                    self.enseigne, len(produits), self._last_status)
        return produits

    # ---------- Vérification d'une fiche connue : /products/<handle>.js ----------
    async def scraper_produit(self, url: str) -> dict:
        if "/products/" not in url:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}
        handle = url.rstrip("/").split("/products/")[-1].split("?")[0]
        if not handle:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}

        data, statut, blocage = await http_get_json(
            f"{self.base}/products/{handle}.js", timeout_ms=config.REQUEST_TIMEOUT_MS)
        if statut != "ok" or not isinstance(data, dict):
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}

        variants = data.get("variants") or []
        dispo = [v for v in variants if v.get("available")]
        en_stock = bool(data.get("available")) or bool(dispo)

        # Prix en CENTIMES côté .js : on prend la variante dispo la moins chère.
        cible = (min(dispo, key=lambda v: v.get("price") or float("inf"))
                 if dispo else (variants[0] if variants else {}))
        cents = cible.get("price", data.get("price"))
        prix = f"{cents / 100:.2f}" if isinstance(cents, (int, float)) else "N/A"

        images = data.get("images") or []
        image = images[0] if images else (data.get("featured_image") or "")

        return {
            "status": "ok",
            "en_stock": en_stock,
            "prix": prix,
            "image_url": self._https(image),
            "ean": "",
            "brand": data.get("vendor", ""),
            "seller": self.enseigne,
            "reference": str(data.get("id", "")),
            "stock_quantity": None,
        }
