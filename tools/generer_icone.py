"""Génère l'icône de l'appli (gui/icon.png + gui/icon.ico) — losange dégradé."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import (QGuiApplication, QImage, QPainter, QPainterPath,
                           QLinearGradient, QColor, QPen)
from PySide6.QtCore import QPointF, Qt

GUI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui")


def dessiner(taille: int) -> QImage:
    img = QImage(taille, taille, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    m = taille * 0.06
    r = taille * 0.22
    fond = QPainterPath()
    fond.addRoundedRect(m, m, taille - 2 * m, taille - 2 * m, r, r)
    grad = QLinearGradient(0, m, 0, taille - m)
    grad.setColorAt(0.0, QColor("#7aa2f7"))
    grad.setColorAt(1.0, QColor("#bb9af7"))
    p.fillPath(fond, grad)

    # Losange central (rappel du logo ◈).
    c = taille / 2.0
    d = taille * 0.26
    los = QPainterPath()
    los.moveTo(QPointF(c, c - d))
    los.lineTo(QPointF(c + d, c))
    los.lineTo(QPointF(c, c + d))
    los.lineTo(QPointF(c - d, c))
    los.closeSubpath()
    p.fillPath(los, QColor("#0f1117"))
    p.setPen(QPen(QColor(255, 255, 255, 70), taille * 0.012))
    p.drawPath(los)

    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv)
    png = dessiner(256)
    chemin_png = os.path.join(GUI_DIR, "icon.png")
    png.save(chemin_png, "PNG")
    chemin_ico = os.path.join(GUI_DIR, "icon.ico")
    ok = png.save(chemin_ico, "ICO")
    print("PNG :", chemin_png)
    print("ICO :", chemin_ico, "(ok)" if ok else "(échec — png seul)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
