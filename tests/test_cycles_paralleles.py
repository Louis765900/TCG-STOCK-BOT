"""Les enseignes sont traitees en parallele : duree du cycle = la plus lente."""
import os
import sys
import time
import asyncio
import tempfile
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config
import database
import main

_TITRE = "Pokémon EV05 : Coffret Dresseur d'Elite"
_DELAI = 0.3


class FauxScraper:
    def __init__(self):
        self._last_status = "ok"

    async def scraper_produit(self, url):
        await asyncio.sleep(_DELAI)
        return {"status": "ok", "en_stock": False, "prix": "10", "image_url": "",
                "brand": "Pokémon"}

    async def scraper_recherche(self):
        await asyncio.sleep(_DELAI)
        return []


async def _scenario():
    config.ENABLE_PRICE_CHART = False
    fd, chemin = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()
    enseignes = ["A", "B", "C", "D"]
    for e in enseignes:
        await database.ajouter_produit(f"https://{e}/p", _TITRE, e, False, prix="10")
    scrapers = {e: FauxScraper() for e in enseignes}

    t0 = time.perf_counter()
    rapport = await main.cycle_watchlist(scrapers, 1)
    duree = time.perf_counter() - t0
    assert len(rapport.stores) == 4
    assert duree < _DELAI * 2.5, f"watchlist sequentielle ? {duree:.2f}s"
    assert 0 < rapport.duree_s < _DELAI * 2.5

    t0 = time.perf_counter()
    rapport = await main.cycle_recherche(scrapers, 2)
    duree = time.perf_counter() - t0
    assert len(rapport.stores) == 4
    assert duree < _DELAI * 2.5, f"recherche sequentielle ? {duree:.2f}s"

    await database.fermer()
    os.remove(chemin)


def test():
    asyncio.run(_scenario())


if __name__ == "__main__":
    test()
    print("OK")
