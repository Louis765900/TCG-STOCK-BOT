"""Scraper pour La Grande Récré."""
import logging
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)

class GrandeRecreScraper(BaseScraper):
    def __init__(self, browser):
        super().__init__("GrandeRecre", browser)
        self.url_recherche = SEARCH_QUERIES.get("GrandeRecre", "https://www.lagranderecre.fr/recherche?q=cartes+pokemon")

    async def scraper_recherche(self) -> list[dict]:
        logger.info(f"[{self.enseigne}] Début du scraping...")
        from debug_utils import debug_dump
        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            # /!\ SÉLECTEURS À AJUSTER LORS DES TESTS /!\
            articles = soup.select(".product-miniature, .item")
            
            for article in articles:
                try:
                    titre_el = article.select_one(".product-title a, h3 a")
                    titre = titre_el.text.strip() if titre_el else "Inconnu"
                    
                    url = titre_el["href"] if titre_el and "href" in titre_el.attrs else ""
                    if url and not url.startswith("http"):
                        url = "https://www.lagranderecre.fr" + url

                    prix_el = article.select_one(".price, .product-price")
                    prix = prix_el.text.strip() if prix_el else "N/A"

                    img_el = article.select_one("img")
                    image_url = img_el["src"] if img_el and "src" in img_el.attrs else ""

                    btn_panier = article.select_one("button.add-to-cart")
                    indispo = article.select_one(".out-of-stock, .indisponible")
                    
                    en_stock = bool(btn_panier and not indispo)

                    if url:
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
                    logger.warning(f"[{self.enseigne}] Erreur parsing d'un article: {e}")

            if len(produits) == 0:
                await debug_dump(page, self.enseigne)

            logger.info(f"[{self.enseigne}] {len(produits)} produits trouvés.")
            return produits
