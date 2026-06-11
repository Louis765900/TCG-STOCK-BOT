"""Scraper pour La Grande Récré."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class GrandeRecreScraper(BaseScraper):
    # Attendre le rendu JS des cartes produit
    wait_selector = ".c-product-tile, .product-tile, .product-miniature, [class*=product-tile]"

    def __init__(self, browser):
        super().__init__("GrandeRecre", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "GrandeRecre", "https://www.lagranderecre.fr/recherche?q=cartes+pokemon"
        )

    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Début du scraping...", self.enseigne)
        from debug_utils import debug_dump

        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            articles = soup.select(
                ".c-product-tile, .product-tile, .product-miniature, [class*=product-tile]"
            )

            for article in articles:
                try:
                    titre_el = article.select_one(
                        ".c-product-tile__title, .product-title, .product-name, h3 a, h2 a"
                    )
                    titre = titre_el.get_text(strip=True) if titre_el else "Inconnu"

                    link_el = article.select_one("a[href]")
                    url = link_el.get("href", "") if link_el else ""
                    if url and not url.startswith("http"):
                        url = "https://www.lagranderecre.fr" + url

                    if not url:
                        continue

                    prix_el = article.select_one(
                        ".c-price__amount, .price, .product-price, [class*=price]"
                    )
                    prix = prix_el.get_text(strip=True) if prix_el else "N/A"

                    img_el = article.select_one("img[src], img[data-src]")
                    image_url = ""
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or ""

                    indispo = article.select_one(
                        ".out-of-stock, .indisponible, [class*=unavailable], [class*=out-of-stock]"
                    )
                    btn_panier = article.select_one(
                        "button.add-to-cart, button[class*=add-to-cart], [class*=btn-cart]"
                    )
                    en_stock = bool(btn_panier and not indispo)

                    produits.append({
                        "url": url,
                        "titre": titre,
                        "prix": prix,
                        "image_url": image_url,
                        "en_stock": en_stock,
                        "country": "FR",
                        "direct_links": {"La Grande Récré": url},
                    })
                except Exception as e:
                    logger.warning("[%s] Erreur parsing article: %s", self.enseigne, e)

            if not produits:
                await debug_dump(page, self.enseigne)

            logger.info("[%s] %d produits trouvés.", self.enseigne, len(produits))
            return produits
