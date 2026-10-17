"""
Scraper générique pour les boutiques **Shopify** via leur API JSON publique.

Beaucoup de boutiques TCG spécialisées tournent sur Shopify, qui expose sans anti-bot :
  - recherche   : /search/suggest.json?q=<mot>&resources[type]=product  (masque les ruptures)
  - collections : /collections.json  puis  /collections/<handle>/products.json
                  (catalogue d'une collection, ruptures incluses, 250 produits par requête)
  - fiche       : /products/<handle>.js  (prix en CENTIMES, dispo par variante)

Lecture GROUPEE (`scraper_lot`) : au lieu d'une requête par produit suivi, on lit une fois les
collections "scellé Pokémon / One Piece" de la boutique (quelques requêtes) et on en déduit
stock et prix de tous les produits suivis. Un produit absent de ces collections est relu
individuellement (`.js`) : jamais de stock deviné.

Variantes : le stock d'un produit n'est PAS "une variante quelconque est disponible". Les
variantes d'ETAT ou de LANGUE non voulues (« Endommagé », « Occasion », « Anglais »…, voir
`SHOPIFY_VARIANTES_EXCLUES`) sont ignorées : un produit dont seule la version abîmée est en
stock reste en rupture (sinon faux restock).

Une instance = une boutique (ex: LudiJeux, RelicTCG). Pour en ajouter une, il
suffit d'une ligne dans config.SHOPIFY_SHOPS — pas de nouveau code.
"""

import asyncio
import logging
import re
import time
from urllib.parse import quote_plus

import config
from scrapers.base_scraper import BaseScraper
from http_fetch import http_get_json
from filter_utils import est_tcg_valide_local, _normaliser

logger = logging.getLogger(__name__)

_SUGGEST = ("{base}/search/suggest.json?q={q}"
            "&resources[type]=product&resources[limit]=10")

# ---------------------------------------------------------------------------
# Selection des collections "scelle" d'une boutique (fonction pure, testable)
# ---------------------------------------------------------------------------
_UNIVERS = ("pokemon", "one piece", "onepiece")
# Mots ENTIERS (jamais de sous-chaine : "mug" ne doit pas exclure "Mugiwara").
_EXCLUSION = {"unite", "unites", "gradee", "gradees", "accessoire", "accessoires", "figurine",
              "figurines", "peluche", "peluches", "mug", "mugs", "funko", "puzzle", "puzzles",
              "sleeve", "sleeves", "tapis", "portefolio", "portefolios", "portfolio", "pokepla",
              "coussin", "coussins", "cadre", "cadres", "verre", "verres", "sac", "sacs",
              "japonais", "japan", "us", "usa", "coreen", "korean", "anglais", "english",
              "single", "singles", "soldes"}
_EXCLUSION_EXPRESSIONS = ("deck box", "deckbox")
_MAX_COLLECTIONS = 14
_PAGES_PAR_COLLECTION = 6      # 6 x 250 = 1500 produits maxi par collection
_COLLECTIONS_EN_PARALLELE = 3
_VERIF_DECOUVERTE_MAX = 150    # fiches lues au plus par cycle de decouverte (recherche)


def choisir_collections(collections: list[dict]) -> list[str]:
    """Handles des collections a lire pour couvrir le scelle Pokemon / One Piece."""
    choisies = []
    for c in collections:
        handle = c.get("handle") or ""
        texte = _normaliser(f"{c.get('title', '')} {handle.replace('-', ' ')}")
        mots = set(re.findall(r"[a-z0-9]+", texte))
        # `products_count` de collections.json est INEXACT (produits non publies inclus :
        # 469 annonces pour 70 reels) et la collection generique "Pokemon" contient souvent
        # des produits absents des collections specialisees : on ne s'en sert que pour
        # ecarter une collection vide, jamais pour la dimensionner.
        n = c.get("products_count")
        if not handle or (isinstance(n, int) and n <= 0):
            continue
        if not any(u in texte for u in _UNIVERS):
            continue
        if mots & _EXCLUSION or any(x in texte for x in _EXCLUSION_EXPRESSIONS):
            continue
        choisies.append(handle)
    return choisies[:_MAX_COLLECTIONS]


# ---------------------------------------------------------------------------
# Lecture des variantes (fonction pure, testable)
# ---------------------------------------------------------------------------
def _mots_exclus() -> tuple:
    return tuple(_normaliser(m) for m in config.SHOPIFY_VARIANTES_EXCLUES if m.strip())


def _prix_variante(v: dict, centimes: bool) -> float:
    try:
        p = float(v.get("price"))
    except (TypeError, ValueError):
        return float("inf")
    return p / 100 if centimes else p


def lire_variantes(variantes: list[dict], centimes: bool) -> dict:
    """Stock et prix d'un produit a partir de ses variantes.

    `centimes` : True pour `/products/<h>.js` (prix entiers en centimes), False pour
    `products.json` (chaines en euros). Le stock vaut True seulement si une variante
    NON exclue est disponible ; le prix est celui de la moins chere de ces variantes
    (disponibles, sinon toutes les variantes retenues). Sans variante : `inconnu`.
    """
    if not variantes:
        return {"inconnu": True, "en_stock": False, "prix": "N/A", "variantes": [], "exclues": 0}
    mots = _mots_exclus()
    infos = []
    for v in variantes:
        texte = _normaliser(" ".join(str(v.get(k) or "") for k in
                                     ("title", "option1", "option2", "option3")))
        infos.append({"titre": v.get("title") or "", "dispo": bool(v.get("available")),
                      "prix": _prix_variante(v, centimes),
                      "exclue": any(m in texte for m in mots), "barcode": str(v.get("barcode") or "")})
    retenues = [i for i in infos if not i["exclue"]]
    dispo = [i for i in retenues if i["dispo"]]
    pool = dispo or retenues
    meilleur = min((i["prix"] for i in pool), default=float("inf"))
    prix = f"{meilleur:.2f}" if 0 < meilleur < float("inf") else "N/A"
    ean = next((i["barcode"] for i in pool if i["barcode"].isdigit()
                and len(i["barcode"]) in (8, 12, 13, 14)), "")
    return {"inconnu": False, "en_stock": bool(dispo), "prix": prix, "ean": ean,
            "variantes": [{k: i[k] for k in ("titre", "dispo", "exclue")} for i in infos],
            "exclues": sum(1 for i in infos if i["exclue"])}


def _handle(url: str) -> str:
    if "/products/" not in url:
        return ""
    return url.rstrip("/").split("/products/")[-1].split("?")[0].split("#")[0]


class ShopifyScraper(BaseScraper):

    utilise_navigateur = False  # API JSON publique, aucun navigateur requis
    mode_decouverte = "suggest"   # "collections" ou "suggest" (voir BaseScraper)

    def __init__(self, enseigne: str, domaine: str, browser, catalogue_complet: bool = False):
        super().__init__(enseigne, browser)
        self.domaine = domaine
        self.base = f"https://www.{domaine}"
        # Decouverte par COLLECTIONS (ruptures incluses) au lieu de la recherche predictive,
        # qui masque les produits indisponibles : sans cela, un produit epuise n'est jamais
        # connu du bot et son retour en stock n'est pas suivi finement.
        self.catalogue_complet = catalogue_complet
        self._collections: tuple[float, list[str]] | None = None   # (horodatage, handles)
        self._statut_snapshot = "ok"

    # parse_page est exigée par la classe de base mais inutile (on passe par l'API).
    def parse_page(self, soup) -> list[dict]:
        return []

    @staticmethod
    def _https(image) -> str:
        """
        Normalise une image Shopify en URL (chaîne).

        Selon l'endpoint, l'image peut être une chaîne OU un objet
        ({"url"/"src": ...}) — il faut donc toujours retomber sur une chaîne,
        sinon on insère un dict en base (→ 'type dict is not supported').
        """
        if isinstance(image, dict):
            image = image.get("url") or image.get("src") or ""
        if not isinstance(image, str):
            return ""
        if image.startswith("//"):
            return "https:" + image
        return image

    # ---------- Resultat commun (catalogue / .js) ----------
    def _resultat(self, p: dict, centimes: bool) -> dict:
        lecture = lire_variantes(p.get("variants") or [], centimes)
        if lecture["inconnu"]:
            return {"status": "inconnu", "en_stock": False, "prix": "N/A", "image_url": ""}
        images = p.get("images") or []
        image = images[0] if images else (p.get("featured_image") or "")
        return {
            "status": "ok",
            "en_stock": lecture["en_stock"],
            "prix": lecture["prix"],
            "image_url": self._https(image),
            "ean": lecture.get("ean", ""),
            "brand": p.get("vendor", ""),
            "seller": self.enseigne,
            "reference": str(p.get("id", "")),
            "stock_quantity": None,           # jamais invente
            "variantes": lecture["variantes"],
            "variantes_exclues": lecture["exclues"],
        }

    # ---------- Collections : selection + lecture (snapshot du catalogue scelle) ----------
    async def _collections_cibles(self) -> list[str]:
        manuelles = config.SHOPIFY_COLLECTIONS.get(self.enseigne)
        if manuelles:
            return manuelles
        if self._collections and time.time() - self._collections[0] < 6 * 3600:
            return self._collections[1]
        cols: list[dict] = []
        for page in (1, 2, 3):
            data, statut, _ = await http_get_json(
                f"{self.base}/collections.json?limit=250&page={page}",
                timeout_ms=config.REQUEST_TIMEOUT_MS)
            lot = data.get("collections") if isinstance(data, dict) else None
            if statut != "ok" or not isinstance(lot, list):
                self._statut_snapshot = statut
                break
            cols += lot
            if len(lot) < 250:
                break
        handles = choisir_collections(cols)
        if handles:
            self._collections = (time.time(), handles)
            logger.info("[%s] Collections suivies : %s", self.enseigne, ", ".join(handles))
        return handles

    async def _snapshot(self) -> dict | None:
        """{handle: produit JSON} des collections scelle ; None si indisponible."""
        handles = await self._collections_cibles()
        if not handles:
            return None
        produits: dict[str, dict] = {}
        etat = {"echecs": 0, "statut": "ok"}
        sem = asyncio.Semaphore(_COLLECTIONS_EN_PARALLELE)

        async def lire(h: str) -> list[dict]:
            out: list[dict] = []
            async with sem:
                for page in range(1, _PAGES_PAR_COLLECTION + 1):
                    data, statut, _ = await http_get_json(
                        f"{self.base}/collections/{h}/products.json?limit=250&page={page}",
                        timeout_ms=config.REQUEST_TIMEOUT_MS)
                    articles = data.get("products") if isinstance(data, dict) else None
                    if statut != "ok" or not isinstance(articles, list):
                        etat["echecs"] += 1
                        etat["statut"] = statut
                        break
                    out.extend(a for a in articles if isinstance(a, dict))
                    if len(articles) < 250:
                        break
            return out

        # Ordre des collections conserve (la 1re version d'un produit l'emporte).
        for articles in await asyncio.gather(*(lire(h) for h in handles)):
            for a in articles:
                if a.get("handle"):
                    produits.setdefault(a["handle"], a)
        self._statut_snapshot = etat["statut"] if (etat["echecs"] and not produits) else "ok"
        if not produits:
            return None
        return produits

    # ---------- Decouverte par collections ----------
    def _produit_depuis_catalogue(self, p: dict) -> dict | None:
        handle, titre = p.get("handle"), p.get("title")
        if not (handle and titre):
            return None
        r = self._resultat(p, centimes=False)
        if r["status"] != "ok":
            return None
        url = f"{self.base}/products/{handle}"
        return {
            "url": url, "titre": titre, "prix": r["prix"], "image_url": r["image_url"],
            "en_stock": r["en_stock"], "ean": r["ean"], "brand": r["brand"],
            "seller": self.enseigne, "country": "FR", "direct_links": {self.enseigne: url},
        }

    async def _recherche_catalogue(self) -> list[dict] | None:
        """Scelle de la boutique (ruptures comprises). None => repli sur la recherche."""
        snap = await self._snapshot()
        if snap is None:
            logger.info("[%s] Collections indisponibles (%s) -> recherche classique.",
                        self.enseigne, self._statut_snapshot)
            return None
        produits = []
        for a in snap.values():
            type_produit = (a.get("product_type") or "").lower()
            if any(m in type_produit for m in ("unité", "unite", "single")):
                continue                        # cartes a l'unite : pas du scelle
            try:
                prod = self._produit_depuis_catalogue(a)
                if prod and est_tcg_valide_local(prod["titre"], prod["brand"]):
                    produits.append(prod)
            except Exception as e:
                logger.debug("[%s] article ignoré: %s", self.enseigne, e)
        self._last_status = "ok"
        logger.info("[%s] Collections : %d produits JCC scellés.", self.enseigne, len(produits))
        return produits

    # ---------- Lecture GROUPEE de la watchlist ----------
    async def scraper_lot(self, urls: list[str]) -> dict:
        """Stock/prix de plusieurs produits suivis en quelques requetes.

        Retourne {url: resultat}. Un produit que les collections ne couvrent pas (ou dont
        la lecture est ambigue) recoit {"status": "a_verifier"} : le moteur le relit via
        `scraper_produit`. Si la boutique bloque, tous les produits recoivent ce statut
        d'erreur (inutile de multiplier des requetes vouees a l'echec).
        """
        snap = await self._snapshot()
        if snap is None:
            if self._statut_snapshot in ("blocked", "timeout"):
                return {u: {"status": self._statut_snapshot, "en_stock": False, "prix": "N/A",
                            "image_url": ""} for u in urls}
            return {}
        out = {}
        for u in urls:
            p = snap.get(_handle(u))
            if p is None:
                out[u] = {"status": "a_verifier"}
                continue
            r = self._resultat(p, centimes=False)
            # Un produit sans variante exploitable n'est pas tranche en lot.
            out[u] = r if r["status"] == "ok" else {"status": "a_verifier"}
        return out

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

    # ---------- Verification des produits decouverts par la recherche predictive ----------
    async def _verifier_decouverte(self, produits: list[dict]) -> list[dict]:
        """Rend la decouverte par recherche aussi fiable que le catalogue et la fiche.

        La recherche predictive ne donne qu'un `available` global (ses `variants` sont
        vides) : un produit annonce "disponible" peut ne l'etre que par une variante
        endommagee ou etrangere. Pour chaque produit JCC annonce disponible, on lit donc la
        fiche (`.js`) et on applique la MEME regle que partout (`lire_variantes`).
          - fiche illisible/bloquee => produit ECARTE ce cycle (jamais annonce sans preuve) ;
          - produit indisponible    => prix "N/A" (prix de la recherche non verifiable par
            variante ; le suivi le renseignera) ;
          - les produits hors JCC ne sont pas verifies (le moteur les ecarte de toute facon).
        """
        sem = asyncio.Semaphore(3)
        restantes = _VERIF_DECOUVERTE_MAX

        async def verifier(p: dict) -> dict | None:
            async with sem:
                res = await self.scraper_produit(p["url"])
            if res.get("status") != "ok":
                logger.info("[%s] %s écarté (fiche: %s) : disponibilité non vérifiable.",
                            self.enseigne, p["titre"], res.get("status"))
                return None
            return dict(p, en_stock=res["en_stock"], prix=res["prix"],
                        image_url=p.get("image_url") or res.get("image_url", ""),
                        ean=res.get("ean", ""))

        sortie, taches = [], []
        for p in produits:
            if not est_tcg_valide_local(p["titre"], p.get("brand", "")):
                sortie.append(p)
            elif not p["en_stock"]:
                sortie.append(dict(p, prix="N/A"))
            elif restantes > 0:
                restantes -= 1
                taches.append(verifier(p))
            else:
                logger.warning("[%s] %s écarté : plafond de vérifications atteint (%d).",
                               self.enseigne, p["titre"], _VERIF_DECOUVERTE_MAX)
        sortie.extend(p for p in await asyncio.gather(*taches) if p is not None)
        return sortie

    async def scraper_recherche(self) -> list[dict]:
        if self.catalogue_complet:
            produits = await self._recherche_catalogue()
            if produits is not None:
                self.mode_decouverte = "collections"
                return produits
        self.mode_decouverte = "suggest"
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

        produits = await self._verifier_decouverte(produits)
        logger.info("[%s] %d produits uniques (statut: %s).",
                    self.enseigne, len(produits), self._last_status)
        return produits

    # ---------- Vérification d'une fiche connue : /products/<handle>.js ----------
    async def scraper_produit(self, url: str) -> dict:
        handle = _handle(url)
        if not handle:
            return {"status": "timeout", "en_stock": False, "prix": "N/A", "image_url": ""}

        data, statut, blocage = await http_get_json(
            f"{self.base}/products/{handle}.js", timeout_ms=config.REQUEST_TIMEOUT_MS)
        if statut != "ok" or not isinstance(data, dict):
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}
        return self._resultat(data, centimes=True)
