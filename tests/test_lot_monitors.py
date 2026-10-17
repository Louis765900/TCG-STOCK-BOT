"""C8B : lecture groupee Shopify/WooCommerce, variantes, produits disparus, historique de prix."""
import asyncio
import os
import sys
import tempfile
import time
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config
import database
import main
import scrapers.shopify as shop
import scrapers.woocommerce as woo
from scrapers.shopify import ShopifyScraper, lire_variantes, choisir_collections
from scrapers.woocommerce import WooCommerceScraper


# ------------------------------------------------------------------ variantes
def _v(titre, dispo, prix="10.00", **kw):
    d = {"title": titre, "available": dispo, "price": prix}
    d.update(kw)
    return d


def test_variantes():
    # Seule la version ENDOMMAGEE est disponible => PAS en stock (sinon faux restock)
    r = lire_variantes([_v("Comme Neuf", False, "79.90"), _v("Endommagé", True, "69.90")], False)
    assert r["en_stock"] is False and r["exclues"] == 1 and r["prix"] == "79.90"
    # Version neuve disponible : prix de la variante RETENUE, pas de la moins chere abimee
    r = lire_variantes([_v("Comme Neuf", True, "219.90"), _v("Endommagé", True, "199.90")], False)
    assert r["en_stock"] is True and r["prix"] == "219.90"
    # Variante de langue etrangere ignoree (option1)
    r = lire_variantes([_v("Default", True, option1="Anglais")], False)
    assert r["en_stock"] is False
    # Cas simple + prix en centimes (.js)
    r = lire_variantes([_v("Default Title", True, 15990, barcode="0820650557446")], True)
    assert r["en_stock"] is True and r["prix"] == "159.90" and r["ean"] == "0820650557446"
    # Plusieurs variantes disponibles : la moins chere retenue
    r = lire_variantes([_v("x6", True, "50"), _v("x12", True, "30")], False)
    assert r["prix"] == "30.00"
    # Rupture totale : prix indicatif conserve, jamais en stock
    r = lire_variantes([_v("Default Title", False, "59.90")], False)
    assert r["en_stock"] is False and r["prix"] == "59.90"
    # Aucune variante => inconnu (jamais presume)
    assert lire_variantes([], False)["inconnu"] is True
    # Prix absent / invalide
    assert lire_variantes([_v("D", True, "abc")], False)["prix"] == "N/A"
    assert lire_variantes([_v("D", True, "0.00")], False)["prix"] == "N/A"


def test_choix_collections():
    cols = [
        {"handle": "jeux-de-carte-pokemon-boosters", "title": "BOOSTERS POKÉMON", "products_count": 55},
        {"handle": "coffrets-pokemon", "title": "COFFRETS POKÉMON", "products_count": 161},
        {"handle": "display-one-piece", "title": "BOOSTERS/DISPLAYS ONE PIECE", "products_count": 22},
        {"handle": "mugiwara-one-piece", "title": "Mugiwara One Piece", "products_count": 5},
        {"handle": "pokemon-2", "title": "Cartes à jouer - POKÉMON", "products_count": 583},   # generique petit
        {"handle": "cartes-a-lunite-pokemon", "title": "Cartes à l'Unité - Pokémon", "products_count": 5370},
        {"handle": "pokemon-cartes", "title": "Cartes Gradées Pokémon", "products_count": 1100},
        {"handle": "pokemon-gros", "title": "Produits Pokémon", "products_count": 2000},       # trop gros
        {"handle": "peluches-pokemon", "title": "Peluches Pokémon", "products_count": 32},
        {"handle": "deck-box-pokemon", "title": "Deck Box Pokémon", "products_count": 7},
        {"handle": "pokemon-japonais", "title": "Pokémon Japonais", "products_count": 136},
        {"handle": "magic", "title": "Cartes à jouer - MAGIC", "products_count": 377},
        {"handle": "vide-pokemon-coffrets", "title": "Coffrets Pokémon", "products_count": 0},
    ]
    # products_count n'est jamais utilise pour dimensionner (il est inexact) : la collection
    # generique "Produits Pokemon" est lue aussi ; seules les collections vides/exclues sautent.
    assert choisir_collections(cols) == ["jeux-de-carte-pokemon-boosters", "coffrets-pokemon",
                                         "display-one-piece", "mugiwara-one-piece", "pokemon-2",
                                         "pokemon-gros"]


# ------------------------------------------------------------------ Shopify lot
def _art(handle, titre, variantes, type_="Pokémon"):
    return {"id": hash(handle) % 10**6, "handle": handle, "title": titre, "product_type": type_,
            "vendor": "Boutique", "images": [{"src": "https://cdn/x.png"}], "variants": variantes}


CATALOGUE = {
    "collections": [
        {"handle": "coffrets-pokemon", "title": "COFFRETS POKÉMON", "products_count": 4},
        {"handle": "display-one-piece", "title": "DISPLAYS ONE PIECE", "products_count": 2},
        {"handle": "cartes-a-lunite-pokemon", "title": "Cartes à l'unité - Pokémon", "products_count": 900},
    ],
    "coffrets-pokemon": [
        _art("etb", "Pokémon - Coffret Dresseur d'Élite ME05", [_v("Default Title", True, "59.90", barcode="0820650557446")]),
        _art("display", "Pokémon - Display de 36 Boosters ME04", [_v("Default Title", False, "239.90")]),
        _art("etb-abime", "Pokémon - ETB Coffret Dresseur d'Élite ME04",
             [_v("Comme Neuf", False, "79.90"), _v("Endommagé", True, "69.90")]),
        _art("carte", "Mesmérella (WHT 042/086) - Flamme Blanche", [_v("D", True)], "Cartes à l'Unité"),
    ],
    "display-one-piece": [
        _art("op-display", "One Piece - Display OP13", [_v("Default Title", True, "99.90")], "One Piece"),
        _art("sans-variante", "One Piece - Booster OP14", []),
    ],
}


def _faux_http(appels, panne=None):
    async def faux(url, timeout_ms=0, headers=None):
        appels.append(url)
        if panne:
            return None, panne, "http_" + panne
        if "collections.json" in url:
            return {"collections": CATALOGUE["collections"]}, "ok", None
        for h, prods in ((k, v) for k, v in CATALOGUE.items() if k != "collections"):
            if f"/collections/{h}/products.json" in url:
                return {"products": prods}, "ok", None
        if url.endswith("/products/introuvable.js"):
            return None, "not_found", "http_404"
        if ".js" in url:
            h = url.rsplit("/", 1)[1][:-3]
            for prods in (v for k, v in CATALOGUE.items() if k != "collections"):
                for p in prods:
                    if p["handle"] == h:
                        q = dict(p, variants=[dict(v, price=int(float(v["price"]) * 100))
                                              for v in p["variants"]])
                        return q, "ok", None
        return None, "not_found", "http_404"
    return faux


def test_shopify_lot():
    appels = []
    reel = shop.http_get_json
    shop.http_get_json = _faux_http(appels)
    try:
        sc = ShopifyScraper("Boutique", "x.fr", None, catalogue_complet=True)
        base = "https://www.x.fr/products/"
        urls = [base + h for h in ("etb", "display", "etb-abime", "op-display", "sans-variante",
                                    "hors-collection")]
        lot = asyncio.run(sc.scraper_lot(urls))
        # 1 (collections.json) + 2 collections retenues (cartes a l'unite exclues) = 3 requetes
        assert len(appels) == 3, appels
        assert lot[base + "etb"]["en_stock"] is True and lot[base + "etb"]["prix"] == "59.90"
        assert lot[base + "etb"]["ean"] == "0820650557446" and lot[base + "etb"]["stock_quantity"] is None
        assert lot[base + "display"]["en_stock"] is False and lot[base + "display"]["prix"] == "239.90"
        # seule la variante endommagee est dispo => rupture
        assert lot[base + "etb-abime"]["en_stock"] is False
        assert lot[base + "op-display"]["en_stock"] is True
        # sans variante ou hors collections => relu individuellement, jamais devine
        assert lot[base + "sans-variante"]["status"] == "a_verifier"
        assert lot[base + "hors-collection"]["status"] == "a_verifier"

        # Collections mises en cache (6 h) : 2e lot = 2 requetes seulement
        appels.clear()
        asyncio.run(sc.scraper_lot(urls[:2]))
        assert len(appels) == 2

        # Decouverte par collections : scelle seulement, ruptures incluses, sans variante ecarte
        appels.clear()
        prods = asyncio.run(sc.scraper_recherche())
        titres = {p["url"].rsplit("/", 1)[1]: p for p in prods}
        assert set(titres) == {"etb", "display", "etb-abime", "op-display"}   # ni carte seule
        assert titres["display"]["en_stock"] is False and titres["display"]["prix"] == "239.90"
        assert titres["etb-abime"]["en_stock"] is False
        # Fiche individuelle (.js, centimes) coherente avec le lot
        indiv = asyncio.run(sc.scraper_produit(base + "etb-abime"))
        assert indiv["status"] == "ok" and indiv["en_stock"] is False and indiv["prix"] == "79.90"
        assert asyncio.run(sc.scraper_produit(base + "introuvable"))["status"] == "not_found"
    finally:
        shop.http_get_json = reel

    # Boutique bloquee : tous les produits recoivent l'erreur (aucune requete individuelle inutile)
    reel = shop.http_get_json
    shop.http_get_json = _faux_http([], panne="blocked")
    try:
        sc = ShopifyScraper("B", "x.fr", None)
        lot = asyncio.run(sc.scraper_lot(["https://www.x.fr/products/a", "https://www.x.fr/products/b"]))
        assert {r["status"] for r in lot.values()} == {"blocked"}
    finally:
        shop.http_get_json = reel

    # Collections indisponibles (404) => lot vide (le moteur relit tout individuellement)
    reel = shop.http_get_json
    shop.http_get_json = _faux_http([], panne="not_found")
    try:
        sc = ShopifyScraper("B", "x.fr", None, catalogue_complet=True)
        assert asyncio.run(sc.scraper_lot(["https://www.x.fr/products/a"])) == {}
    finally:
        shop.http_get_json = reel


# ------------------------------------------------------------------ WooCommerce lot
def _wp(slug, nom, stock=True, achetable=True, prix="5499", type_="simple", restant=None):
    return {"slug": slug, "name": nom, "permalink": f"https://www.w.fr/produit/{slug}/",
            "is_in_stock": stock, "is_purchasable": achetable, "type": type_, "images": [],
            "low_stock_remaining": restant, "sku": "S" + slug,
            "prices": {"price": prix, "currency_minor_unit": 2}}


def test_woo_lot():
    liste = [_wp("etb", "Pokémon ETB", restant=4), _wp("rupture", "Pokémon Display", stock=False),
             _wp("zero", "Pokémon Deck", achetable=False, prix="0"),
             _wp("variable", "Pokémon Pack", type_="variable")]
    hors_liste = {"hors": _wp("hors", "One Piece Display", prix="9990")}
    appels = []

    async def faux(url, timeout_ms=0, headers=None):
        appels.append(url)
        if "search=" in url:
            return (liste if "page=1" in url and "pokemon" in url else []), "ok", None
        if "slug=" in url:
            demandes = url.split("slug=")[1].split("&")[0].replace("%2C", ",").split(",")
            return [hors_liste[s] for s in demandes if s in hors_liste], "ok", None
        return None, "not_found", "x"

    reel = woo.http_get_json
    woo.http_get_json = faux
    try:
        sc = WooCommerceScraper("Boutique", "w.fr", None)
        base = "https://www.w.fr/produit/"
        urls = [base + s + "/" for s in ("etb", "rupture", "zero", "variable", "hors", "disparu")]
        lot = asyncio.run(sc.scraper_lot(urls))
        assert lot[base + "etb/"]["en_stock"] is True and lot[base + "etb/"]["prix"] == "54.99"
        assert lot[base + "etb/"]["stock_quantity"] == 4          # donnee reelle, pas inventee
        assert lot[base + "rupture/"]["en_stock"] is False
        assert lot[base + "zero/"]["en_stock"] is False and lot[base + "zero/"]["prix"] == "N/A"
        assert lot[base + "variable/"]["status"] == "inconnu"      # stock par declinaison indeterminable
        assert lot[base + "hors/"]["en_stock"] is True and lot[base + "hors/"]["prix"] == "99.90"
        assert lot[base + "disparu/"]["status"] == "not_found"
        # 2 termes x 1 page + 1 requete groupee pour les 2 produits hors liste (pas 1 par produit)
        assert len(appels) == 3, appels
        # decouverte: produits variables ecartes
        prods = asyncio.run(sc.scraper_recherche())
        assert "variable" not in " ".join(p["url"] for p in prods)
    finally:
        woo.http_get_json = reel

    reel = woo.http_get_json

    async def bloque(url, timeout_ms=0, headers=None):
        return None, "blocked", "http_403"
    woo.http_get_json = bloque
    try:
        lot = asyncio.run(WooCommerceScraper("B", "w.fr", None).scraper_lot(["https://www.w.fr/p/a/"]))
        assert lot["https://www.w.fr/p/a/"]["status"] == "blocked"
    finally:
        woo.http_get_json = reel


# ------------------------------------------------------------------ moteur : lot + disparus
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
    titre = "Pokémon - Coffret Dresseur d'Élite ME05"
    for u in ("https://s/p/a", "https://s/p/b", "https://s/p/c"):
        await database.ajouter_produit(u, titre, "Boutique", False, prix="50")

    class Scraper:
        _last_status = "ok"
        n_indiv = 0
        lot_a_fournir = {}

        async def scraper_lot(self, urls):
            return {u: self.lot_a_fournir[u] for u in urls if u in self.lot_a_fournir}

        async def scraper_produit(self, url):
            Scraper.n_indiv += 1
            return {"status": "ok", "en_stock": False, "prix": "50", "image_url": "", "brand": "Pokémon"}

    ok = lambda stock, prix="50": {"status": "ok", "en_stock": stock, "prix": prix,
                                   "image_url": "", "brand": "Pokémon"}
    sc = Scraper()
    sc.lot_a_fournir = {"https://s/p/a": ok(True), "https://s/p/b": ok(False),
                        "https://s/p/c": {"status": "a_verifier"}}
    config.WATCHLIST_LOT = True
    rap = await main.cycle_watchlist({"Boutique": sc}, 1)
    assert Scraper.n_indiv == 1                      # seul le produit non tranche est relu
    assert rap.stores[0].lus_en_lot == 2 and rap.stores[0].restocks == 1
    assert [a[1] for a in alertes] == ["RESTOCK"]

    # Lot desactive => lecture individuelle de tout (reglage existant preserve)
    Scraper.n_indiv = 0
    config.WATCHLIST_LOT = False
    await main.cycle_watchlist({"Boutique": sc}, 2)
    assert Scraper.n_indiv == 3
    config.WATCHLIST_LOT = True

    # --- Produits disparus : un 404 isole ne suffit pas ---
    class Absent(Scraper):
        async def scraper_lot(self, urls):
            return {u: {"status": "not_found"} for u in urls}
    config.DISPARU_MIN_ECHECS = 3
    config.DISPARU_APRES_HEURES = 1
    ab = Absent()
    for i in range(5):                                # 5 constats mais trop recents (< 1 h)
        await main.cycle_watchlist({"Boutique": ab}, 10 + i)
    ligne = await database.recuperer_produit("https://s/p/a")
    assert ligne["introuvables"] == 5 and ligne["prochaine_verif"] == 0     # PAS disparu
    assert ligne["en_stock"] == 1                      # etat inchange, aucune fausse rupture
    # Absence continue depuis > 1 h : disparu => relecture espacee, MAIS etat de stock intact
    # (disparaitre n'est pas une rupture constatee)
    db = await database._conn()
    await db.execute("UPDATE produits SET introuvable_depuis = ?", (time.time() - 2 * 3600,))
    await db.commit()
    await main.cycle_watchlist({"Boutique": ab}, 20)
    ligne = await database.recuperer_produit("https://s/p/a")
    assert ligne["en_stock"] == 1 and ligne["prochaine_verif"] > time.time() + 3600
    assert ligne["disparu_depuis"] > 0
    # ... et il n'est plus relu a chaque cycle
    appels = []

    class Compte(Scraper):
        async def scraper_lot(self, urls):
            appels.append(list(urls))
            return {u: ok(False) for u in urls}
    await main.cycle_watchlist({"Boutique": Compte()}, 21)
    assert appels == []                                # tous les produits sont en attente

    # --- Retour apres disparition COURTE (2 h) ---
    config.ALERT_DEDUP_WINDOW = 0
    await db.execute("UPDATE produits SET prochaine_verif = ?", (time.time() - 10,))
    await db.commit()
    alertes.clear()
    sc.lot_a_fournir = {u: ok(True) for u in ("https://s/p/a", "https://s/p/b", "https://s/p/c")}
    await main.cycle_watchlist({"Boutique": sc}, 22)
    # a etait EN STOCK avant de disparaitre : pas de faux restock (trou technique de 2 h)
    # b et c etaient en RUPTURE avant : leur retour en stock est une vraie transition
    assert sorted(a[2] for a in alertes) == ["https://s/p/b", "https://s/p/c"], alertes
    ligne = await database.recuperer_produit("https://s/p/a")
    assert ligne["introuvables"] == 0 and ligne["prochaine_verif"] == 0 and ligne["en_stock"] == 1

    # --- Retour apres disparition LONGUE (30 h) d'un produit qui etait en stock : alerte ---
    await db.execute("UPDATE produits SET introuvables = 6, introuvable_depuis = ?, "
                     "disparu_depuis = ?, prochaine_verif = ? WHERE url = 'https://s/p/a'",
                     (time.time() - 30 * 3600, time.time() - 20 * 3600, time.time() - 10))
    await db.commit()
    alertes.clear()
    await main.cycle_watchlist({"Boutique": sc}, 23)
    assert [(a[1], a[2]) for a in alertes] == [("RESTOCK", "https://s/p/a")], alertes

    # --- Retour en RUPTURE : jamais d'alerte ---
    await db.execute("UPDATE produits SET introuvables = 6, introuvable_depuis = ?, "
                     "prochaine_verif = ?, en_stock = 1 WHERE url = 'https://s/p/b'",
                     (time.time() - 30 * 3600, time.time() - 10))
    await db.commit()
    alertes.clear()
    sc.lot_a_fournir = {u: ok(False) for u in sc.lot_a_fournir}
    await main.cycle_watchlist({"Boutique": sc}, 24)
    assert alertes == []

    # --- Historique de prix sans doublons ---
    h0 = len(await database.recuperer_historique_prix("https://s/p/a"))
    for _ in range(5):
        await database.enregistrer_prix("https://s/p/a", 50.0, True)
    h1 = len(await database.recuperer_historique_prix("https://s/p/a"))
    assert h1 - h0 <= 1                                # identique => au plus un point
    await database.enregistrer_prix("https://s/p/a", 45.0, True)
    assert len(await database.recuperer_historique_prix("https://s/p/a")) == h1 + 1

    await database.fermer()
    os.remove(chemin)


def test_moteur():
    asyncio.run(_moteur())


def test():
    test_variantes()
    test_choix_collections()
    test_shopify_lot()
    test_woo_lot()
    test_moteur()


if __name__ == "__main__":
    test()
    print("OK")
