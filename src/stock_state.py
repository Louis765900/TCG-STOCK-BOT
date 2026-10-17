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


class ConfirmationRupture:
    """Exige N lectures fiables consecutives "indisponible" avant d'acter une rupture.

    Pourquoi : une page qui rend brievement un faux "indisponible" (fiche tronquee,
    bouton charge en retard) enregistrerait une rupture, et la lecture suivante
    declencherait un FAUX restock. Tant que la rupture n'est pas confirmee, l'etat en
    base reste "en stock" : aucune transition, donc aucune fausse alerte.
    Etat en memoire uniquement (une relance repart de zero, sans consequence).
    """

    def __init__(self, seuil: int = 2):
        self.seuil = max(1, int(seuil))
        self._compteurs: dict[str, int] = {}

    def rupture_confirmee(self, cle: str, en_stock_lu: bool) -> bool:
        """A appeler pour un produit CONNU en stock. True => rupture a acter."""
        if en_stock_lu:
            self._compteurs.pop(cle, None)
            return False
        n = self._compteurs.get(cle, 0) + 1
        if n >= self.seuil:
            self._compteurs.pop(cle, None)
            return True
        self._compteurs[cle] = n
        return False

    def oublier(self, cle: str) -> None:
        self._compteurs.pop(cle, None)


def calculer_pause(ecoule: float, mini: int, maxi: int, plancher: float = 5.0,
                   alea: float = 0.5) -> float:
    """Pause avant le prochain cycle, en visant une PERIODE (pas un delai ajoute).

    Un cycle de 40 s avec une periode cible de 120 s ne dort que 80 s : la cadence
    de detection reste stable, quelle que soit la lenteur des enseignes.
    `alea` in [0,1] choisit la cible entre mini et maxi (jitter anti-motif).

    >>> calculer_pause(40, 100, 140, alea=0.5)
    80.0
    >>> calculer_pause(500, 100, 140)
    5.0
    """
    cible = mini + (maxi - mini) * alea
    return max(float(plancher), round(cible - ecoule, 2))
