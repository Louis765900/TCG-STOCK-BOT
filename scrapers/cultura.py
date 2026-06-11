"""Scraper pour Cultura."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class CulturaScraper(BaseScraper):
    # Attendre la liste produits PrestaShop
    wait_selector = "#js-product-list .products, .product-miniature"

    def __init__(self, browser):
        super().__init__("Cultura", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "Cultura", "https://www.cultura.com/recherche.html?q=cartes+pokemon"
        )

    def parse_page(self, soup) -> list[dict]:
        produits = []
        articles = soup.select(".product-miniature, article.product-miniature")

        for article in articles:
            try:
                titre_el = article.select_one(
                    ".product-title a, h3 a, .product-description a"
                )
                titre = titre_el.get_text(strip=True) if titre_el else "Inconnu"

                url = titre_el.get("href", "") if titre_el else ""
                if url and not url.startswith("http"):
                    url = "https://www.cultura.com" + url

                if not url:
                    continue

                prix_el = article.select_one(
                    ".price, .product-price, span[itemprop='price']"
                )
                prix = prix_el.get_text(strip=True) if prix_el else "N/A"

                img_el = article.select_one("img[src], img[data-src]")
                image_url = ""
                if img_el:
                    image_url = img_el.get("src") or img_el.get("data-src") or ""

                indispo = article.select_one(
                    ".out-of-stock, .product-unavailable, [class*=out-of-stock]"
                )
                btn_panier = article.select_one(
                    "button.add-to-cart, .ajax_add_to_cart_button, [data-button-action='add-to-cart']"
                )
                en_stock = bool(btn_panier and not indispo)

                produits.append({
                    "url": url,
                    "titre": titre,
                    "prix": prix,
                    "image_url": image_url,
                    "en_stock": en_stock,
                    "country": "FR",
                    "direct_links": {"Cultura": url},
                })
            except Exception as e:
                logger.warning("[%s] Erreur parsing article: %s", self.enseigne, e)

        return produits
