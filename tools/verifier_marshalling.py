"""Vérifie qu'un objet JS du QML arrive bien comme dict dans le pont (bug QJSValue)."""
import os
import sys
import json
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
d = tempfile.mkdtemp()
os.environ["TCG_DATA_DIR"] = d
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import config  # noqa: F401
from gui_bridge import GuiBridge

QML = b"""
import QtQuick
Item {
    Component.onCompleted: {
        // Exactement ce que fait l'assistant : on passe un objet JS.
        bridge.enregistrerReglages({ "DISCORD_WEBHOOK_URL": "https://exemple/webhook", "MIN_SLEEP": "77" })
    }
}
"""

erreurs = []


def main() -> int:
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    bridge = GuiBridge()
    bridge.erreur.connect(lambda m: erreurs.append(m))
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.loadData(QML)
    QTimer.singleShot(300, app.quit)
    app.exec()

    if erreurs:
        print("ÉCHEC — erreurs émises :", erreurs)
        return 1
    chemin = os.path.join(d, "settings.json")
    if not os.path.exists(chemin):
        print("ÉCHEC — settings.json non écrit.")
        return 1
    data = json.load(open(chemin, encoding="utf-8"))
    if data.get("DISCORD_WEBHOOK_URL") != "https://exemple/webhook" or data.get("MIN_SLEEP") != "77":
        print("ÉCHEC — contenu inattendu :", data)
        return 1
    print("OK — objet QML reçu et enregistré correctement :", data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
