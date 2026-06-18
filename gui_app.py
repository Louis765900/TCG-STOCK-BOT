"""
gui_app.py — Point d'entrée de l'application graphique TCG-STOCK-BOT.

Crée l'application Qt, branche le pont (gui_bridge.GuiBridge) et charge
l'interface QML (gui/Main.qml). Esthétique NixOS / Hyprland : fenêtre arrondie,
sombre, animée.

Lancement : `python gui_app.py`
"""
from __future__ import annotations

import os
import sys
import logging

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

import config  # applique les couches de configuration au démarrage
from gui_bridge import GuiBridge

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gui_app")

BASE = os.path.dirname(os.path.abspath(__file__))
GUI_DIR = os.path.join(BASE, "gui")


def _premier_lancement() -> bool:
    """Vrai si aucun canal Discord n'est encore configuré (→ assistant)."""
    has_webhook = bool(config.DISCORD_WEBHOOK_URL)
    has_bot = bool(config.DISCORD_BOT_TOKEN and config.DISCORD_CHANNEL_ID)
    return not (has_webhook or has_bot)


def main() -> int:
    QGuiApplication.setApplicationName("TCG Stock Bot")
    QGuiApplication.setOrganizationName("TCGStockBot")
    app = QGuiApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    icone = os.path.join(GUI_DIR, "icon.png")
    if os.path.exists(icone):
        app.setWindowIcon(QIcon(icone))

    # Theme.qml exposé comme singleton sous le module "App" (import App 1.0).
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(os.path.join(GUI_DIR, "Theme.qml")),
        "App", 1, 0, "Theme",
    )

    engine = QQmlApplicationEngine()
    bridge = GuiBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("premierLancement", _premier_lancement())
    ctx.setContextProperty("appVersion", "1.0")

    engine.load(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Main.qml")))
    if not engine.rootObjects():
        logger.error("Échec du chargement de l'interface QML.")
        return 1

    logger.info("Interface lancée. Premier lancement : %s", _premier_lancement())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
