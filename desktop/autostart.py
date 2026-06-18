"""
autostart.py — Démarrage automatique de l'appli avec Windows.

Écrit (ou retire) une valeur dans la clé de registre
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. Au prochain ouverture de
session Windows, l'appli se lance toute seule → utile pour une surveillance 24h/24.

Sans effet hors Windows (retourne simplement False).
"""
from __future__ import annotations

import os
import sys
import logging

logger = logging.getLogger("autostart")

_CLE = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NOM = "TCGStockBot"


def _commande_lancement() -> str:
    """Commande qui (re)lance l'appli, selon qu'on est packagé (.exe) ou en dev."""
    if getattr(sys, "frozen", False):
        # Application empaquetée : on relance l'exécutable lui-même.
        return f'"{sys.executable}"'
    # En développement : pythonw (sans console) + le script GUI.
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_app.py")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{script}"'


def disponible() -> bool:
    return os.name == "nt"


def est_actif() -> bool:
    if not disponible():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CLE) as cle:
            winreg.QueryValueEx(cle, _NOM)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def activer() -> bool:
    if not disponible():
        return False
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CLE) as cle:
            winreg.SetValueEx(cle, _NOM, 0, winreg.REG_SZ, _commande_lancement())
        logger.info("Démarrage auto activé.")
        return True
    except OSError as e:
        logger.error("Activation démarrage auto échouée : %s", e)
        return False


def desactiver() -> bool:
    if not disponible():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CLE, 0, winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, _NOM)
        logger.info("Démarrage auto désactivé.")
        return True
    except FileNotFoundError:
        return True  # déjà absent
    except OSError as e:
        logger.error("Désactivation démarrage auto échouée : %s", e)
        return False


def definir(actif: bool) -> bool:
    return activer() if actif else desactiver()
