"""Scraper pour E.Leclerc."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class LeclercScraper(BaseScraper):
    # Attendre le rendu Angular des cartes produit avant de capturer le HTML
    wait_selector = "app-product-card, li.product-container"

    def __init__(self, browser):
        super().__init__("Leclerc", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "Leclerc", "https://www.e.leclerc/recherche?q=cartes+pokemon"
        )

    async def scraper_recherche(self) -> list[dict]:
        logger.info("[%s] Début du scraping...", self.enseigne)
        from debug_utils import debug_dump

        async with self.get_page_soup(self.url_recherche) as (page, soup):
            if not soup:
                return []

            produits = []
            articles = soup.select("app-product-card, li.product-container")

            for article in articles:
                try:
                    titre_el = article.select_one("p.product-label")
                    titre = titre_el.get_text(strip=True) if titre_el else "Inconnu"

                    link_el = article.select_one("a.product-card-link, a[href*='/produit']")
                    url = link_el.get("href", "") if link_el else ""
                    if url and not url.startswith("http"):
                        url = "https://www.e.leclerc" + url

                    if not url:
                        continue

                    unit_el = article.select_one("div.price-unit, [class*=price-unit]")
                    cents_el = article.select_one("span.price-cents, [class*=price-cents]")
                    if unit_el and cents_el:
                        prix = f"{unit_el.get_text(strip=True)},{cents_el.get_text(strip=True)}€"
                    elif unit_el:
                        prix = unit_el.get_text(strip=True) + "€"
                    else:
                        prix = "N/A"

                    img_el = article.select_one("img[src], img[data-src]")
                    image_url = ""
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or ""

                    indispo = article.select_one(
                        ".out-of-stock, .indisponible, [class*=unavailable]"
                    )
                    btn_panier = article.select_one(
                        "button.add-to-cart, .btn-ajouter, [class*=add-to-cart]"
                    )
                    en_stock = bool(btn_panier and not indispo)

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
                    logger.warning("[%s] Erreur parsing article: %s", self.enseigne, e)

            if not produits:
                await debug_dump(page, self.enseigne)

            logger.info("[%s] %d produits trouvés.", self.enseigne, len(produits))
            return produits
