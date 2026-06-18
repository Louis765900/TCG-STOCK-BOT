"""
gui_app.py — Point d'entrée de l'application graphique TCG-STOCK-BOT.

Crée l'application Qt, branche le pont (gui_bridge.GuiBridge) et charge
l'interface QML (gui/Main.qml). Esthétique NixOS / Hyprland.

Fonctionne aussi bien en développement (`python gui_app.py`) qu'empaquetée en
.exe (PyInstaller). Ajoute une icône dans la barre des tâches (tray) : fermer la
fenêtre la réduit dans le tray, le bot continue de tourner 24h/24.

Options :
  --selftest   charge l'IHM sans fenêtre (offscreen) et quitte (0=OK). Sert à
               vérifier qu'un build .exe est sain.
"""
from __future__ import annotations

import os
import sys
import logging

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

logger = logging.getLogger("gui_app")


def _dossier_ressources() -> str:
    """Dossier des ressources QML : _MEIPASS si empaqueté, sinon le dossier du script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "gui")


GUI_DIR = _dossier_ressources()


def _premier_lancement(config) -> bool:
    has_webhook = bool(config.DISCORD_WEBHOOK_URL)
    has_bot = bool(config.DISCORD_BOT_TOKEN and config.DISCORD_CHANNEL_ID)
    return not (has_webhook or has_bot)


def _charger_icone() -> QIcon:
    chemin = os.path.join(GUI_DIR, "icon.png")
    if os.path.exists(chemin):
        return QIcon(chemin)
    # Repli : pastille unie (évite une icône vide si le PNG manque).
    pm = QPixmap(64, 64); pm.fill("#7aa2f7")
    return QIcon(pm)


def _selftest() -> int:
    """Charge l'IHM en mode offscreen et retourne 0 si tout charge."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import config  # noqa: F401
    from gui_bridge import GuiBridge
    app = QApplication(sys.argv)
    erreurs = []
    qmlRegisterSingletonType(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Theme.qml")),
                             "App", 1, 0, "Theme")
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: erreurs.extend(str(w.toString()) for w in ws))
    bridge = GuiBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("premierLancement", False)
    ctx.setContextProperty("appVersion", "1.0")
    engine.load(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Main.qml")))
    QTimer.singleShot(500, app.quit)
    app.exec()
    if not engine.rootObjects():
        print("SELFTEST ÉCHEC :")
        for e in erreurs:
            print("  -", e)
        return 1
    print("SELFTEST OK")
    return 0


def _diag_net() -> int:
    """Vérifie que la couche réseau marche dans l'app empaquetée (curl_cffi inclus).

    Récupère l'API Leclerc (protégée par DataDome) : si ça répond OK, c'est que
    curl_cffi est bien embarqué et opérationnel dans l'exe.
    """
    import asyncio
    import http_fetch
    from http_fetch import http_get_json
    print("curl_cffi actif :", http_fetch._CURL_OK)
    url = ("https://www.e.leclerc/api/rest/live-api/product-search"
           "?text=pokemon%20booster")

    async def run():
        data, statut, blocage = await http_get_json(url)
        n = len(data.get("items", [])) if isinstance(data, dict) else 0
        print(f"Leclerc -> statut={statut} items={n} blocage={blocage}")
        return statut == "ok" and n > 0

    ok = asyncio.run(run())
    print("DIAG-NET OK" if ok else "DIAG-NET ECHEC")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    if "--diag-net" in sys.argv:
        return _diag_net()

    import config  # applique les couches de configuration au démarrage
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from gui_bridge import GuiBridge
    import app_service

    QApplication.setApplicationName("TCG Stock Bot")
    QApplication.setOrganizationName("TCGStockBot")
    app = QApplication(sys.argv)
    # Fermer la fenêtre ne quitte PAS l'appli : elle se réduit dans le tray.
    app.setQuitOnLastWindowClosed(False)
    icone = _charger_icone()
    app.setWindowIcon(icone)

    qmlRegisterSingletonType(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Theme.qml")),
                             "App", 1, 0, "Theme")

    engine = QQmlApplicationEngine()
    bridge = GuiBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("premierLancement", _premier_lancement(config))
    ctx.setContextProperty("appVersion", "1.0")

    engine.load(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Main.qml")))
    if not engine.rootObjects():
        logger.error("Échec du chargement de l'interface QML.")
        return 1
    fenetre = engine.rootObjects()[0]

    # ---- Icône de la barre des tâches (tray) ------------------------------
    tray = QSystemTrayIcon(icone, app)
    tray.setToolTip("TCG Stock Bot")
    menu = QMenu()

    def afficher():
        fenetre.show()
        fenetre.raise_()
        fenetre.requestActivate()

    act_ouvrir = QAction("Ouvrir", app); act_ouvrir.triggered.connect(afficher)
    act_demarrer = QAction("Démarrer le bot", app)
    act_demarrer.triggered.connect(lambda: app_service.demarrer_bot())
    act_arreter = QAction("Arrêter le bot", app)
    act_arreter.triggered.connect(lambda: app_service.arreter_bot())
    act_quitter = QAction("Quitter", app)
    act_quitter.triggered.connect(app.quit)
    for a in (act_ouvrir, act_demarrer, act_arreter):
        menu.addAction(a)
    menu.addSeparator()
    menu.addAction(act_quitter)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda raison: afficher()
                           if raison == QSystemTrayIcon.Trigger else None)
    tray.show()

    # Arrêt propre du bot quand on quitte vraiment l'appli.
    def au_revoir():
        logger.info("Fermeture — arrêt du bot…")
        app_service.arreter_bot()
    app.aboutToQuit.connect(au_revoir)

    logger.info("Interface lancée. Premier lancement : %s", _premier_lancement(config))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
