"""C8C : fiabilite de la decouverte et des alertes Shopify / WooCommerce."""
import asyncio
import os
import sqlite3
import sys
import tempfile
import time
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config
import database
import main
import discord_bot as bot
import scrapers.shopify as shop
import scrapers.woocommerce as woo
from filter_utils import est_tcg_valide_local
from scrapers.registry import construire_tous
from scrapers.shopify import ShopifyScraper
from scrapers.woocommerce import WooCommerceScraper


# ------------------------------------------------------------------ 1. etat degrade
def test_titres_degrades():
    ok = est_tcg_valide_local
    assert not ok("[ENDOMMAGÉ] Pokémon - Coffret Dresseur d'Élite (ETB) ME05")
    assert not ok("Pokémon Display ME04 - boîte abîmée")
    assert not ok("Coffret Dresseur d'Élite Pokémon EV05 d'occasion")
    assert not ok("Elite Trainer Box Pokémon - damaged box")
    assert not ok("Pokémon ETB reconditionné")
    # Le neuf reste valide (y compris la variante "Comme Neuf" dans un titre)
    assert ok("Pokémon - ETB Coffret Dresseur d'Élite ME04 Chaos Ascendant")
    assert ok("Pokémon - Display de 36 Boosters ME03 - Comme Neuf")
    assert ok("One Piece Card Game - Display OP13")


# ------------------------------------------------------------------ 2. decouverte verifiee
def _suggest(handle, titre, dispo, prix="50.00", vendor="Boutique"):
    return {"handle": handle, "title": titre, "available": dispo, "price": prix,
            "vendor": vendor, "variants": []}      # `variants` toujours vide en recherche


def _fiche_js(variantes):
    return {"id": 1, "title": "x", "vendor": "Boutique", "images": ["https://cdn/x.png"],
            "variants": variantes}


def _v(titre, dispo, cents):
    return {"title": titre, "available": dispo, "price": cents}


def test_decouverte_verifiee():
    suggest = [
        _suggest("seulement-abime", "Pokémon - ETB Coffret Dresseur d'Élite ME04", True, "69.90"),
        _suggest("neuf-dispo", "Pokémon - ETB Coffret Dresseur d'Élite ME05", True, "89.90"),
        _suggest("epuise", "Pokémon - Display de 36 Boosters ME04", False, "199.90"),
        _suggest("fiche-bloquee", "Pokémon - Coffret Premium ME03", True, "49.90"),
        _suggest("mug", "Mug Pikachu", True, "9.90"),
    ]
    fiches = {
        "seulement-abime": _fiche_js([_v("Comme Neuf", False, 7990), _v("Endommagé", True, 6990)]),
        "neuf-dispo": _fiche_js([_v("Default Title", True, 8990)]),
    }
    appels = []

    async def faux(url, timeout_ms=0, headers=None):
        appels.append(url)
        if "collections.json" in url:
            return None, "not_found", "http_404"        # pas de collections => recherche
        if "suggest.json" in url:
            return {"resources": {"results": {"products": suggest}}}, "ok", None
        h = url.rsplit("/", 1)[1][:-3]
        if h in fiches:
            return fiches[h], "ok", None
        return None, "blocked", "http_403"

    reel, kw = shop.http_get_json, list(config.SEARCH_KEYWORDS)
    shop.http_get_json = faux
    config.SEARCH_KEYWORDS = ["pokemon coffret"]
    try:
        sc = ShopifyScraper("Boutique", "x.fr", None, catalogue_complet=True)
        prods = {p["url"].rsplit("/", 1)[1]: p for p in asyncio.run(sc.scraper_recherche())}
    finally:
        shop.http_get_json, config.SEARCH_KEYWORDS = reel, kw
    assert sc.mode_decouverte == "suggest"
    # Seule la version ENDOMMAGEE est en stock => PAS annonce disponible, prix de la variante neuve
    assert prods["seulement-abime"]["en_stock"] is False
    assert prods["seulement-abime"]["prix"] == "79.90"
    assert prods["neuf-dispo"]["en_stock"] is True and prods["neuf-dispo"]["prix"] == "89.90"
    # Epuise : indisponible fiable ; prix non verifiable par variante => N/A ; aucune fiche lue
    assert prods["epuise"]["en_stock"] is False and prods["epuise"]["prix"] == "N/A"
    assert not any("epuise.js" in u for u in appels)
    # Disponibilite non verifiable (fiche bloquee) => produit ECARTE, jamais annonce
    assert "fiche-bloquee" not in prods
    # Hors JCC : passe tel quel (le moteur l'ecartera), sans requete
    assert "mug" in prods and not any("mug.js" in u for u in appels)


def test_plafond_verification():
    """Au-dela du plafond, les produits sont ecartes (precision > quantite), pas annonces."""
    import scrapers.shopify as sh
    suggest = [_suggest(f"p{i}", f"Pokémon - Display ME05 n{i}", True) for i in range(6)]

    async def faux(url, timeout_ms=0, headers=None):
        if "suggest.json" in url:
            return {"resources": {"results": {"products": suggest}}}, "ok", None
        if "collections.json" in url:
            return None, "not_found", "x"
        return _fiche_js([_v("Default Title", True, 5000)]), "ok", None
    reel, plafond, kw = shop.http_get_json, sh._VERIF_DECOUVERTE_MAX, list(config.SEARCH_KEYWORDS)
    shop.http_get_json, sh._VERIF_DECOUVERTE_MAX = faux, 4
    config.SEARCH_KEYWORDS = ["pokemon"]
    try:
        prods = asyncio.run(ShopifyScraper("B", "x.fr", None).scraper_recherche())
    finally:
        shop.http_get_json, sh._VERIF_DECOUVERTE_MAX, config.SEARCH_KEYWORDS = reel, plafond, kw
    assert len(prods) == 4 and all(p["en_stock"] for p in prods)
    assert plafond >= 100        # assez haut pour une boutique TCG complete en mode repli


# ------------------------------------------------------------------ 3. coherence des 3 chemins
def test_coherence_shopify():
    cas = {
        "ok": [("Default Title", True, "59.90")],
        "rupture": [("Default Title", False, "59.90")],
        "variante-secondaire": [("Comme Neuf", False, "79.90"), ("Endommagé", True, "69.90")],
        "deux-dispo": [("x6", True, "50.00"), ("x12", True, "30.00")],
        "langue-secondaire": [("Default Title", True, "20.00")],
    }
    # variante de langue : option1
    def art(h, vs):
        variantes = [{"title": t, "available": d, "price": p,
                      "option1": "Anglais" if h == "langue-secondaire" else None} for t, d, p in vs]
        return {"id": 1, "handle": h, "title": f"Pokémon - Display ME05 {h}", "product_type": "Pokémon",
                "vendor": "Boutique", "images": [{"src": "https://cdn/x.png"}], "variants": variantes}
    arts = {h: art(h, v) for h, v in cas.items()}

    async def faux(url, timeout_ms=0, headers=None):
        if "collections.json" in url:
            return {"collections": [{"handle": "pokemon-coffrets", "title": "Coffrets Pokémon",
                                     "products_count": 5}]}, "ok", None
        if "/collections/pokemon-coffrets/products.json" in url:
            return {"products": list(arts.values())}, "ok", None
        if "suggest.json" in url:
            return {"resources": {"results": {"products": [
                _suggest(h, a["title"], any(v["available"] for v in a["variants"]),
                         min(v["price"] for v in a["variants"])) for h, a in arts.items()]}}}, "ok", None
        if ".js" in url:
            a = arts[url.rsplit("/", 1)[1][:-3]]
            return dict(a, variants=[dict(v, price=int(float(v["price"]) * 100))
                                     for v in a["variants"]]), "ok", None
        return None, "not_found", "x"

    reel = shop.http_get_json
    shop.http_get_json = faux
    kw = list(config.SEARCH_KEYWORDS)
    config.SEARCH_KEYWORDS = ["pokemon"]
    try:
        urls = [f"https://www.x.fr/products/{h}" for h in cas]
        sc = ShopifyScraper("B", "x.fr", None, catalogue_complet=True)
        decouverte = {p["url"]: p for p in asyncio.run(sc.scraper_recherche())}   # collections
        lot = asyncio.run(sc.scraper_lot(urls))
        indiv = {u: asyncio.run(sc.scraper_produit(u)) for u in urls}
        sug = ShopifyScraper("B", "x.fr", None, catalogue_complet=False)
        sug._collections = (time.time(), [])
        recherche = {p["url"]: p for p in asyncio.run(sug.scraper_recherche())}   # suggest verifie
    finally:
        shop.http_get_json, config.SEARCH_KEYWORDS = reel, kw
    for u in urls:
        triplet = {(decouverte[u]["en_stock"], decouverte[u]["prix"]),
                   (lot[u]["en_stock"], lot[u]["prix"]),
                   (indiv[u]["en_stock"], indiv[u]["prix"])}
        assert len(triplet) == 1, (u, triplet)                         # catalogue = lot = fiche
        if recherche[u]["en_stock"]:                                   # recherche verifiee
            assert (recherche[u]["en_stock"], recherche[u]["prix"]) in triplet, u
        else:
            assert not lot[u]["en_stock"], u
    assert lot[urls[0]]["en_stock"] is True and lot[urls[2]]["en_stock"] is False
    assert lot[urls[3]]["prix"] == "30.00" and lot[urls[4]]["en_stock"] is False


def test_coherence_woo():
    def wp(slug, **kw):
        base = {"slug": slug, "name": f"Pokémon {slug}", "permalink": f"https://www.w.fr/p/{slug}/",
                "is_in_stock": True, "is_purchasable": True, "type": "simple", "images": [],
                "prices": {"price": "2499", "currency_minor_unit": 2}}
        base.update(kw)
        return base
    items = [wp("ok"), wp("rupture", is_in_stock=False), wp("zero", is_purchasable=False,
             prices={"price": "0", "currency_minor_unit": 2}), wp("prix0",
             prices={"price": "0", "currency_minor_unit": 2})]

    async def faux(url, timeout_ms=0, headers=None):
        if "search=" in url:
            return (items if "pokemon" in url and "page=1" in url else []), "ok", None
        slug = url.split("slug=")[1].split("&")[0]
        return [i for i in items if i["slug"] == slug], "ok", None
    reel = woo.http_get_json
    woo.http_get_json = faux
    try:
        sc = WooCommerceScraper("B", "w.fr", None)
        urls = [i["permalink"] for i in items]
        decouverte = {p["url"]: p for p in asyncio.run(sc.scraper_recherche())}
        lot = asyncio.run(sc.scraper_lot(urls))
        indiv = {u: asyncio.run(sc.scraper_produit(u)) for u in urls}
    finally:
        woo.http_get_json = reel
    for u in urls:
        a = (decouverte[u]["en_stock"], decouverte[u]["prix"])
        assert a == (lot[u]["en_stock"], lot[u]["prix"]) == (indiv[u]["en_stock"], indiv[u]["prix"]), u
    assert lot[urls[0]]["en_stock"] is True
    assert not any(lot[u]["en_stock"] for u in urls[1:])


# ------------------------------------------------------------------ 4. adoption silencieuse
class Faux:
    """Scraper de decouverte controlable."""
    CONCURRENCE_WATCHLIST = 5

    def __init__(self, mode, produits):
        self.mode_decouverte = mode
        self.produits = produits
        self._last_status = "ok"

    async def scraper_recherche(self):
        return self.produits


def _p(nom, stock=True):
    return {"url": f"https://www.x.fr/products/{nom}", "titre": f"Pokémon - Display ME05 {nom}",
            "prix": "100.00", "image_url": "", "en_stock": stock, "brand": "Pokémon"}


async def _adoption():
    config.ENABLE_PRICE_CHART = False
    fd, chemin = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()
    alertes = []

    async def fake(prod, ens, t, chart_png=None):
        alertes.append((t, prod["url"].rsplit("/", 1)[1]))
        return True
    main.envoyer_alerte = fake
    main._sante = main.StoreHealth(seuil=99, pause_s=1)
    E = "LudiJeux"

    # Installation EXISTANTE : la boutique est deja suivie via la recherche (pas de marqueur)
    for nom in ("a", "b"):
        await database.ajouter_produit(f"https://www.x.fr/products/{nom}", f"Pokémon - Display ME05 {nom}",
                                       E, True, prix="100.00")
    assert await database.lire_meta(f"decouverte:{E}") is None

    # Passage aux collections : 300 produits "nouveaux" deja en rayon => AUCUNE alerte
    massif = [_p(f"p{i}") for i in range(300)] + [_p("a"), _p("b")]
    await main.cycle_recherche({E: Faux("collections", massif)}, 1)
    assert alertes == [], alertes[:3]
    assert len(await database.recuperer_tous_produits()) == 302
    assert await database.lire_meta(f"decouverte:{E}") == "collections"

    # Apres l'adoption : une VRAIE nouveaute en stock est annoncee, une en rupture non
    await main.cycle_recherche({E: Faux("collections", massif + [_p("nouveau"), _p("nouveau-rupture", False)])}, 2)
    assert alertes == [("NOUVEAUTE", "nouveau")], alertes

    # Repli temporaire sur la recherche : pas de silence artificiel, marqueur NON retrograde
    alertes.clear()
    await main.cycle_recherche({E: Faux("suggest", [_p("hors-collections")])}, 3)
    assert alertes == [("NOUVEAUTE", "hors-collections")]
    assert await database.lire_meta(f"decouverte:{E}") == "collections"
    # ... et le retour aux collections n'est pas un nouvel amorçage
    alertes.clear()
    await main.cycle_recherche({E: Faux("collections", massif + [_p("autre")])}, 4)
    assert alertes == [("NOUVEAUTE", "autre")]

    # Restock apres amorçage: toujours detecte par la watchlist
    class Wl(Faux):
        async def scraper_produit(self, url):
            return {"status": "ok", "en_stock": True, "prix": "100.00", "image_url": "", "brand": "Pokémon"}
    await database.mettre_a_jour_stock("https://www.x.fr/products/p1", False)
    alertes.clear()
    await main.cycle_watchlist({E: Wl("collections", [])}, 5)
    assert ("RESTOCK", "p1") in alertes

    # Cycle vide (boutique en panne) : le marqueur n'est pas ecrit, l'adoption reste a faire
    F = "Autre"
    await database.ajouter_produit("https://www.y.fr/products/z", "Pokémon - Display ME05 z", F, True)
    await main.cycle_recherche({F: Faux("collections", [])}, 6)
    assert await database.lire_meta(f"decouverte:{F}") is None
    alertes.clear()
    await main.cycle_recherche({F: Faux("collections", [_p("n1"), _p("n2")])}, 7)
    assert alertes == []                                   # adoption (silencieuse) enfin faite
    assert await database.lire_meta(f"decouverte:{F}") == "collections"

    # Boutique en mode recherche, deja connue, sans marqueur : comportement INCHANGE (alerte)
    G = "Troisieme"
    await database.ajouter_produit("https://www.z.fr/products/q", "Pokémon - Display ME05 q", G, True)
    alertes.clear()
    await main.cycle_recherche({G: Faux("suggest", [_p("neuf")])}, 8)
    assert alertes == [("NOUVEAUTE", "neuf")]
    assert await database.lire_meta(f"decouverte:{G}") == "suggest"

    # Enseigne sans notion de mode (None) : aucun marqueur, comportement historique
    H = "Quatrieme"
    await database.ajouter_produit("https://www.h.fr/products/q", "Pokémon - Display ME05 q", H, True)
    alertes.clear()
    await main.cycle_recherche({H: Faux(None, [_p("h1")])}, 9)
    assert alertes == [("NOUVEAUTE", "h1")] and await database.lire_meta(f"decouverte:{H}") is None

    await database.fermer()
    os.remove(chemin)


def test_adoption():
    asyncio.run(_adoption())


# ------------------------------------------------------------------ 5. compatibilite donnees / reglages
def test_migration_ancienne_base():
    fd, chemin = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(chemin)
    # Schema d'origine (avant manuel, introuvables, prochaine_verif, disparu_depuis, meta)
    c.execute("""CREATE TABLE produits (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE NOT NULL,
        titre TEXT NOT NULL, enseigne TEXT NOT NULL, en_stock INTEGER NOT NULL, prix TEXT DEFAULT 'N/A',
        image_url TEXT DEFAULT '', derniere_alerte REAL DEFAULT 0, dernier_vu REAL NOT NULL,
        date_decouverte REAL NOT NULL)""")
    c.execute("""CREATE TABLE price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL,
        prix_value REAL NOT NULL, en_stock INTEGER NOT NULL, timestamp REAL NOT NULL)""")
    c.execute("INSERT INTO produits (url,titre,enseigne,en_stock,prix,image_url,derniere_alerte,dernier_vu,"
              "date_decouverte) VALUES ('https://a/p','Pokémon Display ME05','LudiJeux',1,'89.90','i.png',123.0,5,4)")
    for i, p in enumerate((99.9, 89.9)):
        c.execute("INSERT INTO price_history (url,prix_value,en_stock,timestamp) VALUES ('https://a/p',?,1,?)",
                  (p, 1000 + i))
    c.commit()
    c.close()

    async def go():
        database.DB_PATH = chemin
        await database.initialiser_db()
        await database.initialiser_db()                    # idempotent
        row = await database.recuperer_produit("https://a/p")
        assert row["titre"] == "Pokémon Display ME05" and row["prix"] == "89.90"
        assert row["image_url"] == "i.png" and row["derniere_alerte"] == 123.0 and row["en_stock"] == 1
        assert row["manuel"] == 0 and row["introuvables"] == 0 and row["prochaine_verif"] == 0
        assert row["disparu_depuis"] == 0
        hist = await database.recuperer_historique_prix("https://a/p")
        assert [h["prix_value"] for h in hist] == [99.9, 89.9]
        assert await database.lire_meta("x") is None
        await database.ecrire_meta("x", "1")
        await database.ecrire_meta("x", "2")
        assert await database.lire_meta("x") == "2"
        # Le moteur lit la ligne migree sans erreur
        main.envoyer_alerte = lambda *a, **k: asyncio.sleep(0)
        main._sante = main.StoreHealth(seuil=99, pause_s=1)

        class S:
            _last_status = "ok"
            CONCURRENCE_WATCHLIST = 5

            async def scraper_produit(self, url):
                return {"status": "ok", "en_stock": True, "prix": "89.90", "image_url": "", "brand": "Pokémon"}
        rap = await main.cycle_watchlist({"LudiJeux": S()}, 1)
        assert rap.stores[0].statut == "healthy"
        await database.fermer()
    asyncio.run(go())
    for ext in ("", "-wal", "-shm"):
        try:
            os.remove(chemin + ext)
        except OSError:
            pass


def test_reglages_et_registre():
    # Defaut : decouverte par collections pour toutes les boutiques Shopify (adoption protegee)
    tous = construire_tous(None)
    shopify = [s for s in tous.values() if isinstance(s, ShopifyScraper)]
    assert shopify and all(s.catalogue_complet for s in shopify) == ("*" in config.SHOPIFY_CATALOGUE_COMPLET)
    ancien = config.SHOPIFY_CATALOGUE_COMPLET
    try:
        config.SHOPIFY_CATALOGUE_COMPLET = {"Dracaugames"}                 # ancien reglage
        t = construire_tous(None)
        assert t["Dracaugames"].catalogue_complet and not t["LudiJeux"].catalogue_complet
        config.SHOPIFY_CATALOGUE_COMPLET = set()                           # opt-out
        assert not any(s.catalogue_complet for s in construire_tous(None).values()
                       if isinstance(s, ShopifyScraper))
    finally:
        config.SHOPIFY_CATALOGUE_COMPLET = ancien
    # Affichage des disparus
    assert bot.symbole_stock({"en_stock": 1, "prochaine_verif": 0}) == "🟢"
    assert bot.symbole_stock({"en_stock": 0}) == "🔴"
    assert bot.symbole_stock({"en_stock": 1, "prochaine_verif": 123.0}) == "⚫"


def test():
    test_titres_degrades()
    test_decouverte_verifiee()
    test_plafond_verification()
    test_coherence_shopify()
    test_coherence_woo()
    test_adoption()
    test_migration_ancienne_base()
    test_reglages_et_registre()


if __name__ == "__main__":
    test()
    print("OK")
