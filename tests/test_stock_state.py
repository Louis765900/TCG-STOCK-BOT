import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

from stock_state import evaluer_transition, doit_alerter, RESTOCK, RUPTURE, STABLE


def test():
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
