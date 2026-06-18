"""
Vérifie que l'interface QML se charge sans erreur (sans afficher de fenêtre).

Usage : python tools/verifier_qml.py
Utilise la plateforme Qt 'offscreen' : aucune fenêtre, idéal pour un check rapide
ou une CI. Sort en code 0 si l'IHM charge, 1 sinon.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType

import config  # noqa: F401  (applique la config)
from gui_bridge import GuiBridge

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_DIR = os.path.join(BASE, "gui")

_erreurs = []


def main() -> int:
    app = QGuiApplication(sys.argv)
    qmlRegisterSingletonType(
        QUrl.fromLocalFile(os.path.join(GUI_DIR, "Theme.qml")), "App", 1, 0, "Theme"
    )
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: _erreurs.extend(str(w.toString()) for w in ws))

    bridge = GuiBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("bridge", bridge)
    ctx.setContextProperty("premierLancement", False)
    ctx.setContextProperty("appVersion", "1.0")

    engine.load(QUrl.fromLocalFile(os.path.join(GUI_DIR, "Main.qml")))

    # Laisse un tick pour que les composants se créent, puis on quitte.
    QTimer.singleShot(600, app.quit)
    app.exec()

    if not engine.rootObjects():
        print("ÉCHEC : Main.qml n'a pas pu être chargé.")
        for e in _erreurs:
            print("  -", e)
        return 1
    # Des warnings non bloquants peuvent exister ; on les affiche mais on n'échoue
    # que sur absence de root object (= erreur fatale de chargement).
    if _erreurs:
        print("Chargé, mais avec des avertissements :")
        for e in _erreurs:
            print("  -", e)
        return 2
    print("OK : interface QML chargée sans erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
