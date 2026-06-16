"""
Scraper générique pour les boutiques **WooCommerce** (WordPress) via la
**Store API** publique (pas d'authentification, pas d'anti-bot sur l'API) :
  - recherche : /wp-json/wc/store/v1/products?search=<mot>&per_page=100
  - fiche     : /wp-json/wc/store/v1/products?slug=<slug>

Une instance = une boutique (ex: Le Coin des Barons). Pour en ajouter une,
une ligne dans config.WOO_SHOPS suffit — pas de nouveau code.

Note : la recherche Store API fait un "ET" strict sur les mots ; une requête
multi-mots ("pokemon display") renvoie souvent 0. On interroge donc par TERME
D'UNIVERS large ("pokemon", "one piece") et le filtre local affine ensuite.
"""

import asyncio
import html
import logging
from urllib.parse import quote_plus

import config
from scrapers.base_scraper import BaseScraper
from http_fetch import http_get_json
from filter_utils import MOTS_UNIVERS

logger = logging.getLogger(__name__)

# Termes de recherche larges (l'API fait un ET strict -> pas de multi-mots).
_REQUETES = ["pokemon", "one piece"] if not MOTS_UNIVERS else MOTS_UNIVERS
_PAR_PAGE = 100
_MAX_PAGES = 3  # borne : jusqu'à 300 produits par terme


class WooCommerceScraper(BaseScraper):

    def __init__(self, enseigne: str, domaine: str, browser):
        super().__init__(enseigne, browser)
        self.domaine = domaine
        self.base = f"https://www.{domaine}"
        self.api = f"{self.base}/wp-json/wc/store/v1/products"

    def parse_page(self, soup) -> list[dict]:  # inutile (API JSON)
        return []

    @staticmethod
    def _prix(prices: dict) -> str:
        """prices.price est en unités mineures (centimes) -> euros."""
        try:
            brut = float(prices.get("price"))
            unit = int(prices.get("currency_minor_unit", 2))
            return f"{brut / (10 ** unit):.2f}"
        except (TypeError, ValueError, AttributeError):
            return "N/A"

    def _produit(self, p: dict) -> dict | None:
        nom = html.unescape(p.get("name") or "").strip()
        url = p.get("permalink") or ""
        if not (nom and url):
            return None
        images = p.get("images") or []
        image = images[0].get("src", "") if images else ""
        return {
            "url": url,
            "titre": nom,
            "prix": self._prix(p.get("prices") or {}),
            "image_url": image,
            "en_stock": bool(p.get("is_in_stock")),
            "brand": "",  # Woo Store API n'expose pas de marque fiable
            "seller": self.enseigne,
            "country": "FR",
            "direct_links": {self.enseigne: url},
        }

    # ---------- Recherche (découverte) ----------
    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Recherche WooCommerce (%d termes)...", self.enseigne, len(_REQUETES))
        sem = asyncio.Semaphore(config.SEARCH_CONCURRENCY)
        statuts: list[str] = []

        async def une_page(mot: str, page: int):
            url = f"{self.api}?search={quote_plus(mot)}&per_page={_PAR_PAGE}&page={page}"
            async with sem:
                data, statut, blocage = await http_get_json(url, timeout_ms=config.REQUEST_TIMEOUT_MS)
            return data, statut, blocage

        async def chercher(mot: str) -> list[dict]:
            out = []
            for page in range(1, _MAX_PAGES + 1):
                data, statut, blocage = await une_page(mot, page)
                statuts.append(statut)
                if statut != "ok" or not isinstance(data, list):
                    if blocage:
                        logger.warning("[%s] '%s' p%d bloqué/échec (%s).",
                                       self.enseigne, mot, page, blocage)
                    break
                for item in data:
                    try:
                        prod = self._produit(item)
                        if prod:
                            out.append(prod)
                    except Exception as e:
                        logger.debug("[%s] item ignoré: %s", self.enseigne, e)
                if len(data) < _PAR_PAGE:
                    break  # dernière page
            return out

        resultats = await asyncio.gather(*(chercher(m) for m in _REQUETES))
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

    # ---------- Vérification d'une fiche connue (par slug) ----------
    async def scraper_produit(self, url: str) -> dict:
        slug = url.rstrip("/").split("/")[-1].split("?")[0]
        if not slug:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}

        data, statut, _ = await http_get_json(
            f"{self.api}?slug={quote_plus(slug)}", timeout_ms=config.REQUEST_TIMEOUT_MS)
        if statut != "ok" or not isinstance(data, list) or not data:
            # statut != ok OU produit introuvable : on ne touche pas l'état.
            return {"status": statut if statut != "ok" else "timeout",
                    "en_stock": False, "prix": "N/A", "image_url": ""}

        prod = self._produit(data[0]) or {}
        return {
            "status": "ok",
            "en_stock": prod.get("en_stock", False),
            "prix": prod.get("prix", "N/A"),
            "image_url": prod.get("image_url", ""),
            "ean": "",
            "brand": "",
            "seller": self.enseigne,
            "reference": str(data[0].get("sku", "")),
            "stock_quantity": None,
        }
