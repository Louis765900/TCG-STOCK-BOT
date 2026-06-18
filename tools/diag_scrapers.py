"""Diagnostic live : interroge Leclerc + RelicTCG une fois et affiche le résultat."""
import os
import sys
import asyncio

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

from scrapers.leclerc import LeclercScraper
from scrapers.shopify import ShopifyScraper


async def main():
    scrapers = [
        LeclercScraper(browser=None),
        ShopifyScraper("RelicTCG", "relictcg.com", browser=None),
        ShopifyScraper("LudiJeux", "ludijeux.fr", browser=None),
    ]
    for s in scrapers:
        try:
            produits = await s.scraper_recherche()
            statut = getattr(s, "_last_status", "?")
            print(f"{s.enseigne:12} statut={statut:8} produits={len(produits)}")
            for p in produits[:3]:
                img = p.get("image_url")
                typ = type(img).__name__
                print(f"    - {p.get('titre','')[:55]:55} | img={typ} | {p.get('prix')}")
        except Exception as e:
            print(f"{s.enseigne:12} ERREUR: {e}")


if __name__ == "__main__":
    asyncio.run(main())
