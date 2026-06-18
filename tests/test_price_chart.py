"""Tests du graphique de prix : un graphe doit sortir même avec 1 seul relevé."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from price_chart import generer_graphique_prix, _MATPLOTLIB_OK


def test():
    if not _MATPLOTLIB_OK:
        print("matplotlib absent — test graphique ignoré.")
        return
    now = time.time()

    # 0 relevé numérique -> None (rien à tracer)
    assert generer_graphique_prix([], "Produit") is None
    assert generer_graphique_prix([{"prix_value": None, "timestamp": now}], "Produit") is None

    # 1 seul relevé -> PNG quand même (ligne plate) : c'est le cœur du fix
    png1 = generer_graphique_prix([{"prix_value": 79.99, "timestamp": now}], "ETB Nuit Noire")
    assert isinstance(png1, bytes) and png1[:8] == b"\x89PNG\r\n\x1a\n"

    # Plusieurs relevés -> PNG
    hist = [{"prix_value": 26.96, "timestamp": now - 86400},
            {"prix_value": 21.95, "timestamp": now}]
    png2 = generer_graphique_prix(hist, "Nanoblock")
    assert isinstance(png2, bytes) and png2[:8] == b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    test()
    print("OK")
