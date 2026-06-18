"""Tests du Chantier A : navigateur optionnel, config en couches, contrôleur du bot."""
import os
import sys
import json
import time
import asyncio
import tempfile

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import config
import bot_state
import main
from bot_controller import BotController
from scrapers.leclerc import LeclercScraper
from scrapers.shopify import ShopifyScraper
from scrapers.woocommerce import WooCommerceScraper
from scrapers.auchan import AuchanScraper
from scrapers.cultura import CulturaScraper
from scrapers.kingjouet import KingJouetScraper


def _test_navigateur_optionnel():
    # Les sources HTTP/JSON ne nécessitent pas de navigateur…
    assert LeclercScraper.utilise_navigateur is False
    assert ShopifyScraper.utilise_navigateur is False
    assert WooCommerceScraper.utilise_navigateur is False
    assert AuchanScraper.utilise_navigateur is False
    # …les sites blindés, si.
    assert CulturaScraper.utilise_navigateur is True
    assert KingJouetScraper.utilise_navigateur is True


def _test_config_couches():
    d = tempfile.mkdtemp()
    os.environ["TCG_DATA_DIR"] = d
    try:
        assert config.dossier_donnees() == d
        chemin = config.sauver_reglages_utilisateur({"TCG_TEST_KEY": "hello", "MIN_SLEEP": "42"})
        assert os.path.exists(chemin)
        assert os.environ.get("TCG_TEST_KEY") == "hello"
        data = json.load(open(chemin, encoding="utf-8"))
        assert data["TCG_TEST_KEY"] == "hello" and data["MIN_SLEEP"] == "42"
        # _appliquer_couche réinjecte bien dans l'environnement
        os.environ.pop("TCG_TEST_KEY", None)
        config._appliquer_couche(chemin)
        assert os.environ.get("TCG_TEST_KEY") == "hello"
    finally:
        os.environ.pop("TCG_DATA_DIR", None)
        os.environ.pop("TCG_TEST_KEY", None)
        os.environ.pop("MIN_SLEEP", None)


def _test_dormir_interruptible():
    async def scenario():
        ev = asyncio.Event()
        ev.set()
        t0 = time.monotonic()
        await main._dormir(5.0, ev)  # doit revenir tout de suite (event déjà set)
        assert time.monotonic() - t0 < 1.0
    asyncio.run(scenario())


def _test_controleur_start_stop():
    # On remplace la vraie boucle par une factice qui respecte stop_event
    # (évite tout réseau/Discord pendant le test).
    async def fausse_boucle(stop_event=None):
        bot_state.set_status(running=True, cycle=1)
        if stop_event is not None:
            await stop_event.wait()
        bot_state.set_status(running=False)

    vrai = main.main_loop
    main.main_loop = fausse_boucle
    try:
        ctrl = BotController()
        assert ctrl.est_actif() is False
        assert ctrl.demarrer() is True
        time.sleep(0.4)
        assert ctrl.est_actif() is True
        assert ctrl.get_status()["running"] is True
        assert ctrl.demarrer() is False        # déjà actif
        assert ctrl.arreter(timeout=5) is True  # arrêt propre
        assert ctrl.est_actif() is False
    finally:
        main.main_loop = vrai


def test():
    _test_navigateur_optionnel()
    _test_config_couches()
    _test_dormir_interruptible()
    _test_controleur_start_stop()


if __name__ == "__main__":
    test()
    print("OK")
