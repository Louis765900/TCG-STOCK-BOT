import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import store_health
from store_health import StoreHealth


def test():
    faux_temps = [1000.0]
    original = store_health.time.time
    store_health.time.time = lambda: faux_temps[0]
    try:
        h = StoreHealth(seuil=3, pause_s=3600)
        assert h.enregistrer("S", "blocked") is False
        assert h.enregistrer("S", "timeout") is False
        assert h.en_veille("S") is False
        # 3e échec -> veille
        assert h.enregistrer("S", "blocked") is True
        assert h.en_veille("S") is True
        # Expiration
        faux_temps[0] += 3601
        assert h.en_veille("S") is False
        # 'empty'/'healthy' = succès -> reset
        h2 = StoreHealth(seuil=2, pause_s=10)
        h2.enregistrer("A", "blocked")
        assert h2.enregistrer("A", "empty") is False
        assert h2.enregistrer("A", "blocked") is False
        assert h2.en_veille("A") is False
    finally:
        store_health.time.time = original


if __name__ == "__main__":
    test()
    print("OK")
