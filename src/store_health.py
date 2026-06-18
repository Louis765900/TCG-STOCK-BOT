"""
store_health.py - Mise en veille automatique des enseignes en echec.

Certaines enseignes (Cultura, King Jouet, Smyths) sont protegees et echouent
souvent. Plutot que de relancer un navigateur lourd a chaque cycle pour rien, on
suit leur "sante" : apres N echecs consecutifs, on met l'enseigne en veille pour
un moment, puis on lui redonne sa chance.

Statuts consideres comme un ECHEC (cf. cycle_report.StoreReport.statut) :
    "blocked", "timeout", "parser_error".
Les statuts "healthy" et "empty" = l'enseigne a repondu (succes) : on remet le
compteur a zero. ("empty" = a repondu mais 0 produit, ce n'est pas un blocage.)
"""

from __future__ import annotations

import time

STATUTS_ECHEC = {"blocked", "timeout", "parser_error"}


class StoreHealth:
    def __init__(self, seuil: int = 3, pause_s: int = 3600):
        self.seuil = seuil          # nb d'echecs consecutifs avant mise en veille
        self.pause_s = pause_s      # duree de la veille (secondes)
        self._echecs: dict[str, int] = {}
        self._veille_jusqu: dict[str, float] = {}

    def en_veille(self, enseigne: str) -> bool:
        """Vrai si l'enseigne est actuellement en veille (a sauter)."""
        return time.time() < self._veille_jusqu.get(enseigne, 0.0)

    def minutes_restantes(self, enseigne: str) -> int:
        restant = self._veille_jusqu.get(enseigne, 0.0) - time.time()
        return max(int(restant / 60) + 1, 0)

    def enregistrer(self, enseigne: str, statut: str) -> bool:
        """
        Met a jour la sante apres un cycle. Retourne True si l'enseigne vient
        d'etre mise en veille (pour pouvoir le logger).
        """
        if statut not in STATUTS_ECHEC:
            # Succes : on oublie les echecs et on leve une eventuelle veille.
            self._echecs[enseigne] = 0
            self._veille_jusqu.pop(enseigne, None)
            return False

        self._echecs[enseigne] = self._echecs.get(enseigne, 0) + 1
        if self._echecs[enseigne] >= self.seuil:
            self._veille_jusqu[enseigne] = time.time() + self.pause_s
            self._echecs[enseigne] = 0  # budget de retry frais apres la veille
            return True
        return False
