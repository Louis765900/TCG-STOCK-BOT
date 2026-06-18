"""
Scraper pour E.Leclerc - via l'API JSON interne (pas de navigateur).

Le site e.leclerc est protege par DataDome cote HTML, mais expose une API de
recherche JSON ouverte (moteur "Pertimm") :
    https://www.e.leclerc/api/rest/live-api/product-search?text=<mot-cle>

On l'interroge directement : c'est rapide, fiable, et ca donne deja prix, stock,
vendeur, EAN et image. On n'utilise donc ni le navigateur ni parse_page HTML.
"""

import asyncio
import logging
import random
import re
from urllib.parse import quote_plus

import config
from scrapers.base_scraper import BaseScraper
from http_fetch import http_get_json

logger = logging.getLogger(__name__)

API_URL = "https://www.e.leclerc/api/rest/live-api/product-search?text={q}"


class LeclercScraper(BaseScraper):

    utilise_navigateur = False  # API JSON interne, aucun navigateur requis

    # Leclerc limite agressivement le débit (HTTP 429) si on enchaîne les requêtes
    # en rafale. On interroge donc ses mots-clés UN PAR UN, avec une petite pause
    # aléatoire entre chacun : un poil plus lent, mais bien plus fiable (fini les
    # 429). Le retry/backoff de http_fetch reste là pour les coups durs.
    CONCURRENCE_RECHERCHE = 1
    DELAI_ENTRE_REQUETES = (0.3, 0.7)

    def __init__(self, browser):
        super().__init__("Leclerc", browser)

    # parse_page est inutile ici (on passe par l'API JSON), mais la classe de base
    # l'exige. On la garde vide.
    def parse_page(self, soup) -> list[dict]:
        return []

    # ---------- Extraction d'un item JSON -> dict produit ----------
    @staticmethod
    def _chercher_attribut(groupes, code):
        """Cherche un attribut par code dans une liste de groupes/attributs."""
        for groupe in groupes or []:
            for attr in groupe.get("attributes", []):
                if attr.get("code") == code:
                    return attr.get("value")
        return None

    @staticmethod
    def _meilleure_offre(variant: dict):
        offres = variant.get("offers") or []
        if not offres:
            return None

        def prix(o):
            return o.get("basePrice", {}).get("price", {}).get("price", float("inf"))

        # On choisit l'offre EN STOCK la moins chere (le meilleur deal pour l'acheteur).
        # Sinon, faute de stock, la moins chere tout court.
        en_stock = [o for o in offres if (o.get("stock") or 0) > 0]
        return min(en_stock or offres, key=prix)

    def _produit_depuis_item(self, item: dict) -> dict | None:
        ean = str(item.get("id") or item.get("sku") or "")
        slug = item.get("slug") or ""
        titre = item.get("label") or ""
        if not (ean and slug and titre):
            return None

        url = f"https://www.e.leclerc/fp/{slug}-{ean}"
        variants = item.get("variants") or []
        variant = variants[0] if variants else {}

        # Prix + stock + vendeur depuis la meilleure offre
        prix, en_stock, stock_qte, vendeur = "N/A", False, None, ""
        offre = self._meilleure_offre(variant)
        if offre:
            cents = offre.get("basePrice", {}).get("price", {}).get("price")
            if isinstance(cents, (int, float)):
                prix = f"{cents / 100:.2f}"
            stock_qte = offre.get("stock")
            en_stock = bool(stock_qte and stock_qte > 0)
            vendeur = (offre.get("shop") or {}).get("label", "")

        # Image (image1 de preference)
        image_url = ""
        for attr in variant.get("attributes", []):
            if attr.get("code", "").startswith("image") and isinstance(attr.get("value"), dict):
                image_url = attr["value"].get("url", "")
                if image_url:
                    break

        # Marque
        marque_val = self._chercher_attribut(item.get("attributeGroups"), "marque")
        brand = marque_val.get("label", "") if isinstance(marque_val, dict) else (marque_val or "")

        return {
            "url": url,
            "titre": titre,
            "prix": prix,
            "image_url": image_url,
            "en_stock": en_stock,
            "stock_quantity": stock_qte,
            "ean": ean,
            "brand": brand,
            "seller": vendeur,
            "country": "FR",
            "direct_links": {"E.Leclerc": url},
        }

    # ---------- Recherche (decouverte) ----------
    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Recherche API %d mots-cles...", self.enseigne, len(config.SEARCH_KEYWORDS))
        sem = asyncio.Semaphore(self.CONCURRENCE_RECHERCHE)
        statuts: list[str] = []
        # Si Leclerc se met à throttler (429/503), on ARRÊTE le balayage : continuer
        # à le marteler ne ferait qu'aggraver le bannissement de l'IP (DataDome).
        # Le bot réessaiera au prochain cycle, et StoreHealth le met en veille 1h
        # après plusieurs échecs → l'IP récupère.
        etat = {"blocs": 0, "stop": False}

        async def chercher(mot: str) -> list[dict]:
            if etat["stop"]:
                return []
            url = API_URL.format(q=quote_plus(mot))
            async with sem:
                if etat["stop"]:
                    return []
                data, statut, blocage = await http_get_json(url, timeout_ms=config.REQUEST_TIMEOUT_MS)
                # Petite pause pour rester sous le radar du limiteur de débit.
                await asyncio.sleep(random.uniform(*self.DELAI_ENTRE_REQUETES))
            statuts.append(statut)
            if statut != "ok" or not isinstance(data, dict):
                if blocage:
                    logger.warning("[%s] '%s' bloque/echec (%s).", self.enseigne, mot, blocage)
                if statut == "blocked":
                    etat["blocs"] += 1
                    if etat["blocs"] >= 2 and not etat["stop"]:
                        etat["stop"] = True
                        logger.warning("[%s] Throttling detecte — arret du balayage "
                                       "(reprise au prochain cycle).", self.enseigne)
                return []
            produits = []
            for item in data.get("items", []):
                try:
                    p = self._produit_depuis_item(item)
                    if p:
                        produits.append(p)
                except Exception as e:
                    logger.debug("[%s] item ignore: %s", self.enseigne, e)
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

    # ---------- Verification d'une fiche connue (watchlist) ----------
    async def scraper_produit(self, url: str) -> dict:
        """Revérifie un produit connu en interrogeant l'API par son EAN."""
        m = re.search(r"-(\d{8,14})(?:\.html)?(?:[/?#]|$)", url)
        ean = m.group(1) if m else ""
        if not ean:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}

        data, statut, blocage = await http_get_json(
            API_URL.format(q=ean), timeout_ms=config.REQUEST_TIMEOUT_MS)
        if statut != "ok" or not isinstance(data, dict):
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}

        for item in data.get("items", []):
            if str(item.get("id") or item.get("sku")) == ean:
                p = self._produit_depuis_item(item)
                if p:
                    return {
                        "status": "ok",
                        "en_stock": p["en_stock"],
                        "prix": p["prix"],
                        "image_url": p["image_url"],
                        "ean": p["ean"],
                        "brand": p["brand"],
                        "seller": p["seller"],
                        "reference": p["ean"],
                        "stock_quantity": p["stock_quantity"],
                    }

        # Produit absent de l'API : on ne touche pas l'etat (evite une fausse rupture).
        return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}
