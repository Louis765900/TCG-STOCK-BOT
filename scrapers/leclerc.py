"""Scraper pour Leclerc."""
import logging
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)

class LeclercScraper(BaseScraper):
    def __init__(self, browser):
        super().__init__("Leclerc", browser)
        self.url_recherche = SEARCH_QUERIES.get("Leclerc", "https://www.e.leclerc/recherche?q=cartes+pokemon")

    async def scraper_recherche(self) -> list[dict]:
        logger.info(f"[{self.enseigne}] Début du scraping...")
        from debug_utils import debug_dump
        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            # Sélecteurs Leclerc
            articles = soup.select("li.product-container, app-product-card")
            
            for article in articles:
                try:
                    titre_el = article.select_one("p.product-label")
                    titre = titre_el.text.strip() if titre_el else "Inconnu"
                    
                    link_el = article.select_one("a.product-card-link")
                    url = link_el["href"] if link_el and "href" in link_el.attrs else ""
                    if url and not url.startswith("http"):
                        url = "https://www.e.leclerc" + url

                    unit_el = article.select_one("div.price-unit")
                    cents_el = article.select_one("span.price-cents")
                    
                    if unit_el and cents_el:
                        prix = f"{unit_el.text.strip()},{cents_el.text.strip()}"
                    elif unit_el:
                        prix = unit_el.text.strip()
                    else:
                        prix = "N/A"

                    img_el = article.select_one("img")
                    image_url = img_el["src"] if img_el and "src" in img_el.attrs else ""

                    btn_panier = article.select_one("button.add-to-cart, .btn-ajouter")
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
                            "direct_links": {"E.Leclerc": url},
                        })
                except Exception as e:
                    logger.warning(f"[{self.enseigne}] Erreur parsing d'un article: {e}")

            if len(produits) == 0:
                await debug_dump(page, self.enseigne)

            logger.info(f"[{self.enseigne}] {len(produits)} produits trouvés.")
            return produits
