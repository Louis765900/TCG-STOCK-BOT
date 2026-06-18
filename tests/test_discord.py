import os
import sys
import asyncio
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import discord_webhook as dw
from discord_webhook import build_alert_embed, build_buy_components
from product_format import normalize_product

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


if __name__ == "__main__":
    test()
    print("OK")
