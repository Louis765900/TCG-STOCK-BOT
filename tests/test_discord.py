import os
import sys
import asyncio
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import discord_webhook as dw
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

    async def fake(payload, chart_png=None):
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


if __name__ == "__main__":
    test()
    print("OK")
