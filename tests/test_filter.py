"""Tests du filtre TCG : garde Pokémon + One Piece FR scellés, rejette le reste."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from filter_utils import est_tcg_valide_local as v


# (titre, marque, attendu)
CAS = [
    # --- Pokémon FR : doit PASSER ---
    ("Pokémon EV05 : Coffret Dresseur d'Elite", "", True),
    ("Display M1S - Scellé", "Pokémon", True),          # marque seule porte "pokemon"
    ("25Th V Card Box - Pokémon", "", True),
    ("Coffret Pokémon Bundle 6 boosters EV06.5 - Fable Nébuleuse", "", True),
    ("POKEMON Pack Sticker Day", "", True),              # liste blanche
    # --- One Piece FR : doit PASSER ---
    ("ETB One Piece PRB01", "", True),
    ("Display One Piece OP02", "", True),
    ("One Piece : OP11 Booster Blister (24) FR", "Asmodee", True),
    ("One Piece : Starter Deck 21 (6) FR", "Asmodee", True),
    ("Coffret One Piece Romance Dawn", "", True),
    # --- Éditions étrangères : doit ÊTRE REJETÉ (FR uniquement) ---
    ("Pokemon Booster Japonais EV05", "", False),
    ("Display One Piece OP05 Japonais", "", False),
    ("One Piece OP-05 Booster Box (English)", "", False),
    ("ONE PIECE JCC - Starter Deck Straw hat Crew ST01 x6 EN (12/22)", "Bandai", False),
    # --- Hors-cible (jouets, merch, autres TCG, manga, food) : REJETÉ ---
    ("BANDAI Arène Pokémon et 2 spinners", "", False),
    ("Coffret Pokémon Quiz box 100 questions", "", False),
    ("Figurine One Piece Luffy Ichibansho", "", False),
    ("LEGO ONE PIECE - Le Bateau Pirate Vogue Merry", "LEGO", False),
    ("One Piece - Coffret Île des hommes-poissons (Tomes 62 à 70)", "", False),
    ("One Piece Films - Coffret 3", "", False),
    ("Mon Bubble Tea - One Piece (Coffret)", "", False),
    ("One Piece - Jeu de 54 cartes - Boîte de cartes (Coffret)", "", False),
    ("Display Yu-Gi-Oh OCG", "", False),                 # autre TCG
    # --- Multi-TCG : un "booster/display" sans univers ne doit PAS passer ---
    ("Booster de Jeu - Horizon du Modern III - FR", "Novalis", False),  # Magic
    ("Display Lorcana - Les Terres d'Encre", "", False),
    ("Booster Disney Lorcana", "", False),
]


def test():
    erreurs = []
    for titre, marque, attendu in CAS:
        if v(titre, marque) != attendu:
            erreurs.append(f"  {titre!r} (marque {marque!r}) -> {not attendu}, attendu {attendu}")
    assert not erreurs, "Cas du filtre en échec :\n" + "\n".join(erreurs)


if __name__ == "__main__":
    test()
    print("OK")
