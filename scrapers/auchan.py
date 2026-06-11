"""Scraper pour Auchan."""
import re
import logging
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)

class AuchanScraper(BaseScraper):
    def __init__(self, browser):
        super().__init__("Auchan", browser)
        self.url_recherche = SEARCH_QUERIES.get("Auchan", "https://www.auchan.fr/recherche?text=cartes+pokemon")

    async def scraper_recherche(self) -> list[dict]:
        logger.info(f"[{self.enseigne}] Début du scraping...")
        from debug_utils import debug_dump
        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            articles = soup.select("article.product-thumbnail")
            
            for article in articles:
                try:
                    titre_el = article.select_one("p.product-thumbnail__description")
                    titre = titre_el.text.strip() if titre_el else "Inconnu"
                    
                    link_el = article.select_one("a.product-thumbnail__details-wrapper")
                    url = link_el["href"] if link_el and "href" in link_el.attrs else ""
                    if url and not url.startswith("http"):
                        url = "https://www.auchan.fr" + url

                    prix_el = article.select_one("div.product-price")
                    if prix_el:
                        prix_texte = prix_el.text.strip()
                        # Nettoyage pour garder uniquement les chiffres et la virgule/point
                        prix = re.sub(r'[^\d,.]', '', prix_texte)
                    else:
                        prix = "N/A"
                    old_price_el = article.select_one("del.product-price")
                    old_price = old_price_el.text.strip() if old_price_el else ""
                    discount_el = article.select_one(".product-discount-old-price__sticker")
                    discount = discount_el.text.strip() if discount_el else ""

                    img_el = article.select_one("img")
                    image_url = ""
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or ""

                    availability_el = article.select_one('meta[itemprop="availability"]')
                    stock_el = article.select_one(".quantity-selector[data-stock]")
                    indispo = "outOfStock" in article.get("class", [])
                    stock_quantity = None

                    en_stock = False
                    if availability_el:
                        en_stock = "instock" in availability_el.get("content", "").lower()
                    elif stock_el:
                        try:
                            stock_quantity = int(stock_el.get("data-stock", "0"))
                            en_stock = stock_quantity > 0
                        except ValueError:
                            en_stock = False
                    en_stock = en_stock and not indispo
                    if stock_quantity is None and stock_el:
                        try:
                            stock_quantity = int(stock_el.get("data-stock", "0"))
                        except ValueError:
                            stock_quantity = None

                    reference = article.get("data-id", "")
                    offer_el = article.select_one("[data-offer-id]")
                    detailed_reference = offer_el.get("data-offer-id", "") if offer_el else reference

                    if url:
                        produits.append({
                            "url": url,
                            "titre": titre,
                            "prix": prix,
                            "old_price": old_price,
                            "discount": discount,
                            "image_url": image_url,
                            "en_stock": en_stock,
                            "stock_quantity": stock_quantity,
                            "reference": reference,
                            "detailed_reference": detailed_reference,
                            "country": "FR",
                            "direct_links": {"Auchan": url},
                        })
                except Exception as e:
                    logger.warning(f"[{self.enseigne}] Erreur parsing d'un article: {e}")

            if len(produits) == 0:
                await debug_dump(page, self.enseigne)

            logger.info(f"[{self.enseigne}] {len(produits)} produits trouvés.")
            return produits
