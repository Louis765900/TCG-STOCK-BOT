"""Scraper pour Cultura."""
import logging
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)

class CulturaScraper(BaseScraper):
    def __init__(self, browser):
        super().__init__("Cultura", browser)
        self.url_recherche = SEARCH_QUERIES.get("Cultura", "https://www.cultura.com/recherche.html?q=cartes+pokemon")

    async def scraper_recherche(self) -> list[dict]:
        logger.info(f"[{self.enseigne}] Début du scraping...")
        from debug_utils import debug_dump
        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            # /!\ SÉLECTEURS À AJUSTER LORS DES TESTS /!\
            # Hypothèse de structure classique pour un site e-commerce
            articles = soup.select(".product-list-item, article.product-miniature")
            
            for article in articles:
                try:
                    # Titre
                    titre_el = article.select_one(".product-title a, h3 a")
                    titre = titre_el.text.strip() if titre_el else "Inconnu"
                    
                    # URL
                    url = titre_el["href"] if titre_el and "href" in titre_el.attrs else ""
                    if url and not url.startswith("http"):
                        url = "https://www.cultura.com" + url

                    # Prix
                    prix_el = article.select_one(".price, .product-price")
                    prix = prix_el.text.strip() if prix_el else "N/A"

                    # Image
                    img_el = article.select_one("img")
                    image_url = img_el["src"] if img_el and "src" in img_el.attrs else ""

                    # Stock
                    # Hypothèse: s'il y a un bouton "Ajouter au panier", c'est en stock
                    # Ou s'il y a un tag "Indisponible"
                    btn_panier = article.select_one("button.add-to-cart, a.add-to-cart")
                    indispo = article.select_one(".out-of-stock, .rupture")
                    
                    en_stock = False
                    if btn_panier and not indispo:
                        en_stock = True

                    if url:
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
                    logger.warning(f"[{self.enseigne}] Erreur parsing d'un article: {e}")

            if len(produits) == 0:
                await debug_dump(page, self.enseigne)

            logger.info(f"[{self.enseigne}] {len(produits)} produits trouvés.")
            return produits
