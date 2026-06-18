"""Tests du Chantier B : couche service (app_service) + pont Qt (gui_bridge)."""
import os
import sys
import json
import logging
import tempfile

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import config
import database
import app_service
import discord_webhook


def _test_couleur():
    assert app_service._to_int_couleur(0x123456) == 0x123456
    assert app_service._to_int_couleur("#FF0000") == 0xFF0000
    assert app_service._to_int_couleur("00FF00") == 0x00FF00
    assert app_service._to_int_couleur("") == 0xE30613      # défaut
    assert app_service._to_int_couleur("pasunecouleur") == 0xE30613


def _test_reglages():
    d = tempfile.mkdtemp()
    os.environ["TCG_DATA_DIR"] = d
    try:
        chemin = app_service.enregistrer_reglages(
            {"MIN_SLEEP": "90", "MASQUER_REVENDEURS": "true", "CLE_INCONNUE": "x"}
        )
        assert os.path.exists(chemin)
        data = json.load(open(chemin, encoding="utf-8"))
        assert data["MIN_SLEEP"] == "90"
        assert data["MASQUER_REVENDEURS"] == "true"
        assert "CLE_INCONNUE" not in data        # clé hors liste blanche ignorée
        reglages = app_service.lire_reglages()
        assert "MIN_SLEEP" in reglages and "ENABLED_STORES" in reglages
    finally:
        os.environ.pop("TCG_DATA_DIR", None)
        for k in ("MIN_SLEEP", "MASQUER_REVENDEURS"):
            os.environ.pop(k, None)


def _test_watchlist():
    db = os.path.join(tempfile.mkdtemp(), "test.db")
    vrai = database.DB_PATH
    database.DB_PATH = db
    try:
        loop = app_service._boucle()
        loop.executer(database.initialiser_db())
        assert app_service.lister_watchlist() == []
        loop.executer(database.ajouter_produit(
            "http://x/1", "Pokémon ETB", "Auchan", True, "29.99€"))
        produits = app_service.lister_watchlist()
        assert len(produits) == 1 and produits[0]["titre"] == "Pokémon ETB"
        assert app_service.supprimer_produit("http://x/1") is True
        assert app_service.lister_watchlist() == []
    finally:
        database.DB_PATH = vrai


def _test_logs():
    tampon = app_service.installer_capture_logs()
    recu = []
    tampon.sur_nouvelle_ligne(recu.append)
    logging.getLogger("test_gui").warning("coucou-test-log")
    assert any("coucou-test-log" in l for l in tampon.lignes())
    assert any("coucou-test-log" in l for l in recu)


def _test_envoi_compose(monkeypatch_embed=None):
    captures = {}

    async def faux_poster(embed, content=""):
        captures["embed"] = embed
        captures["content"] = content
        return True

    vrai = discord_webhook.poster_embed
    discord_webhook.poster_embed = faux_poster
    try:
        # message vide → refusé
        assert app_service.envoyer_message_compose() is False
        # message valide → embed bien construit
        ok = app_service.envoyer_message_compose(
            titre="Titre", description="Desc", couleur="#5865F2",
            footer="pied", content="@everyone")
        assert ok is True
        assert captures["embed"]["title"] == "Titre"
        assert captures["embed"]["color"] == 0x5865F2
        assert captures["embed"]["footer"]["text"] == "pied"
        assert captures["content"] == "@everyone"
    finally:
        discord_webhook.poster_embed = vrai


def _test_pont_qt():
    # Test de fumée : on instancie le pont sous une QCoreApplication et on
    # vérifie qu'une ligne de log déclenche bien le signal logLine.
    from PySide6.QtCore import QCoreApplication, QTimer
    from gui_bridge import GuiBridge

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    bridge = GuiBridge()
    recues = []
    bridge.logLine.connect(recues.append)

    # lireReglages / couleursEnseignes renvoient bien des dicts
    assert isinstance(bridge.lireReglages(), dict)
    assert isinstance(bridge.couleursEnseignes(), dict)
    assert isinstance(bridge.statut(), dict)

    logging.getLogger("test_qt").warning("ligne-qt-test")
    # Laisse la boucle Qt distribuer le signal (connexion en file d'attente).
    QTimer.singleShot(200, app.quit)
    app.exec()
    assert any("ligne-qt-test" in l for l in recues)


def test():
    _test_couleur()
    _test_reglages()
    _test_watchlist()
    _test_logs()
    _test_envoi_compose()
    _test_pont_qt()


if __name__ == "__main__":
    test()
    print("OK")
