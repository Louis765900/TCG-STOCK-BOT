"""Carrefour : lecture de fiche (JSON-LD), listing, stock direct vs marketplace, inconnu."""
import asyncio
import json
import os
import sys
import tempfile
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config
import database
import main
import discord_bot as bot
import scrapers.carrefour as carrefour
from scrapers.carrefour import analyser_fiche, analyser_listing, CarrefourScraper
from product_format import est_revendeur

URL = "https://www.carrefour.fr/p/coffret-pokemon-asmodee-0820650557446"


def _offre(vendeur, dispo, prix):
    return {"@type": "Offer", "price": prix, "priceCurrency": "EUR",
            "availability": f"https://schema.org/{dispo}",
            "seller": {"@type": "Organization", "name": vendeur}}


def _page(offres, agregat=True):
    produit = {"@context": "https://schema.org/", "@type": "Product", "name": "Coffret Pokémon",
               "gtin13": "0820650557446", "brand": {"@type": "Brand", "name": "ASMODEE"},
               "image": {"@type": "ImageObject", "url": "https://media.carrefour.fr/x.jpg"}}
    if offres is not None:
        produit["offers"] = ({"@type": "AggregateOffer", "offers": offres} if agregat
                             else offres[0])
    autre = {"@type": "BreadcrumbList", "itemListElement": []}
    return ('<html><script type="application/ld+json">' + json.dumps(autre) + "</script>"
            '<script type="application/ld+json">' + json.dumps(produit) + "</script></html>")


def test_fiche():
    # Livraison Carrefour en stock => en stock, vendeur Carrefour (officiel), prix direct
    r = analyser_fiche(_page([_offre("Carrefour Livraison", "InStock", 24.99),
                              _offre("Marchand X", "InStock", 99)]))
    assert r["status"] == "ok" and r["en_stock"] is True and r["stock_etat"] == "en_stock"
    assert r["prix"] == "24.99" and r["seller"] == "Carrefour" and r["ean"] == "0820650557446"
    assert r["brand"] == "ASMODEE" and r["image_url"].endswith("x.jpg")
    assert r["stock_quantity"] is None                        # jamais de quantite inventee
    assert not est_revendeur("Carrefour", r["seller"])

    # Livraison "InStoreOnly" + Drive InStock => PAS du stock en ligne (drive signale)
    r = analyser_fiche(_page([_offre("Carrefour Livraison", "InStoreOnly", 24.99),
                              _offre("Carrefour Drive", "InStock", 24.99)]))
    assert r["en_stock"] is False and r["stock_etat"] == "rupture" and r["drive"] is True
    assert r["prix"] == "24.99"

    # Seulement des marchands tiers en stock => rupture Carrefour, prix tiers JAMAIS expose
    offres = [_offre("1foDiscount", "InStock", 31.83), _offre("Leasi", "InStock", 104)]
    r = analyser_fiche(_page(offres))
    assert r["en_stock"] is False and r["prix"] == "N/A" and r["offres_marketplace"] == 2
    # ... sauf option explicite : alors vendeur = tiers => revendeur (masquable)
    r = analyser_fiche(_page(offres), inclure_marketplace=True)
    assert r["en_stock"] is True and r["seller"] == "1foDiscount" and r["prix"] == "31.83"
    assert est_revendeur("Carrefour", r["seller"])

    # Offre unique (non agregee), rupture explicite
    r = analyser_fiche(_page([_offre("Carrefour", "OutOfStock", 12)], agregat=False))
    assert r["en_stock"] is False and r["prix"] == "12.00"
    # Aucune offre => rupture (rien ne prouve une disponibilite), prix N/A
    r = analyser_fiche(_page(None))
    assert r["status"] == "ok" and r["en_stock"] is False and r["prix"] == "N/A"
    r = analyser_fiche(_page([]))
    assert r["en_stock"] is False and r["nb_offres"] == 0
    # Prix invalide / nul jamais expose
    assert analyser_fiche(_page([_offre("Carrefour", "InStock", 0)]))["prix"] == "N/A"
    assert analyser_fiche(_page([_offre("Carrefour", "InStock", "abc")]))["prix"] == "N/A"

    # Pas de Product / HTML casse / vide => INCONNU (jamais "en stock" par defaut)
    for html in ("<html>rien</html>", "",
                 '<script type="application/ld+json">{casse</script>',
                 '<script type="application/ld+json">{"@type":"Organization"}</script>'):
        r = analyser_fiche(html)
        assert r["status"] == "inconnu" and r["en_stock"] is False, html


def test_listing():
    html = """
    <article class="product-list-card-plp-grid" data-testid="0820650557446">
      <a data-testid="product-card-title" href="/p/coffret-pokemon-asmodee-0820650557446?s=2145">
        <h3> Coffret   Pokémon </h3></a></article>
    <article data-testid="1"><a data-testid="product-card-title"
        href="/p/coffret-pokemon-asmodee-0820650557446"><h3>Doublon</h3></a></article>
    <article data-testid="2"><a data-testid="product-card-title" href="/autre/page">
        <h3>Hors /p/</h3></a></article>
    <a href="/p/sans-testid">pas une carte</a>"""
    cartes = analyser_listing(html)
    assert cartes == [{"url": URL, "titre": "Coffret Pokémon", "ean": "0820650557446"}]


async def _decouverte():
    cartes = "".join(
        f'<article data-testid="{i}"><a data-testid="product-card-title" href="/p/{slug}-{i}">'
        f"<h3>{t}</h3></a></article>" for i, (slug, t) in enumerate([
            ("coffret", "Coffret Pokémon Dresseur d'Élite ME05"),
            ("peluche", "Peluche Pikachu 30 cm"),
            ("display", "Display Pokémon ME04 36 boosters"),
            ("op", "One Piece Carte Display OP13"),
        ], start=1000))
    fiches = {
        "https://www.carrefour.fr/p/coffret-1000":
            _page([_offre("Carrefour Livraison", "InStock", 54.99)]),
        "https://www.carrefour.fr/p/display-1002": "<html>page changee</html>",   # illisible
        "https://www.carrefour.fr/p/op-1003": _page([_offre("Carrefour", "OutOfStock", 99)]),
    }
    vus = []

    async def faux_get(url, timeout_ms=0):
        vus.append(url)
        if "/r/" in url:
            if "page=" not in url and "licence,pokemon" in url:
                return cartes, "ok", None
            return "<html></html>", "ok", None      # pagination terminee
        if url in fiches:
            return fiches[url], "ok", None
        return None, "blocked", "http_429"

    async def vite(_):
        return None

    reel_get, reel_sleep = carrefour.http_get, carrefour.asyncio.sleep
    carrefour.http_get, carrefour.asyncio.sleep = faux_get, vite
    try:
        sc = CarrefourScraper(None)
        prods = await sc.scraper_recherche()
    finally:
        carrefour.http_get, carrefour.asyncio.sleep = reel_get, reel_sleep
    return prods, sc, vus


def test_decouverte():
    prods, sc, vus = asyncio.run(_decouverte())
    urls = {p["url"] for p in prods}
    # Peluche filtree AVANT toute requete ; fiche illisible ecartee (jamais presumee en stock)
    assert not any("peluche" in u for u in vus)
    assert len(prods) == 2 and not any("display-1002" in u for u in urls)
    coffret = next(p for p in prods if p["url"].endswith("coffret-1000"))
    assert coffret["en_stock"] is True and coffret["prix"] == "54.99"
    assert coffret["seller"] == "Carrefour" and coffret["ean"] == "0820650557446"
    op = next(p for p in prods if p["url"].endswith("op-1003"))
    assert op["en_stock"] is False
    assert sc._last_status == "ok"
    assert CarrefourScraper.CONCURRENCE_WATCHLIST <= 2


async def _moteur():
    config.ENABLE_PRICE_CHART = False
    fd, chemin = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()
    alertes = []

    async def fake(prod, ens, t, chart_png=None):
        alertes.append((ens, t, prod["url"]))
        return True
    main.envoyer_alerte = fake
    main._sante = main.StoreHealth(seuil=99, pause_s=1)

    # --- Fiche "inconnu" : etat inchange, aucune alerte, enseigne en parser_error ---
    await database.ajouter_produit(URL, "Coffret Pokémon Dresseur d'Élite ME05", "Carrefour",
                                   False, prix="50", manuel=True)

    class Inconnu:
        _last_status = "ok"
        CONCURRENCE_WATCHLIST = 2

        async def scraper_produit(self, url):
            return {"status": "inconnu", "en_stock": False, "prix": "N/A", "image_url": ""}
    rap = await main.cycle_watchlist({"Carrefour": Inconnu()}, 1)
    assert rap.stores[0].statut == "parser_error"           # pas "healthy" !
    assert alertes == [] and (await database.recuperer_produit(URL))["en_stock"] == 0

    # --- Erreur reseau : ni rupture ni alerte ---
    class Bloque(Inconnu):
        async def scraper_produit(self, url):
            return {"status": "blocked", "en_stock": False, "prix": "N/A", "image_url": ""}
    await main.cycle_watchlist({"Carrefour": Bloque()}, 2)
    assert alertes == [] and (await database.recuperer_produit(URL))["en_stock"] == 0

    # --- Vrai restock lu sur la fiche => une alerte ---
    class Stock(Inconnu):
        async def scraper_produit(self, url):
            return analyser_fiche(_page([_offre("Carrefour Livraison", "InStock", 54.99)]))
    await main.cycle_watchlist({"Carrefour": Stock()}, 3)
    assert [a[:2] for a in alertes] == [("Carrefour", "RESTOCK")]

    # --- Amorcage PAR ENSEIGNE : nouvelle enseigne => decouverte silencieuse ---
    alertes.clear()

    def decouverte(url):
        class D:
            _last_status = "ok"

            async def scraper_recherche(self):
                return [{"url": url, "titre": "Display Pokémon ME04 36 boosters",
                         "prix": "199.99", "image_url": "", "en_stock": True,
                         "brand": "Pokémon"}]
        return D()
    await main.cycle_recherche({"Dracaugames": decouverte("https://x/nouveau-1")}, 4)
    assert alertes == []                                    # enseigne inconnue en base
    assert await database.recuperer_produit("https://x/nouveau-1") is not None
    # Enseigne desormais connue : une vraie nouveaute alerte bien
    await main.cycle_recherche({"Dracaugames": decouverte("https://x/nouveau-2")}, 5)
    assert [a[1] for a in alertes] == ["NOUVEAUTE"]

    await database.fermer()
    os.remove(chemin)


def test_moteur():
    asyncio.run(_moteur())


def test_url_discord():
    config.ENABLED_STORES = list(config.ENABLED_STORES) + ["Carrefour", "Dracaugames"]
    assert bot._enseigne_pour_url(URL) == "Carrefour"
    assert bot.normaliser_url(URL + "?s=2145") == URL           # ?s=<vendeur> retire
    assert bot._enseigne_pour_url("https://www.dracaugames.com/products/x") == "Dracaugames"
    assert bot._enseigne_pour_url("https://carrefour.fr.evil.com/p/x") is None


def test():
    test_fiche()
    test_listing()
    test_decouverte()
    test_url_discord()
    test_moteur()


if __name__ == "__main__":
    test()
    print("OK")
