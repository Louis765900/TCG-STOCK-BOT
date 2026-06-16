"""Scraper pour Auchan."""
import logging
from scrapers.base_scraper import BaseScraper
from config import SEARCH_QUERIES

logger = logging.getLogger(__name__)


class AuchanScraper(BaseScraper):
    # Auchan sert ses pages sans protection : HTTP simple d'abord (navigateur en secours).
    http_first = True

    def __init__(self, browser):
        super().__init__("Auchan", browser)
        self.url_recherche = SEARCH_QUERIES.get(
            "Auchan", "https://www.auchan.fr/recherche?text=cartes+pokemon"
        )

    def parse_page(self, soup) -> list[dict]:
        produits = []
        articles = soup.select("article.product-thumbnail")

        for article in articles:
            try:
                # URL
                link_el = article.select_one("a.product-thumbnail__details-wrapper")
                href = link_el.get("href", "") if link_el else ""
                if not href:
                    continue
                url = "https://www.auchan.fr" + href if not href.startswith("http") else href

                # Titre — brand et nom sont dans le même <p>, séparateur espace
                titre_el = article.select_one("p.product-thumbnail__description")
                titre = titre_el.get_text(separator=" ", strip=True) if titre_el else "Inconnu"

                # Image via meta schema.org
                img_meta = article.select_one("meta[itemprop='image']")
                image_url = img_meta.get("content", "") if img_meta else ""

                # Prix via meta schema.org (content en float string, ex: "20.83")
                prix_meta = article.select_one("meta[itemprop='price']")
                prix = f"{prix_meta.get('content', 'N/A')}€" if prix_meta else "N/A"

                # Ancien prix (barré)
                old_price_el = article.select_one("del.product-price--old")
                old_price = old_price_el.get_text(strip=True) if old_price_el else ""

                # Réduction
                discount_el = article.select_one(".product-discount-old-price__sticker")
                discount = discount_el.get_text(strip=True) if discount_el else ""

                # Stock — source 1 : classe outOfStock sur l'article
                out_of_stock_class = "outOfStock" in article.get("class", [])

                # Stock — source 2 : meta schema.org availability
                avail_meta = article.select_one("meta[itemprop='availability']")
                avail_content = avail_meta.get("content", "").lower() if avail_meta else ""

                # Stock — source 3 : data-stock (prend le max si plusieurs offres)
                stock_quantity = None
                stock_els = article.select("[data-stock]")
                if stock_els:
                    vals = []
                    for s in stock_els:
                        try:
                            vals.append(int(s.get("data-stock", "0")))
                        except ValueError:
                            pass
                    if vals:
                        stock_quantity = max(vals)

                if out_of_stock_class:
                    en_stock = False
                elif avail_content:
                    en_stock = "instock" in avail_content
                elif stock_quantity is not None:
                    en_stock = stock_quantity > 0
                else:
                    en_stock = True

                # Références
                reference = article.get("data-id", "")
                footer_el = article.select_one("footer[data-offer-id]")
                detailed_reference = footer_el.get("data-offer-id", reference) if footer_el else reference

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
                logger.warning("[%s] Erreur parsing d'un article: %s", self.enseigne, e)

        return produits
