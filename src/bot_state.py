"""
bot_state.py - Etat partage, en memoire, entre la boucle de scraping (main) et
le bot Discord (discord_bot).

Sert pour /pause et /resume : couper temporairement l'envoi des alertes sans
arreter le bot. (Les cycles continuent de tourner ; seules les alertes sont mises
en silence.)
"""

import time

_pause = False


def alertes_en_pause() -> bool:
    return _pause


def set_pause(valeur: bool) -> None:
    global _pause
    _pause = bool(valeur)


# ---------------------------------------------------------------------------
# Statut d'exécution (lu par l'interface graphique / le contrôleur du bot).
# Mis à jour par la boucle principale ; purement en mémoire.
# ---------------------------------------------------------------------------
_status = {
    "running": False,      # la boucle tourne-t-elle ?
    "cycle": 0,            # numéro du dernier cycle
    "mode": "",            # "recherche" ou "watchlist"
    "produits": 0,         # produits surveillés (watchlist)
    "alertes_total": 0,    # alertes envoyées depuis le démarrage
    "dernier_resume": "",  # résumé texte du dernier cycle
    "enseignes": {},       # {enseigne: statut} du dernier cycle
    "demarre_a": 0.0,      # timestamp de démarrage
    "maj": 0.0,            # timestamp de dernière mise à jour
}


def set_status(**kwargs) -> None:
    """Met à jour le statut d'exécution (appelé par la boucle principale)."""
    _status.update(kwargs)
    _status["maj"] = time.time()


def get_status() -> dict:
    """Retourne une copie du statut courant (pour l'IHM)."""
    return dict(_status)
