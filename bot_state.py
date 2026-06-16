"""
bot_state.py - Etat partage, en memoire, entre la boucle de scraping (main) et
le bot Discord (discord_bot).

Sert pour /pause et /resume : couper temporairement l'envoi des alertes sans
arreter le bot. (Les cycles continuent de tourner ; seules les alertes sont mises
en silence.)
"""

_pause = False


def alertes_en_pause() -> bool:
    return _pause


def set_pause(valeur: bool) -> None:
    global _pause
    _pause = bool(valeur)
