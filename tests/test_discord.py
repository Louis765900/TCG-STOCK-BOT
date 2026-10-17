import os
import sys
import asyncio
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import discord_webhook as dw
_ENVOYER_REEL = dw._envoyer
from discord_webhook import build_alert_embed, build_buy_components
from product_format import normalize_product
import discord_bot as db


class _FauxUser:
    def __init__(self, uid, admin):
        self.id = uid
        class _P: administrator = admin
        self.guild_permissions = _P()


class _FauxInteraction:
    def __init__(self, user):
        self.user = user


def test_securite_discord():
    # Validation de domaine par hostname EXACT (anti-SSRF) : une sous-chaine ne suffit pas.
    assert db._enseigne_pour_url("https://www.auchan.fr/p/x") == "Auchan"
    assert db._enseigne_pour_url("https://www.e.leclerc/produit") == "Leclerc"
    assert db._enseigne_pour_url("https://www.smythstoys.com/fr/x") == "Smyths"
    assert db._enseigne_pour_url("https://evil.com/?x=auchan.fr") is None
    assert db._enseigne_pour_url("https://auchan.fr.evil.com/x") is None
    assert db._enseigne_pour_url("http://169.254.169.254/latest/?d=auchan.fr") is None

    # Autorisation : sans OWNER_ID -> admin requis ; membre lambda refusé.
    db.DISCORD_OWNER_ID = ""
    assert db.est_autorise(_FauxInteraction(_FauxUser(1, True))) is True
    assert db.est_autorise(_FauxInteraction(_FauxUser(2, False))) is False
    # Avec OWNER_ID -> seul cet utilisateur, même un admin tiers est refusé.
    db.DISCORD_OWNER_ID = "42"
    assert db.est_autorise(_FauxInteraction(_FauxUser(42, False))) is True
    assert db.est_autorise(_FauxInteraction(_FauxUser(7, True))) is False
    db.DISCORD_OWNER_ID = ""

PROD = {"url": "https://x.fr/p/pr-C1", "titre": "Coffret Pokemon", "prix": "54.99",
        "en_stock": True, "country": "FR", "ean": "0820650559013",
        "old_price": "69.99", "direct_links": {"Auchan": "https://x.fr/p"}}


def test():
    # Boutons : Acheter (lien) + recherches + Autobuy (interactif)
    comps = build_buy_components(normalize_product(dict(PROD), "Auchan"))
    boutons = comps[0]["components"]
    labels = [b.get("label") for b in boutons]
    assert any("Acheter" in l for l in labels)
    assert any(b.get("custom_id") == "autobuy" for b in boutons)

    # Libellés d'embed selon le type
    for t, attendu in [("NOUVEAUTE", "Nouveau"), ("RESTOCK", "Restock"),
                       ("DEAL", "Baisse de prix")]:
        e = build_alert_embed(dict(PROD), "Auchan", t)
        assert attendu in e["footer"]["text"], (t, e["footer"])

    # Ping de rôle : présent si configuré, absent sinon
    captures = {}

    async def fake(payload, chart_png=None, enseigne=None):
        captures.clear(); captures.update(payload)

    dw._envoyer = fake
    dw.DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/x/y"

    dw.DISCORD_ALERT_ROLE_ID = ""
    asyncio.run(dw.envoyer_alerte(dict(PROD), "Auchan", "RESTOCK"))
    assert "content" not in captures

    dw.DISCORD_ALERT_ROLE_ID = "123"
    asyncio.run(dw.envoyer_alerte(dict(PROD), "Auchan", "RESTOCK"))
    assert captures.get("content") == "<@&123>"
    assert captures.get("allowed_mentions") == {"roles": ["123"]}

    # Heartbeat ne ping jamais
    asyncio.run(dw.envoyer_message({"title": "resume"}))
    assert "content" not in captures

    # Correctifs sécurité (SSRF /add + autorisation des commandes)
    test_securite_discord()
    test_routage_par_enseigne()


if __name__ == "__main__":
    test()
    print("OK")


def test_routage_par_enseigne():
    dw._envoyer = _ENVOYER_REEL
    dw.DISCORD_WEBHOOK_URL = "https://defaut"
    dw.DISCORD_WEBHOOKS_BY_STORE = {"Auchan": "https://auchan"}
    dw.DISCORD_CHANNELS_BY_STORE = {"Auchan": "111"}
    dw.DISCORD_CHANNEL_ID = "999"
    assert dw.webhook_pour("Auchan") == "https://auchan"
    assert dw.webhook_pour("Leclerc") == "https://defaut"      # repli par defaut
    assert dw.webhook_pour(None) == "https://defaut"
    assert dw.canal_pour("Auchan") == "111"
    assert dw.canal_pour("Leclerc") == "999"

    # Un webhook propre a l'enseigne suffit meme sans webhook par defaut.
    dw.DISCORD_WEBHOOK_URL = ""
    vus = []

    async def faux_post(session, url, **kw):
        vus.append(url)
        return True
    ancien_post, ancien_bot = dw._post_avec_retry, dw._mode_bot
    dw._post_avec_retry, dw._mode_bot = faux_post, lambda: False
    try:
        prod = {"url": "https://x/p", "titre": "Coffret", "prix": "10", "en_stock": True}
        assert asyncio.run(dw.envoyer_alerte(prod, "Auchan", "RESTOCK")) is True
        assert vus == ["https://auchan"]
        assert asyncio.run(dw.envoyer_alerte(prod, "Leclerc", "RESTOCK")) is True
        assert vus == ["https://auchan"]      # rien a livrer pour Leclerc : pas d'envoi
    finally:
        dw._post_avec_retry, dw._mode_bot = ancien_post, ancien_bot
        asyncio.run(dw.fermer_session())
