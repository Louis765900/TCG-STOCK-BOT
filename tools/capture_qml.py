"""Capture une image de l'interface QML (mode offscreen) pour vérifier le rendu."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

import config  # noqa: F401
from gui_bridge import GuiBridge

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_DIR = os.path.join(BASE, "gui")
SORTIE = os.path.join(BASE, "tools", "apercu.png")
PAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ASSISTANT = "--assistant" in sys.argv


def main() -> int:
    app = QGuiApplication(sys.argv)
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(os.path.join(GUI_DIR, "Theme.qml")), "App", 1, 0, "Theme"
    )
    engine = QQmlApplicationEngine()
    bridge = GuiBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("premierLancement", ASSISTANT)
    ctx.setContextProperty("appVersion", "1.0")
    engine.load(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Main.qml")))
    if not engine.rootObjects():
        print("Échec chargement.")
        return 1
    win = engine.rootObjects()[0]
    if not ASSISTANT:
        win.setProperty("pageIndex", PAGE)

    from PySide6.QtQuick import QQuickItem

    cadre = win.findChild(QQuickItem, "cadre")
    if cadre is None:
        print("Item 'cadre' introuvable.")
        return 1

    _res = {}

    def grab():
        r = cadre.grabToImage()
        _res["r"] = r  # garder une référence vivante

        def sauver():
            r.saveToFile(SORTIE)
            print("Capture :", SORTIE)
            app.quit()
        r.ready.connect(sauver)

    QTimer.singleShot(900, grab)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
