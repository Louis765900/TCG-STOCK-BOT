"""
stock_state.py - Regle de transition de stock (surveillance par difference d'etat).

Principe : on n'alerte QUE sur un changement reel d'etat, pas a chaque fois qu'un
produit est en stock. On compare l'etat memorise (base) a l'etat lu maintenant.

Regle d'or : ne JAMAIS appeler ce module avec une lecture ratee (blocage / timeout).
Un site bloque renvoie "indisponible" par defaut ; le prendre pour une rupture
declencherait ensuite un faux restock. L'appelant doit donc filtrer en amont
(statut == "ok") avant de demander la decision ici.
"""

from __future__ import annotations

# Actions possibles renvoyees par evaluer_transition.
RESTOCK = "restock"   # etait indisponible -> maintenant disponible  => ALERTE
RUPTURE = "rupture"   # etait disponible   -> maintenant indisponible => on note, pas d'alerte
STABLE = "stable"     # aucun changement                              => rien a faire


def evaluer_transition(ancien_en_stock: bool, nouveau_en_stock: bool) -> str:
    """
    Compare l'ancien et le nouvel etat de stock et renvoie l'action a faire.

    A n'appeler qu'avec une lecture FIABLE du stock (statut "ok").

    >>> evaluer_transition(False, True)
    'restock'
    >>> evaluer_transition(True, False)
    'rupture'
    >>> evaluer_transition(True, True)
    'stable'
    >>> evaluer_transition(False, False)
    'stable'
    """
    ancien = bool(ancien_en_stock)
    nouveau = bool(nouveau_en_stock)
    if nouveau and not ancien:
        return RESTOCK
    if ancien and not nouveau:
        return RUPTURE
    return STABLE


def doit_alerter(action: str) -> bool:
    """Seul un restock declenche une alerte Discord."""
    return action == RESTOCK
