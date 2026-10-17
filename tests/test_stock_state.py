import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

from stock_state import (evaluer_transition, doit_alerter, RESTOCK, RUPTURE, STABLE,
                         ConfirmationRupture, calculer_pause)


def test():
    c = ConfirmationRupture(2)
    assert not c.rupture_confirmee("u", False)      # 1re lecture indispo : on attend
    assert not c.rupture_confirmee("u", True)       # retour en stock : compteur remis a 0
    assert not c.rupture_confirmee("u", False)
    assert c.rupture_confirmee("u", False)          # 2 indispos consecutives : confirmee
    assert ConfirmationRupture(1).rupture_confirmee("x", False)

    assert calculer_pause(40, 100, 140, alea=0.5) == 80.0
    assert calculer_pause(500, 100, 140) == 5.0     # cycle trop long : plancher
    assert 100 - 40 <= calculer_pause(40, 100, 140, alea=0.0) <= 140 - 40
    assert evaluer_transition(False, True) == RESTOCK and doit_alerter(RESTOCK)
    assert evaluer_transition(True, False) == RUPTURE and not doit_alerter(RUPTURE)
    assert evaluer_transition(True, True) == STABLE
    assert evaluer_transition(False, False) == STABLE
    # Valeurs SQLite (0/1) tolérées
    assert evaluer_transition(0, 1) == RESTOCK
    assert evaluer_transition(1, 1) == STABLE


if __name__ == "__main__":
    test()
    print("OK")
