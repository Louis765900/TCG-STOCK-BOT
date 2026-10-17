"""C6 : /watch /unwatch /list - validation d'URL, doublons, pagination, prise en compte
par le moteur de surveillance."""
import os
import sys
import asyncio
import tempfile
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import config
import database
import discord_bot as bot
import main

URL = "https://www.auchan.fr/pokemon-coffret-dresseur-elite-ev05/pr-C1234567"


def test_normaliser_url():
    n = bot.normaliser_url
    assert n(URL) == URL
    # Doublons : fragment, parametres de suivi, casse de l'hote ignores.
    assert n("https://WWW.Auchan.fr/p/x?utm_source=a&id=3#top") == "https://www.auchan.fr/p/x?id=3"
    # Destinations refusees (SSRF / abus).
    for mauvaise in ["", None, "http://www.auchan.fr/p", "ftp://www.auchan.fr/p",
                     "https://user:pw@www.auchan.fr/p", "https://www.auchan.fr:8080/p",
                     "https://www.auchan.fr/p x", "https://www.auchan.fr/p\nx",
                     "javascript:alert(1)", "https://" + "a" * 600 + ".fr/p",
                     "https://127.0.0.1/p", "https://[::1]/p"]:
        res = n(mauvaise)
        assert res is None or bot._enseigne_pour_url(res) is None, mauvaise
    assert n("https://auchan.fr@evil.com/p") is None            # identifiants refuses


async def _scenario():
    config.ENABLE_PRICE_CHART = False
    config.ENABLED_STORES = ["Auchan", "Leclerc"]
    fd, chemin = tempfile.mkstemp(suffix=".db"); os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()

    # --- /watch : succes, doublon (meme avec parametre de suivi), invalide ---
    assert "✅" in await bot.ajouter_produit_url(URL)
    assert "déjà" in await bot.ajouter_produit_url(URL + "?utm_campaign=x")
    assert "❌" in await bot.ajouter_produit_url("http://www.auchan.fr/p")
    assert "non reconnue" in await bot.ajouter_produit_url("https://evil.com/?x=auchan.fr")
    assert "désactivée" in await bot.ajouter_produit_url("https://www.cultura.com/p/x.html")
    assert len(await database.recuperer_tous_produits()) == 1

    # --- Boutique Shopify configuree : reconnue ---
    config.SHOPIFY_SHOPS["MaBoutique"] = "maboutique.fr"
    config.ENABLED_STORES.append("MaBoutique")
    assert bot._enseigne_pour_url("https://maboutique.fr/products/x") == "MaBoutique"

    # --- Le moteur prend en compte l'ajout ET ne le purge pas (titre issu de l'URL) ---
    row = await database.recuperer_produit(URL)
    assert row["manuel"] == 1
    await main._purger_watchlist()
    assert await database.recuperer_produit(URL) is not None

    alertes = []

    async def fake_alerte(prod, ens, t, chart_png=None):
        alertes.append((ens, t))
        return True
    main.envoyer_alerte = fake_alerte

    class Scraper:
        _last_status = "ok"

        async def scraper_produit(self, url):
            return {"status": "ok", "en_stock": True, "prix": "39.99", "image_url": "",
                    "brand": ""}   # marque vide : le filtre auto l'aurait purge
    rapport = await main.cycle_watchlist({"Auchan": Scraper()}, 1)
    assert alertes == [("Auchan", "RESTOCK")], alertes
    assert rapport.stores[0].restocks == 1
    assert await database.recuperer_produit(URL) is not None

    # --- /unwatch ---
    assert "retiré" in await bot.retirer_produit_url(URL + "#frag")
    assert "n'est pas" in await bot.retirer_produit_url(URL)
    assert "❌" in await bot.retirer_produit_url("http://x")
    assert await database.recuperer_produit(URL) is None
    # Retire => le moteur ne le surveille plus.
    alertes.clear()
    await main.cycle_watchlist({"Auchan": Scraper()}, 2)
    assert alertes == []

    # --- /list : pagination + filtre ---
    assert "Aucun produit" in await bot.texte_liste()
    for i in range(23):
        ens = "Auchan" if i % 2 == 0 else "Leclerc"
        await database.ajouter_produit(f"https://x/{i}", f"Produit *{i}*", ens, i % 3 == 0)
    p1 = await bot.texte_liste(1)
    assert "page 1/3" in p1 and "23" in p1 and "page:2" in p1
    p3 = await bot.texte_liste(3)
    assert "page 3/3" in p3 and "page:" not in p3
    assert "page 3/3" in await bot.texte_liste(99)      # hors bornes : borne haute
    assert "page 1/3" in await bot.texte_liste(-5)      # hors bornes : borne basse
    leclerc = await bot.texte_liste(1, "leclerc")
    assert "[Leclerc]" in leclerc and "[Auchan]" not in leclerc
    assert "Aucun produit suivi pour" in await bot.texte_liste(1, "Inconnue")
    assert "\\*" in p1                                   # markdown du titre echappe
    assert len(p1) < 2000

    # --- /watchlist (ancienne commande) toujours operationnelle ---
    assert "Watchlist" in await bot.texte_watchlist()

    await database.fermer()
    os.remove(chemin)


def test():
    test_normaliser_url()
    asyncio.run(_scenario())


if __name__ == "__main__":
    test()
    print("OK")
