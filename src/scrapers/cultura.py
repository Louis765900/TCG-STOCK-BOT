"""Scraper pour Cultura.

Le site a change de plateforme : chaque carte produit porte ses donnees en attributs
`data-product-*` (nom, prix, EAN, stock). Plus de PrestaShop (`.product-miniature`) ni de
`recherche.html` (404).

IMPORTANT : le HTML brut de `/search/results?q=...` ne contient AUCUNE carte (resultats
charges cote client) et `/recherche?q=...` ne renvoie qu'une liste generique sans rapport
avec la requete. Il faut donc un navigateur qui execute le JavaScript, puis on lit les
cartes une fois rendues.
"""
import logging
from urllib.parse import urljoin

from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)

_BASE = "https://www.cultura.com"

# Valeur de `data-product-stock` signifiant "achetable maintenant en ligne".
# Les autres ("INDISPONIBLE EN LIGNE", "DISPONIBLE SOUS X JOURS" = reappro fournisseur,
# "DISPONIBLE A PARTIR DU", "available_preorder") ne sont PAS du stock immediat : on les
# traite en rupture pour ne jamais declencher une fausse alerte restock.
_STOCK_EN_LIGNE = "en stock en ligne"


class CulturaScraper(BaseScraper):
    wait_selector = '[data-cmp-is="product"]'
    search_selector_timeout = 20000
    # http_first=False / utilise_navigateur=True (valeurs par defaut) : rendu JS requis.

    def __init__(self, browser):
        super().__init__("Cultura", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "Cultura", _BASE + "/recherche?q=cartes+pokemon"
        )

    def parse_page(self, soup) -> list[dict]:
        produits = []
        for carte in soup.select('[data-cmp-is="product"]'):
            try:
                titre = (carte.get("data-product-name") or "").strip()
                lien = carte.select_one('a[href^="/p-"], a[href*="/p-"]')
                href = lien.get("href", "") if lien else ""
                if not (titre and href):
                    continue
                url = urljoin(_BASE, href).split("?")[0]

                prix = (carte.get("data-product-price") or "").strip()
                try:
                    prix = f"{float(prix):.2f}"
                except ValueError:
                    prix = "N/A"

                stock_txt = (carte.get("data-product-stock") or "").strip().lower()
                marketplace = carte.select_one(".one-card--product--mkp") is not None
                marque = carte.select_one(".one-product__desc__origin")

                img = carte.select_one("img[src]")
                image_url = img.get("src", "") if img else ""
                if "placeholder" in image_url:
                    image_url = ""

                ean = (carte.get("data-product-ean") or "").strip()
                produits.append({
                    "url": url,
                    "titre": titre,
                    "prix": prix,
                    "image_url": image_url,
                    "en_stock": stock_txt == _STOCK_EN_LIGNE,
                    "ean": ean,
                    "brand": marque.get_text(strip=True) if marque else "",
                    "reference": (carte.get("data-product-sku") or "").strip(),
                    "seller": "Vendeur partenaire (marketplace)" if marketplace else "Cultura",
                    "country": "FR",
                    "direct_links": {"Cultura": url},
                })
            except Exception as e:
                logger.warning("[%s] Erreur parsing carte: %s", self.enseigne, e)

        return produits
