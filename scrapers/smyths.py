"""Scraper pour Smyths Toys."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class SmythsScraper(BaseScraper):
    # Attendre le chargement de la liste produits (SAP hybris / custom)
    wait_selector = ".product-item, .product-list-item, [class*=product-item]"

    def __init__(self, browser):
        super().__init__("Smyths", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "Smyths",
            "https://www.smythstoys.com/fr/fr-fr/recherche/?text=cartes+pokemon",
        )

    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Début du scraping...", self.enseigne)
        from debug_utils import debug_dump

        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            articles = soup.select(
                ".product-item, .product-list-item, [class*=product-item]"
            )

            for article in articles:
                try:
                    titre_el = article.select_one(
                        ".product-title, .name a, h3 a, h2 a, [class*=product-name]"
                    )
                    titre = titre_el.get_text(strip=True) if titre_el else "Inconnu"

                    link_el = article.select_one("a[href]")
                    url = link_el.get("href", "") if link_el else ""
                    if url and not url.startswith("http"):
                        url = "https://www.smythstoys.com" + url

                    if not url:
                        continue

                    prix_el = article.select_one(".price, .product-price, [class*=price]")
                    prix = prix_el.get_text(strip=True) if prix_el else "N/A"

                    img_el = article.select_one("img[src], img[data-src]")
                    image_url = ""
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or ""

                    indispo = article.select_one(
                        ".out-of-stock, [class*=out-of-stock], [class*=unavailable]"
                    )
                    btn_panier = article.select_one(
                        "button.add-to-cart, button[class*=add-to-cart], [class*=btn-basket]"
                    )
                    en_stock = bool(btn_panier and not indispo)

                    produits.append({
                        "url": url,
                        "titre": titre,
                        "prix": prix,
                        "image_url": image_url,
                        "en_stock": en_stock,
                        "country": "FR",
                        "direct_links": {"Smyths Toys": url},
                    })
                except Exception as e:
                    logger.warning("[%s] Erreur parsing article: %s", self.enseigne, e)

            if not produits:
                await debug_dump(page, self.enseigne)

            logger.info("[%s] %d produits trouvés.", self.enseigne, len(produits))
            return produits
