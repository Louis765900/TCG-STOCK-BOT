"""Construction de la table {nom d'enseigne: scraper} (partagee par le bot et l'audit)."""
import config
from scrapers.cultura import CulturaScraper
from scrapers.leclerc import LeclercScraper
from scrapers.kingjouet import KingJouetScraper
from scrapers.smyths import SmythsScraper
from scrapers.granderecre import GrandeRecreScraper
from scrapers.auchan import AuchanScraper
from scrapers.shopify import ShopifyScraper
from scrapers.woocommerce import WooCommerceScraper


def construire_tous(browser=None) -> dict:
    """Tous les scrapers connus (actifs ou non), sans navigateur par defaut."""
    scrapers = {
        "Cultura": CulturaScraper(browser),
        "Leclerc": LeclercScraper(browser),
        "KingJouet": KingJouetScraper(browser),
        "Smyths": SmythsScraper(browser),
        "GrandeRecre": GrandeRecreScraper(browser),
        "Auchan": AuchanScraper(browser),
    }
    for nom, domaine in config.SHOPIFY_SHOPS.items():
        scrapers[nom] = ShopifyScraper(nom, domaine, browser)
    for nom, domaine in config.WOO_SHOPS.items():
        scrapers[nom] = WooCommerceScraper(nom, domaine, browser)
    return scrapers
