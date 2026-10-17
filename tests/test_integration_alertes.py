"""
C8C.1 - Tests d'INTEGRATION des alertes (boutiques SIMULEES, vrai moteur + vrais scrapers).

Une fausse boutique Shopify (collections, recherche, fiches .js) et une fausse boutique
WooCommerce evoluent dans le temps ; chaque etape verifie la liste EXACTE des alertes envoyees :
une vraie nouveaute disponible = exactement une alerte, tout le reste = aucune fausse alerte.
Aucun reseau, aucun envoi Discord.
"""
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
from scrapers.shopify import ShopifyScraper
from scrapers.woocommerce import WooCommerceScraper

E = "Boutique"


# ======================================================================= boutique Shopify simulee
class FausseShopify:
    def __init__(self):
        self.produits: dict[str, dict] = {}     # handle -> {titre, type, variantes, publie}
        self.panne: str | None = None            # "blocked" => toute la boutique bloque
        self.requetes = 0

    def ajouter(self, handle, titre, variantes, type_="Pokémon", publie=True):
        self.produits[handle] = {"titre": titre, "type": type_, "publie": publie,
                                 "variantes": [list(v) for v in variantes]}

    def stock(self, handle, dispo, variante=0):
        self.produits[handle]["variantes"][variante][1] = dispo

    def _json(self, h, centimes):
        p = self.produits[h]
        return {"id": abs(hash(h)) % 10**6, "handle": h, "title": p["titre"], "product_type": p["type"],
                "vendor": "Boutique", "images": [{"src": "https://cdn/x.png"}],
                "variants": [{"title": t, "available": d, "price": int(float(pr) * 100) if centimes else pr}
                             for t, d, pr in p["variantes"]]}

    async def http(self, url, timeout_ms=0, headers=None):
        self.requetes += 1
        if self.panne:
            return None, self.panne, "http_403"
        publies = {h: p for h, p in self.produits.items() if p["publie"]}
        if "/collections.json" in url:
            return {"collections": [{"handle": "pokemon", "title": "Produits Pokémon",
                                     "products_count": len(publies)}]}, "ok", None
        if "/collections/pokemon/products.json" in url:
            return {"products": [self._json(h, False) for h in publies]}, "ok", None
        if "suggest.json" in url:
            return {"resources": {"results": {"products": [
                {"handle": h, "title": p["titre"], "available": any(v[1] for v in p["variantes"]),
                 "price": min(v[2] for v in p["variantes"]), "vendor": "Boutique", "variants": []}
                for h, p in publies.items()]}}}, "ok", None
        if ".js" in url:
            h = url.rsplit("/", 1)[1][:-3]
            if h in publies:
                return self._json(h, True), "ok", None
            return None, "not_found", "http_404"
        return None, "not_found", "http_404"


def _t(nom):
    return f"Pokémon - Display de 36 Boosters ME05 {nom}"


class Banc:
    """Moteur + base temporaire + enregistreur d'alertes."""

    def __init__(self, boutique, scraper_factory, modele_url="https://www.x.fr/products/{}"):
        self.modele_url = modele_url
        self.boutique = boutique
        self.factory = scraper_factory
        self.alertes: list[tuple[str, str]] = []
        self.n = 0

    async def demarrer(self):
        config.ENABLE_PRICE_CHART = False
        config.ALERT_DEDUP_WINDOW = 600
        fd, self.chemin = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_PATH = self.chemin
        await database.initialiser_db()

        async def fake(prod, ens, t, chart_png=None):
            self.alertes.append((t, prod["url"].rstrip("/").rsplit("/", 1)[1]))
            return True
        main.envoyer_alerte = fake
        main._sante = main.StoreHealth(seuil=99, pause_s=1)
        self.scraper = self.factory()

    async def arreter(self):
        await database.fermer()
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(self.chemin + ext)
            except OSError:
                pass

    def vider(self):
        self.alertes.clear()

    async def recherche(self, scraper=None):
        self.n += 1
        return await main.cycle_recherche({E: scraper or self.scraper}, self.n)

    async def watchlist(self, scraper=None):
        self.n += 1
        return await main.cycle_watchlist({E: scraper or self.scraper}, self.n)

    async def ligne(self, handle):
        return await database.recuperer_produit(self.modele_url.format(handle))

    async def reculer(self, handle, heures):
        """Le produit est absent depuis `heures` : recule SEULEMENT le debut de l'absence
        (le moteur declarera lui-meme la disparition au prochain cycle)."""
        db = await database._conn()
        await db.execute("UPDATE produits SET introuvable_depuis = ? WHERE url = ?",
                         (time.time() - heures * 3600, self.modele_url.format(handle)))
        await db.commit()

    async def echeance(self, handle):
        """Le temps passe : la relecture espacee du produit disparu est due."""
        db = await database._conn()
        await db.execute("UPDATE produits SET prochaine_verif = ? WHERE url = ?",
                         (time.time() - 10, self.modele_url.format(handle)))
        await db.commit()

    async def disparaitre(self, handle, heures, boutique):
        """Fiche depubliee, constatee absente, declaree disparue PAR LE MOTEUR."""
        boutique.produits[handle]["publie"] = False
        for _ in range(3):
            await self.watchlist()
        await self.reculer(handle, heures)
        await self.watchlist()                                       # declaration de disparition
        ligne = await self.ligne(handle)
        assert ligne["prochaine_verif"] > time.time() + 3600 and ligne["disparu_depuis"] > 0
        n = ligne["introuvables"]
        await self.watchlist()                                       # en attente : non relu
        assert (await self.ligne(handle))["introuvables"] == n


# ======================================================================= scenario Shopify
async def _scenario_shopify():
    f = FausseShopify()
    reel = shop.http_get_json
    shop.http_get_json = f.http
    kw, dedup = list(config.SEARCH_KEYWORDS), config.ALERT_DEDUP_WINDOW
    config.SEARCH_KEYWORDS = ["pokemon"]
    config.WATCHLIST_LOT = True
    config.ALERTER_REAPPARITION = False
    config.DISPARU_MIN_ECHECS, config.DISPARU_APRES_HEURES = 3, 1
    config.REAPPARITION_ALERTE_HEURES = 24
    config.PRIX_CONFIRMATIONS = 2
    config.RUPTURE_CONFIRMATIONS = 2
    main._confirmation.seuil = 2
    banc = Banc(f, lambda: ShopifyScraper(E, "x.fr", None, catalogue_complet=False))
    try:
        await banc.demarrer()
        tout = []                                   # journal de TOUTES les alertes attendues

        # ---- installation existante en mode RECHERCHE (premiere decouverte : silencieuse)
        f.ajouter("etb", _t("etb"), [("Default Title", True, "89.90")])
        f.ajouter("pack", _t("pack"), [("Default Title", True, "49.90")])
        f.ajouter("display", _t("display"), [("Default Title", False, "199.90")])
        # La recherche annonce ce produit "disponible" alors que seule la version ENDOMMAGEE l'est
        f.ajouter("ko-initial", _t("ko-initial"), [("Comme Neuf", False, "79.90"), ("Endommagé", True, "59.90")])
        await banc.recherche()
        assert banc.alertes == [] and len(await database.recuperer_tous_produits()) == 4
        assert await database.lire_meta(f"decouverte:{E}") == "suggest"
        assert (await banc.ligne("ko-initial"))["en_stock"] == 0          # verifie sur fiche : rupture
        assert (await banc.ligne("etb"))["en_stock"] == 1

        # ---- le catalogue grossit (deja en rayon) puis ACTIVATION du catalogue complet
        for i in range(30):
            f.ajouter(f"ancien{i}", _t(f"ancien{i}"), [("Default Title", i % 2 == 0, "20.00")])
        f.ajouter("carte", "Rosélia de Cynthia (DRI 007) - Rivalités Destinées - Carte Pokémon",
                  [("Default Title", True, "0.50")], type_="Cartes à l'Unité")
        f.ajouter("carte2", "Pokémon Ninjask - Carte seule", [("Default Title", True, "0.30")],
                  type_="Cartes à l'unité")
        banc.scraper = ShopifyScraper(E, "x.fr", None, catalogue_complet=True)
        banc.vider()
        await banc.recherche()
        suivis = {p["url"].rsplit("/", 1)[1] for p in await database.recuperer_tous_produits()}
        assert banc.alertes == [], banc.alertes                    # adoption : 0 fausse nouveaute
        assert len(suivis) == 34 and "carte" not in suivis and "carte2" not in suivis
        assert await database.lire_meta(f"decouverte:{E}") == "collections"
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == []                                  # stable : rien

        # ---- VRAIE NOUVEAUTE disponible : exactement UNE alerte, meme apres plusieurs cycles
        f.ajouter("nouveau", _t("nouveau"), [("Default Title", True, "59.90")])
        await banc.recherche()
        await banc.recherche()
        await banc.watchlist()
        await banc.watchlist()
        assert banc.alertes == [("NOUVEAUTE", "nouveau")], banc.alertes
        tout += banc.alertes
        banc.vider()

        # ---- nouveaute EN RUPTURE : aucune alerte ; puis disponible : exactement un RESTOCK
        f.ajouter("bientot", _t("bientot"), [("Default Title", False, "79.90")])
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == []
        f.stock("bientot", True)
        await banc.watchlist()
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "bientot")], banc.alertes
        tout += banc.alertes
        banc.vider()

        # ---- nouveaute dont SEULE la variante endommagee est disponible : aucune alerte
        f.ajouter("neuf-ko", _t("neuf-ko"), [("Comme Neuf", False, "79.90"), ("Endommagé", True, "59.90")])
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == [], banc.alertes
        assert (await banc.ligne("neuf-ko"))["en_stock"] == 0
        f.stock("neuf-ko", True, variante=0)                        # la version NEUVE arrive
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "neuf-ko")], banc.alertes
        tout += banc.alertes
        banc.vider()

        # ---- produit d'occasion publie comme fiche a part, et carte seule : jamais d'alerte
        f.ajouter("occasion", "[ENDOMMAGÉ] " + _t("occasion"), [("Default Title", True, "30.00")])
        f.ajouter("carte3", "Mesmérella (WHT 042) - Flamme Blanche", [("Default Title", True, "0.4")])
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == []
        assert await banc.ligne("occasion") is None and await banc.ligne("carte3") is None

        # ---- glitch d'une lecture (rupture isolee puis retour) : aucune fausse alerte
        f.stock("etb", False)
        await banc.watchlist()                                      # 1re lecture "rupture"
        f.stock("etb", True)
        await banc.watchlist()                                      # retour : rien
        assert banc.alertes == [] and (await banc.ligne("etb"))["en_stock"] == 1
        # vraie rupture (2 lectures) puis vrai restock : exactement un RESTOCK
        f.stock("etb", False)
        await banc.watchlist()
        await banc.watchlist()
        assert (await banc.ligne("etb"))["en_stock"] == 0 and banc.alertes == []
        f.stock("etb", True)
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "etb")], banc.alertes
        tout += banc.alertes
        banc.vider()

        # ---- erreurs reseau : aucune alerte, aucun changement d'etat
        avant = {p["url"]: p["en_stock"] for p in await database.recuperer_tous_produits()}
        f.panne = "blocked"
        rap = await banc.watchlist()
        await banc.recherche()
        f.panne = None
        assert banc.alertes == [] and rap.stores[0].statut == "blocked"
        apres = {p["url"]: p["en_stock"] for p in await database.recuperer_tous_produits()}
        assert apres == avant

        # ---- REAPPARITION : fiche absente puis de retour, stock inchange => PAS de RESTOCK
        await banc.disparaitre("pack", 30, f)                         # "pack" etait EN STOCK
        assert (await banc.ligne("pack"))["en_stock"] == 1            # disparition != rupture
        assert banc.alertes == []
        await banc.echeance("pack")
        f.produits["pack"]["publie"] = True                           # fiche de retour, toujours en stock
        rap = await banc.watchlist()
        assert banc.alertes == [], banc.alertes                       # reapparition != restock
        assert rap.stores[0].reapparitions == 1 and rap.stores[0].restocks == 0
        ligne = await banc.ligne("pack")
        assert ligne["introuvables"] == 0 and ligne["prochaine_verif"] == 0 and ligne["en_stock"] == 1

        # ---- vraie transition cachee derriere une disparition : "display" etait en RUPTURE
        await banc.disparaitre("display", 30, f)
        assert (await banc.ligne("display"))["en_stock"] == 0
        await banc.echeance("display")
        f.produits["display"]["publie"] = True
        f.stock("display", True)                                      # revient EN STOCK
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "display")], banc.alertes
        tout += banc.alertes
        banc.vider()

        # ---- reapparition qui revient en RUPTURE : aucune alerte
        await banc.disparaitre("bientot", 30, f)
        await banc.echeance("bientot")
        f.produits["bientot"]["publie"] = True
        f.stock("bientot", False)
        await banc.watchlist()
        assert banc.alertes == []

        # ---- option ALERTER_REAPPARITION : alerte DISTINCTE, jamais "RESTOCK"
        config.ALERTER_REAPPARITION = True
        config.ALERT_DEDUP_WINDOW = 0
        await banc.disparaitre("nouveau", 30, f)
        await banc.echeance("nouveau")
        f.produits["nouveau"]["publie"] = True
        await banc.watchlist()
        assert banc.alertes == [("REAPPARITION", "nouveau")], banc.alertes
        banc.vider()
        # absence courte (< 24 h) : meme avec l'option, aucune alerte
        await banc.disparaitre("etb", 7, f)
        await banc.echeance("etb")
        f.produits["etb"]["publie"] = True
        await banc.watchlist()
        assert banc.alertes == []
        config.ALERTER_REAPPARITION = False

        # ---- bilan : toutes les alertes de la simulation sont des vraies, une seule fois chacune
        assert tout == [("NOUVEAUTE", "nouveau"), ("RESTOCK", "bientot"), ("RESTOCK", "neuf-ko"),
                        ("RESTOCK", "etb"), ("RESTOCK", "display")], tout
        assert len(tout) == len(set(tout))
    finally:
        shop.http_get_json = reel
        config.SEARCH_KEYWORDS, config.ALERT_DEDUP_WINDOW = kw, dedup
        config.ALERTER_REAPPARITION = False
        await banc.arreter()


def test_integration_shopify():
    asyncio.run(_scenario_shopify())


# ======================================================================= scenario WooCommerce
class FausseWoo:
    def __init__(self):
        self.produits: dict[str, dict] = {}

    def ajouter(self, slug, nom, stock=True, achetable=True, prix="3999", type_="simple"):
        self.produits[slug] = {"slug": slug, "name": nom, "permalink": f"https://www.w.fr/p/{slug}/",
                               "is_in_stock": stock, "is_purchasable": achetable, "type": type_,
                               "images": [], "sku": slug,
                               "prices": {"price": prix, "currency_minor_unit": 2}, "publie": True}

    async def http(self, url, timeout_ms=0, headers=None):
        pub = [p for p in self.produits.values() if p["publie"]]
        if "search=" in url:
            return (pub if "pokemon" in url and "page=1" in url else []), "ok", None
        if "slug=" in url:
            demandes = url.split("slug=")[1].split("&")[0].replace("%2C", ",").split(",")
            return [p for p in pub if p["slug"] in demandes], "ok", None
        return None, "not_found", "x"


async def _scenario_woo():
    w = FausseWoo()
    reel = woo.http_get_json
    woo.http_get_json = w.http
    config.WATCHLIST_LOT = True
    config.ALERTER_REAPPARITION = False
    config.DISPARU_MIN_ECHECS, config.DISPARU_APRES_HEURES = 3, 1
    nom = lambda n: f"Pokémon - Display de 36 Boosters ME05 {n}"
    banc = Banc(w, lambda: WooCommerceScraper(E, "w.fr", None), "https://www.w.fr/p/{}/")
    try:
        await banc.demarrer()
        w.ajouter("a", nom("a"))
        w.ajouter("b", nom("b"), stock=False)
        await banc.recherche()
        assert banc.alertes == []                                   # premiere decouverte silencieuse

        # nouveaute disponible => exactement une alerte
        w.ajouter("nouveau", nom("nouveau"))
        await banc.recherche()
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == [("NOUVEAUTE", "nouveau")], banc.alertes
        banc.vider()

        # faux "en stock" (non achetable a 0 EUR), produit variable, prix 0 : jamais d'alerte
        w.ajouter("lire-la-suite", nom("lls"), stock=True, achetable=False, prix="0")
        w.ajouter("variable", nom("var"), type_="variable")
        w.ajouter("prix-nul", nom("pn"), prix="0")
        await banc.recherche()
        await banc.watchlist()
        assert banc.alertes == []

        # le produit non achetable devient reellement achetable => un seul RESTOCK
        w.produits["lire-la-suite"].update(is_purchasable=True, prices={"price": "2499", "currency_minor_unit": 2})
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "lire-la-suite")], banc.alertes
        banc.vider()

        # restock classique + reapparition sans changement
        w.produits["b"]["is_in_stock"] = True
        await banc.watchlist()
        assert banc.alertes == [("RESTOCK", "b")]
        banc.vider()
        await banc.disparaitre("a", 30, w)
        assert (await banc.ligne("a"))["en_stock"] == 1             # disparition != rupture
        await banc.echeance("a")
        w.produits["a"]["publie"] = True
        rap = await banc.watchlist()
        assert banc.alertes == [] and rap.stores[0].reapparitions == 1
    finally:
        woo.http_get_json = reel
        await banc.arreter()


def test_integration_woo():
    asyncio.run(_scenario_woo())


def test():
    test_integration_shopify()
    test_integration_woo()


if __name__ == "__main__":
    test()
    print("OK")
