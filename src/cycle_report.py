"""Suivi des statistiques par cycle de scraping."""
import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class StoreReport:
    enseigne: str
    statut: str = "pending"
    produits_trouves: int = 0
    nouveautes: int = 0
    restocks: int = 0
    ruptures: int = 0
    duree_s: float = 0.0

    def __post_init__(self):
        self._debut = time.time()

    def terminer(self, statut: str):
        self.duree_s = round(time.time() - self._debut, 2)
        self.statut = statut


@dataclass
class CycleReport:
    cycle_num: int
    mode: str = "recherche"
    timestamp: float = field(default_factory=time.time)
    stores: List[StoreReport] = field(default_factory=list)

    def ajouter_store(self, store: StoreReport):
        self.stores.append(store)

    def resume(self) -> str:
        total_p = sum(s.produits_trouves for s in self.stores)
        total_n = sum(s.nouveautes for s in self.stores)
        total_r = sum(s.restocks for s in self.stores)
        total_ru = sum(s.ruptures for s in self.stores)
        bloques = [s.enseigne for s in self.stores if s.statut == "blocked"]
        erreurs = [s.enseigne for s in self.stores if s.statut in ("timeout", "parser_error", "empty")]
        sains = [s.enseigne for s in self.stores if s.statut == "healthy"]
        lines = [
            f"=== RAPPORT CYCLE {self.cycle_num} ({self.mode.upper()}) ===",
            f"Produits: {total_p} | Nouveautes: {total_n} | Restocks: {total_r} | Ruptures: {total_ru}",
            f"Sains: {', '.join(sains) or 'aucun'}",
            f"Bloques: {', '.join(bloques) or 'aucun'}",
            f"Erreurs/vides: {', '.join(erreurs) or 'aucun'}",
        ]
        return "\n".join(lines)
