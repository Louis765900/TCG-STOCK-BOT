"""
structured_data.py - Extraction des donnees produit structurees (schema.org).

La plupart des sites e-commerce decrivent leurs produits de facon STANDARD via :
  - JSON-LD  : <script type="application/ld+json"> { "@type": "Product", ... }
  - Microdata : <div itemtype="https://schema.org/Product"> ... itemprop="..."

Lire ces donnees est bien plus robuste que des selecteurs CSS maison : le format
est commun a tous les sites et change rarement. Ce module fusionne les deux
sources et renvoie un dict normalise. JSON-LD est prioritaire (plus propre),
la microdata comble les trous.

Fonction principale :
    extraire_donnees_structurees(html) -> dict

Le dict ne contient que les cles reellement trouvees. Cles possibles :
    title, price, old_price, currency, in_stock (bool|None), stock_quantity,
    image_url, ean, sku, brand, seller, rating, rating_count
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger("structured_data")

# Valeurs schema.org indiquant qu'un produit est disponible / indisponible.
_DISPO_OUI = {"instock", "limitedavailability", "onlineonly", "instoreonly", "preorder"}
_DISPO_NON = {"outofstock", "soldout", "discontinued", "backorder"}


# =============================================================================
# Helpers generiques
# =============================================================================

def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(node: dict) -> set[str]:
    """Retourne l'ensemble des @type d'un noeud, en minuscules."""
    return {str(t).lower() for t in _as_list(node.get("@type"))}


def _texte(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value") or ""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _prix(value: Any) -> str:
    """Normalise un prix en chaine '24.90' (sans symbole)."""
    if value is None:
        return ""
    m = re.search(r"\d+(?:[.,]\d+)?", str(value))
    return m.group(0).replace(",", ".") if m else ""


def _disponibilite(value: Any) -> Optional[bool]:
    """Traduit un champ availability schema.org en booleen (ou None si inconnu)."""
    if not value:
        return None
    token = str(value).rsplit("/", 1)[-1].strip().lower()
    if token in _DISPO_OUI:
        return True
    if token in _DISPO_NON:
        return False
    return None


def _image(value: Any) -> str:
    """Extrait une URL d'image depuis string / liste / ImageObject."""
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            url = item.get("url") or item.get("contentUrl")
            if url:
                return str(url).strip()
    return ""


def _ean(node: dict) -> str:
    """Cherche un code-barres (GTIN/EAN) parmi les variantes schema.org."""
    for key in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin", "ean", "mpn"):
        val = node.get(key)
        if val:
            digits = re.sub(r"\D", "", str(val))
            if len(digits) in {8, 12, 13, 14}:
                return digits
    return ""


# =============================================================================
# JSON-LD
# =============================================================================

def _noeuds_json_ld(html: str) -> list[dict]:
    """Renvoie tous les noeuds JSON-LD (en deroulant @graph et les listes)."""
    soup = BeautifulSoup(html, "html.parser")
    noeuds: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        brut = script.string or script.get_text() or ""
        if not brut.strip():
            continue
        try:
            data = json.loads(brut)
        except (json.JSONDecodeError, ValueError):
            continue
        for bloc in _as_list(data):
            if not isinstance(bloc, dict):
                continue
            if "@graph" in bloc:
                noeuds.extend(n for n in _as_list(bloc["@graph"]) if isinstance(n, dict))
            else:
                noeuds.append(bloc)
    return noeuds


def _offre(node: dict) -> dict:
    """Extrait prix/dispo/vendeur depuis offers (Offer ou AggregateOffer)."""
    res: dict = {}
    offres = _as_list(node.get("offers"))
    if not offres:
        return res

    # On prend la 1re offre pour le detail ; AggregateOffer expose lowPrice.
    principale = offres[0]
    if not isinstance(principale, dict):
        return res

    if "lowprice" in {k.lower() for k in principale}:
        # AggregateOffer
        low = principale.get("lowPrice") or principale.get("lowprice")
        res["price"] = _prix(low)
    else:
        res["price"] = _prix(principale.get("price"))

    currency = principale.get("priceCurrency")
    if currency:
        res["currency"] = _texte(currency)

    dispo = _disponibilite(principale.get("availability"))
    if dispo is not None:
        res["in_stock"] = dispo

    seller = principale.get("seller")
    if seller:
        res["seller"] = _texte(seller)

    return {k: v for k, v in res.items() if v not in ("", None)}


def _depuis_json_ld(html: str) -> dict:
    for node in _noeuds_json_ld(html):
        if "product" not in _types(node):
            continue
        res: dict = {}
        if node.get("name"):
            res["title"] = _texte(node["name"])
        if node.get("brand"):
            res["brand"] = _texte(node["brand"])
        if node.get("sku"):
            res["sku"] = _texte(node["sku"])
        img = _image(node.get("image"))
        if img:
            res["image_url"] = img
        ean = _ean(node)
        if ean:
            res["ean"] = ean

        rating = node.get("aggregateRating")
        if isinstance(rating, dict):
            if rating.get("ratingValue"):
                res["rating"] = _texte(rating["ratingValue"])
            count = rating.get("reviewCount") or rating.get("ratingCount")
            if count:
                res["rating_count"] = _texte(count)

        res.update(_offre(node))
        if res:
            return res
    return {}


# =============================================================================
# Microdata (fallback / complement)
# =============================================================================

def _microdata_valeur(el) -> str:
    """Lit la valeur d'un element microdata (content, href/src, ou texte)."""
    if el is None:
        return ""
    if el.has_attr("content"):
        return el["content"].strip()
    if el.has_attr("href"):
        return el["href"].strip()
    if el.has_attr("src"):
        return el["src"].strip()
    return el.get_text(strip=True)


def _depuis_microdata(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    conteneur = soup.find(itemtype=re.compile(r"schema\.org/Product", re.I))
    if conteneur is None:
        return {}

    def prop(name: str):
        return conteneur.find(itemprop=re.compile(rf"^{name}$", re.I))

    res: dict = {}
    if (el := prop("name")):
        res["title"] = _texte(_microdata_valeur(el))
    if (el := prop("brand")):
        res["brand"] = _texte(_microdata_valeur(el))
    if (el := prop("sku")):
        res["sku"] = _texte(_microdata_valeur(el))
    if (el := prop("image")):
        res["image_url"] = _microdata_valeur(el)
    for key in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin", "ean", "mpn"):
        if (el := prop(key)):
            digits = re.sub(r"\D", "", _microdata_valeur(el))
            if len(digits) in {8, 12, 13, 14}:
                res["ean"] = digits
                break
    if (el := prop("price")):
        res["price"] = _prix(_microdata_valeur(el))
    if (el := prop("priceCurrency")):
        res["currency"] = _texte(_microdata_valeur(el))
    if (el := prop("availability")):
        dispo = _disponibilite(_microdata_valeur(el))
        if dispo is not None:
            res["in_stock"] = dispo
    if (el := prop("seller")):
        res["seller"] = _texte(_microdata_valeur(el))

    return {k: v for k, v in res.items() if v not in ("", None)}


# =============================================================================
# API publique
# =============================================================================

def extraire_donnees_structurees(html: Optional[str]) -> dict:
    """
    Fusionne JSON-LD (prioritaire) et microdata d'une page produit.
    Retourne un dict ne contenant que les champs trouves.
    """
    if not html:
        return {}
    try:
        json_ld = _depuis_json_ld(html)
        micro = _depuis_microdata(html)
    except Exception as e:  # robustesse : jamais planter le scraper
        logger.debug("Extraction structuree echouee: %s", e)
        return {}

    # JSON-LD prioritaire : on part de la microdata puis on ecrase avec JSON-LD.
    fusion = dict(micro)
    fusion.update(json_ld)
    return fusion
