"""Scraper pour King Jouet."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class KingJouetScraper(BaseScraper):
    # Attendre le chargement de la grille produits
    wait_selector = ".product-block, .product-item, [class*=product-block]"

    def __init__(self, browser):
        super().__init__("KingJouet", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "KingJouet", "https://www.king-jouet.com/recherche.htm?mot=cartes+pokemon"
        )

    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Début du scraping...", self.enseigne)
        from debug_utils import debug_dump

        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            articles = soup.select(".product-block, .product-item, [class*=product-block]")

            for article in articles:
                try:
                    titre_el = article.select_one(
                        ".title a, .product-title a, .product-name a, h3 a, h2 a"
                    )
                    titre = titre_el.get_text(strip=True) if titre_el else "Inconnu"

                    url = titre_el.get("href", "") if titre_el else ""
                    if url and not url.startswith("http"):
                        url = "https://www.king-jouet.com" + url

                    if not url:
                        continue

                    prix_el = article.select_one(".price, .prix, [class*=price]")
                    prix = prix_el.get_text(strip=True) if prix_el else "N/A"

                    img_el = article.select_one("img[data-src], img[src]")
                    image_url = ""
                    if img_el:
                        image_url = img_el.get("data-src") or img_el.get("src") or ""

                    indispo = article.select_one(
                        ".rupture, .out-of-stock, [class*=rupture], [class*=out-of-stock]"
                    )
                    btn_panier = article.select_one(
                        ".add-to-cart, button.ajouter, button[class*=add-to-cart]"
                    )
                    en_stock = bool(btn_panier and not indispo)

                    produits.append({
                        "url": url,
                        "titre": titre,
                        "prix": prix,
                        "image_url": image_url,
                        "en_stock": en_stock,
                        "country": "FR",
                        "direct_links": {"King Jouet": url},
                    })
                except Exception as e:
                    logger.warning("[%s] Erreur parsing article: %s", self.enseigne, e)

            if not produits:
                await debug_dump(page, self.enseigne)

            logger.info("[%s] %d produits trouvés.", self.enseigne, len(produits))
            return produits
