"""
Scraper Carrefour (carrefour.fr) - listings publics + fiches produit JSON-LD.

Sources (testees le 17/10/2026, aucun contournement) :
  - La RECHERCHE (`/s?q=`) est derriere un challenge Cloudflare (HTTP 429, `cf-mitigated:
    challenge`) : elle n'est PAS utilisee.
  - Les LISTINGS de categorie (`/r/...`) et les FICHES (`/p/...`) repondent normalement en
    HTML serveur et ne sont pas interdits par robots.txt. Decouverte = listing "jeux
    classiques" filtre par licence (Pokemon / One Piece) ; lecture = JSON-LD de la fiche.

Fiabilite du stock : la fiche liste CHAQUE offre avec son vendeur et sa disponibilite.
  - `en_stock` = une offre de livraison de CARREFOUR lui-meme ("Carrefour" ou
    "Carrefour Livraison") est InStock. Un marchand tiers (marketplace) n'est jamais compte
    comme stock Carrefour, sauf CARREFOUR_INCLURE_MARKETPLACE=true.
  - "Carrefour Drive" (retrait magasin) ou `InStoreOnly` : depend du magasin => PAS du stock
    en ligne (signale dans `drive`, exploite plus tard par le chantier "stock magasin").
  - JSON-LD Product absent/illisible => statut "inconnu" : jamais presume en stock.
  - Aucune quantite n'est inventee (`stock_quantity` = None).
"""
import asyncio
import json
import logging
import random
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
from http_fetch import http_get
from filter_utils import est_tcg_valide_local
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_BASE = "https://www.carrefour.fr"
_LISTING = _BASE + "/r/jeux-jouets/jeux-societe-puzzle/jeux-classiques+licence,{licence}"
_LICENCES = ("pokemon", "one-piece")
_MAX_PAGES = 4          # 30 cartes par page ; le rayon Pokemon en compte ~85
_PAUSE_PAGES = (1.5, 3.0)

_OFFRES_LIVRAISON_DIRECTE = {"carrefour", "carrefour livraison"}
_IN_STOCK = "instock"


def _vendeur(offre: dict) -> str:
    v = offre.get("seller")
    if isinstance(v, dict):
        v = v.get("name")
    return (v or "").strip() if isinstance(v, str) else ""


def _dispo(offre: dict) -> str:
    return str(offre.get("availability") or "").rsplit("/", 1)[-1].strip().lower()


def _cle_prix(offre: dict) -> float:
    """Cle de tri par prix, tolerante (prix absent/illisible => en dernier)."""
    try:
        return float(offre.get("price"))
    except (TypeError, ValueError):
        return float("inf")


def _prix(valeur) -> str:
    try:
        p = float(valeur)
    except (TypeError, ValueError):
        return "N/A"
    return f"{p:.2f}" if p > 0 else "N/A"


def _produits_jsonld(html: str) -> list[dict]:
    """Tous les objets JSON-LD de type Product de la page (liste, @graph ou objet)."""
    out = []
    soup = BeautifulSoup(html, "html.parser")
    for balise in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(balise.string or "")
        except (ValueError, TypeError):
            continue
        pile = data if isinstance(data, list) else [data]
        while pile:
            d = pile.pop()
            if isinstance(d, list):
                pile.extend(d)
            elif isinstance(d, dict):
                if "@graph" in d:
                    pile.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    out.append(d)
    return out


def analyser_fiche(html: str, inclure_marketplace: bool = False) -> dict:
    """Lit une fiche Carrefour. Pur (sans reseau) => testable sur des charges figees.

    Retourne {"status": "ok", ...} avec `stock_etat` in {"en_stock", "rupture"}, ou
    {"status": "inconnu", "raison": ...} si la fiche ne permet pas de conclure.
    """
    produits = _produits_jsonld(html or "")
    if not produits:
        return {"status": "inconnu", "raison": "json-ld Product absent",
                "en_stock": False, "prix": "N/A", "image_url": ""}
    p = produits[0]

    offres_brut = p.get("offers")
    offres: list[dict] = []
    if isinstance(offres_brut, dict):
        offres = offres_brut.get("offers") if isinstance(offres_brut.get("offers"), list) \
            else [offres_brut]
    elif isinstance(offres_brut, list):
        offres = offres_brut
    offres = [o for o in offres if isinstance(o, dict)]

    directes = [o for o in offres if _vendeur(o).lower().startswith("carrefour")]
    livraison = [o for o in directes
                 if _vendeur(o).lower() in _OFFRES_LIVRAISON_DIRECTE and _dispo(o) == _IN_STOCK]
    drive = any((_vendeur(o).lower() not in _OFFRES_LIVRAISON_DIRECTE and _dispo(o) == _IN_STOCK)
                or _dispo(o) == "instoreonly" for o in directes)
    marketplace = [o for o in offres if o not in directes and _dispo(o) == _IN_STOCK]

    if livraison:
        choix = min(livraison, key=_cle_prix)
        en_stock, vendeur, prix = True, "Carrefour", _prix(choix.get("price"))
    elif inclure_marketplace and marketplace:
        choix = min(marketplace, key=_cle_prix)
        en_stock, vendeur, prix = True, _vendeur(choix) or "Marketplace", _prix(choix.get("price"))
    else:
        en_stock, vendeur = False, "Carrefour"
        # Prix indicatif seulement si Carrefour vend lui-meme ce produit (jamais celui d'un tiers).
        prix = _prix(directes[0].get("price")) if directes else "N/A"

    image = p.get("image")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    marque = p.get("brand")
    marque = marque.get("name", "") if isinstance(marque, dict) else (marque or "")
    ean = str(p.get("gtin13") or p.get("gtin") or "")

    return {
        "status": "ok",
        "stock_etat": "en_stock" if en_stock else "rupture",
        "en_stock": en_stock,
        "prix": prix,
        "image_url": image if isinstance(image, str) else "",
        "ean": ean,
        "brand": marque if isinstance(marque, str) else "",
        "seller": vendeur,
        "reference": ean,
        "stock_quantity": None,           # jamais invente
        "titre": (p.get("name") or "").strip(),
        "drive": drive,
        "offres_marketplace": len(marketplace),
        "nb_offres": len(offres),
    }


def analyser_listing(html: str) -> list[dict]:
    """Cartes d'une page de listing : titre, URL canonique, EAN. Pur, testable."""
    soup = BeautifulSoup(html or "", "html.parser")
    out, vus = [], set()
    for a in soup.select('a[data-testid="product-card-title"]'):
        href = a.get("href", "")
        if not href.startswith("/p/"):
            continue
        url = urljoin(_BASE, href).split("?")[0]
        if url in vus:
            continue
        vus.add(url)
        titre = " ".join(a.get_text(" ").split())
        article = a.find_parent("article")
        ean = (article.get("data-testid") if article else "") or ""
        out.append({"url": url, "titre": titre, "ean": ean})
    return out


class CarrefourScraper(BaseScraper):

    utilise_navigateur = False
    # Poli avec Cloudflare : peu de fiches en parallele (cf. main.cycle_watchlist).
    CONCURRENCE_WATCHLIST = 2

    def __init__(self, browser):
        super().__init__("Carrefour", browser)

    def parse_page(self, soup) -> list[dict]:   # exigee par la classe de base
        return []

    # ---------- Fiche produit (watchlist) ----------
    async def scraper_produit(self, url: str) -> dict:
        html, statut, blocage = await http_get(url, timeout_ms=config.REQUEST_TIMEOUT_MS)
        await asyncio.sleep(random.uniform(0.3, 0.8))
        if html is None:
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}
        res = analyser_fiche(html, inclure_marketplace=config.CARREFOUR_INCLURE_MARKETPLACE)
        if res["status"] != "ok":
            logger.warning("[Carrefour] fiche illisible (%s): %s", res.get("raison"), url)
        return res

    # ---------- Decouverte (listings par licence) ----------
    async def scraper_recherche(self) -> list[dict]:
        cartes: dict[str, dict] = {}
        statuts: list[str] = []
        for licence in _LICENCES:
            for page in range(1, _MAX_PAGES + 1):
                url = _LISTING.format(licence=licence) + (f"?page={page}" if page > 1 else "")
                html, statut, blocage = await http_get(url, timeout_ms=config.REQUEST_TIMEOUT_MS)
                statuts.append(statut)
                if html is None:
                    logger.warning("[Carrefour] listing %s p%d: %s (%s)",
                                   licence, page, statut, blocage)
                    break
                nouvelles = [c for c in analyser_listing(html) if c["url"] not in cartes]
                for c in nouvelles:
                    cartes[c["url"]] = c
                if not nouvelles:
                    break
                await asyncio.sleep(random.uniform(*_PAUSE_PAGES))

        if "ok" in statuts:
            self._last_status = "ok"
        elif "blocked" in statuts:
            self._last_status = "blocked"
        else:
            self._last_status = "timeout"

        # Pre-filtre sur le titre (evite de lire les fiches de cahiers, peluches, jeux...),
        # puis LECTURE DE LA FICHE : le listing n'indique pas le stock, on ne le presume pas.
        candidats = [c for c in cartes.values() if est_tcg_valide_local(c["titre"])]
        sem = asyncio.Semaphore(self.CONCURRENCE_WATCHLIST)

        async def verifier(c):
            async with sem:
                return c, await self.scraper_produit(c["url"])

        produits = []
        for c, fiche in await asyncio.gather(*(verifier(c) for c in candidats)):
            if fiche.get("status") != "ok":
                logger.info("[Carrefour] %s ignoré (fiche: %s)", c["titre"], fiche.get("status"))
                continue
            if not est_tcg_valide_local(c["titre"], fiche.get("brand", "")):
                continue
            produits.append({
                "url": c["url"],
                "titre": fiche.get("titre") or c["titre"],
                "prix": fiche["prix"],
                "image_url": fiche["image_url"],
                "en_stock": fiche["en_stock"],
                "ean": fiche["ean"],
                "brand": fiche["brand"],
                "seller": fiche["seller"],
                "reference": fiche["reference"],
                "stock_quantity": None,
                "country": "FR",
                "direct_links": {"Carrefour": c["url"]},
            })
        logger.info("[Carrefour] %d cartes listées, %d candidats JCC, %d vérifiés (statut: %s).",
                    len(cartes), len(candidats), len(produits), self._last_status)
        return produits
