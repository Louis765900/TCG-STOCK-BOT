"""Statistiques de sante/latence par enseigne et commande /status."""
import os
import sys
import time
import asyncio
import tempfile
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import database
import discord_bot


async def _scenario():
    fd, chemin = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()
    assert "Pas encore" in await discord_bot.texte_status()

    now = time.time()
    for i, (statut, duree) in enumerate([("healthy", 1.0), ("healthy", 3.0),
                                         ("blocked", 9.0), ("healthy", 2.0)]):
        await database.enregistrer_cycle(now - 100 + i, i, "Auchan", statut, 5, 0, 0, 0, duree)
    # Ancien (hors fenetre 24 h) : ignore
    await database.enregistrer_cycle(now - 48 * 3600, 0, "Vieux", "healthy", 1, 0, 0, 0, 1.0)

    st = await database.stats_enseignes(24)
    assert set(st) == {"Auchan"}
    a = st["Auchan"]
    assert a["cycles"] == 4 and a["ok"] == 3 and a["taux_ok"] == 0.75
    assert a["duree_p95"] == 9.0 and a["dernier_statut"] == "healthy"

    txt = await discord_bot.texte_status()
    assert "Auchan" in txt and "75%" in txt and "p95" in txt

    await database.fermer()
    os.remove(chemin)


def test():
    asyncio.run(_scenario())


if __name__ == "__main__":
    test()
    print("OK")
