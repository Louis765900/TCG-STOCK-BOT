"""Tests d'intégration de la logique de main : transitions, deals, pause, amorçage."""
import os
import sys
import asyncio
import tempfile
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import config
import database
import bot_state
import main


class Store:
    def __init__(self):
        self.restocks = 0
        self.ruptures = 0
        self.nouveautes = 0


_TITRE_VALIDE = "Pokémon EV05 : Coffret Dresseur d'Elite"


def _res(status="ok", en_stock=True, prix="33.95"):
    return {"status": status, "en_stock": en_stock, "prix": prix, "image_url": "",
            "brand": "Pokémon"}


def _item(url, prix, en_stock):
    return {"url": url, "titre": _TITRE_VALIDE, "en_stock": int(en_stock), "prix": prix,
            "image_url": ""}


async def _scenario():
    config.ENABLE_PRICE_CHART = False
    config.DEAL_DROP_PERCENT = 15
    bot_state.set_pause(False)
    alertes = []

    async def fake_alerte(prod, ens, t, chart_png=None):
        alertes.append(t)
    main.envoyer_alerte = fake_alerte

    fd, chemin = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()

    # --- Lecture bloquée NE crée PAS de fausse rupture ---
    await database.ajouter_produit("u1", "Coffret", "Auchan", True, prix="10")
    # (le cycle filtre déjà les statuts != ok ; ici on teste _traiter directement
    #  uniquement avec des lectures fiables)
    await main._traiter_resultat_watchlist("Auchan", _item("u1", "10", True),
                                           _res("ok", True, "10"), Store())
    assert alertes == []  # stable, pas d'alerte

    # --- Restock indispo -> stock ---
    await database.ajouter_produit("u2", "Coffret", "Auchan", False, prix="10")
    await main._traiter_resultat_watchlist("Auchan", _item("u2", "10", False),
                                           _res("ok", True, "10"), Store())
    assert "RESTOCK" in alertes

    # --- Deal : baisse >= 15% sur produit en stock ---
    alertes.clear()
    await database.ajouter_produit("u3", "Coffret", "Auchan", True, prix="40")
    await main._traiter_resultat_watchlist("Auchan", _item("u3", "40", True),
                                           _res("ok", True, "29.99"), Store())
    assert "DEAL" in alertes

    # --- Pause : aucune alerte ne part ---
    alertes.clear()
    bot_state.set_pause(True)
    await database.ajouter_produit("u4", "Coffret", "Auchan", False, prix="10")
    await main._traiter_resultat_watchlist("Auchan", _item("u4", "10", False),
                                           _res("ok", True, "10"), Store())
    assert alertes == []
    bot_state.set_pause(False)

    # --- Garde-fou : un produit hors-cible (jouet) est purgé, jamais d'alerte ---
    alertes.clear()
    await database.ajouter_produit("u5", "BANDAI Arène Pokémon et 2 spinners",
                                   "Auchan", False, prix="29.99")
    item_junk = {"url": "u5", "titre": "BANDAI Arène Pokémon et 2 spinners",
                 "en_stock": 0, "prix": "29.99", "image_url": ""}
    await main._traiter_resultat_watchlist("Auchan", item_junk,
                                           _res("ok", True, "29.99"), Store())
    assert alertes == []  # restock ignoré : ce n'est pas du JCC
    assert await database.recuperer_produit("u5") is None  # et il est purgé

    os.remove(chemin)


def test():
    asyncio.run(_scenario())


if __name__ == "__main__":
    test()
    print("OK")
