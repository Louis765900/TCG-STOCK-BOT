"""
Scraper générique pour les boutiques **WooCommerce** (WordPress) via la
**Store API** publique (pas d'authentification, pas d'anti-bot sur l'API) :
  - recherche : /wp-json/wc/store/v1/products?search=<mot>&per_page=100
  - fiche     : /wp-json/wc/store/v1/products?slug=<slug>
  - lot       : /wp-json/wc/store/v1/products?slug=<s1>,<s2>,...   (plusieurs produits)

Une instance = une boutique (ex: Le Coin des Barons). Pour en ajouter une,
une ligne dans config.WOO_SHOPS suffit — pas de nouveau code.

Note : la recherche Store API fait un "ET" strict sur les mots ; une requête
multi-mots ("pokemon display") renvoie souvent 0. On interroge donc par TERME
D'UNIVERS large ("pokemon", "one piece") et le filtre local affine ensuite.

Lecture GROUPEE (`scraper_lot`) : les listes de recherche par univers (quelques requetes)
donnent stock et prix de presque toute la watchlist ; les produits qu'elles ne couvrent pas
sont demandes par lots de slugs, jamais un par un. Un slug absent d'une reponse reussie est
`not_found` (constat explicite), pas une erreur reseau.

Produits "variables" (plusieurs declinaisons) : la Store API ne donne pas le stock par
declinaison, seulement un agregat. Le stock n'etant pas determinable avec certitude, ils sont
ignores en decouverte et `inconnu` en suivi (jamais d'alerte sur un agregat ambigu).
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
_URL_LOT_MAX = 1500   # longueur maxi des slugs d'une requete groupee (URL < ~2000 car.)


def _slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0].split("#")[0]


class WooCommerceScraper(BaseScraper):

    utilise_navigateur = False  # Store API publique, aucun navigateur requis

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
        prix = self._prix(p.get("prices") or {})
        if prix != "N/A" and float(prix) <= 0:
            prix = "N/A"   # prix 0 = non renseigne, jamais un vrai prix
        # "En stock" seulement si le produit est reellement ACHETABLE : la Store API
        # annonce parfois is_in_stock=true pour un produit non achetable a 0 EUR
        # ("Lire la suite") -> faux restock si on ne regarde que is_in_stock.
        achetable = bool(p.get("is_purchasable", True)) and prix != "N/A"
        restant = p.get("low_stock_remaining")
        return {
            "url": url,
            "titre": nom,
            "prix": prix,
            "image_url": image,
            "en_stock": bool(p.get("is_in_stock")) and achetable,
            "stock_quantity": restant if isinstance(restant, int) and restant >= 0 else None,
            "variable": p.get("type") == "variable" or bool(p.get("variations")),
            "brand": "",  # Woo Store API n'expose pas de marque fiable
            "seller": self.enseigne,
            "country": "FR",
            "direct_links": {self.enseigne: url},
        }

    def _resultat(self, p: dict) -> dict:
        """Resultat de suivi (meme format que scraper_produit) pour un produit Store API."""
        prod = self._produit(p)
        if prod is None or prod["variable"]:
            return {"status": "inconnu", "en_stock": False, "prix": "N/A", "image_url": ""}
        return {
            "status": "ok",
            "en_stock": prod["en_stock"],
            "prix": prod["prix"],
            "image_url": prod["image_url"],
            "ean": "",
            "brand": "",
            "seller": self.enseigne,
            "reference": str(p.get("sku") or ""),
            "stock_quantity": prod["stock_quantity"],
        }

    # ---------- Listes par terme d'univers (partagees decouverte / lot) ----------
    async def _lister(self) -> tuple[list[dict], list[str]]:
        """Produits Store API (bruts) des listes par univers + statuts des requetes."""
        sem = asyncio.Semaphore(config.SEARCH_CONCURRENCY)
        statuts: list[str] = []

        async def une_page(mot: str, page: int):
            url = f"{self.api}?search={quote_plus(mot)}&per_page={_PAR_PAGE}&page={page}"
            async with sem:
                return await http_get_json(url, timeout_ms=config.REQUEST_TIMEOUT_MS)

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
                out.extend(i for i in data if isinstance(i, dict))
                if len(data) < _PAR_PAGE:
                    break  # dernière page
            return out

        lots = await asyncio.gather(*(chercher(m) for m in _REQUETES))
        return [i for lot in lots for i in lot], statuts

    # ---------- Recherche (découverte) ----------
    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Recherche WooCommerce (%d termes)...", self.enseigne, len(_REQUETES))
        items, statuts = await self._lister()
        produits, vus = [], set()
        for item in items:
            try:
                prod = self._produit(item)
            except Exception as e:
                logger.debug("[%s] item ignoré: %s", self.enseigne, e)
                continue
            if not prod or prod["variable"] or prod["url"] in vus:
                continue          # variable : stock par declinaison indeterminable
            vus.add(prod["url"])
            produits.append(prod)

        if "ok" in statuts:
            self._last_status = "ok"
        elif "blocked" in statuts:
            self._last_status = "blocked"
        else:
            self._last_status = "timeout"

        logger.info("[%s] %d produits uniques (statut: %s).",
                    self.enseigne, len(produits), self._last_status)
        return produits

    # ---------- Lecture GROUPEE de la watchlist ----------
    async def scraper_lot(self, urls: list[str]) -> dict:
        """Stock/prix de plusieurs produits suivis en quelques requetes (voir en-tete)."""
        items, statuts = await self._lister()
        if not items and statuts and all(s in ("blocked", "timeout") for s in statuts):
            etat = "blocked" if "blocked" in statuts else "timeout"
            return {u: {"status": etat, "en_stock": False, "prix": "N/A", "image_url": ""}
                    for u in urls}
        par_slug = {i.get("slug"): i for i in items if i.get("slug")}

        out: dict[str, dict] = {}
        manquants: dict[str, str] = {}
        for u in urls:
            p = par_slug.get(_slug(u))
            if p is not None:
                out[u] = self._resultat(p)
            else:
                manquants[u] = _slug(u)

        # Produits hors des listes : requetes groupees par slugs (jamais une par une).
        lots, courant, taille = [], [], 0
        for u, s in manquants.items():
            if courant and taille + len(s) + 1 > _URL_LOT_MAX:
                lots.append(courant)
                courant, taille = [], 0
            courant.append(u)
            taille += len(s) + 1
        if courant:
            lots.append(courant)

        for groupe in lots:
            slugs = [manquants[u] for u in groupe]
            data, statut, _ = await http_get_json(
                f"{self.api}?slug={quote_plus(','.join(slugs))}&per_page={_PAR_PAGE}",
                timeout_ms=config.REQUEST_TIMEOUT_MS)
            if statut != "ok" or not isinstance(data, list):
                for u in groupe:
                    out[u] = {"status": statut, "en_stock": False, "prix": "N/A",
                              "image_url": ""}
                continue
            trouves = {i.get("slug"): i for i in data if isinstance(i, dict)}
            for u in groupe:
                p = trouves.get(manquants[u])
                out[u] = self._resultat(p) if p is not None else {
                    "status": "not_found", "en_stock": False, "prix": "N/A", "image_url": ""}
            await asyncio.sleep(0.2)
        return out

    # ---------- Vérification d'une fiche connue (par slug) ----------
    async def scraper_produit(self, url: str) -> dict:
        slug = _slug(url)
        if not slug:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}

        data, statut, _ = await http_get_json(
            f"{self.api}?slug={quote_plus(slug)}", timeout_ms=config.REQUEST_TIMEOUT_MS)
        if statut != "ok" or not isinstance(data, list) or not data:
            # statut != ok OU produit introuvable : on ne touche pas l'état.
            return {"status": statut if statut != "ok" else "not_found",
                    "en_stock": False, "prix": "N/A", "image_url": ""}
        return self._resultat(data[0])
