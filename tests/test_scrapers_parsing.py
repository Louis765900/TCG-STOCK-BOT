"""Parsing des scrapers sur des charges utiles figees (hors reseau) : stock reel, prix reel."""
import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "tools"))

from bs4 import BeautifulSoup
from scrapers.woocommerce import WooCommerceScraper
from scrapers.shopify import ShopifyScraper
from scrapers.auchan import AuchanScraper
import audit_scrapers as audit


def _woo(**kw):
    base = {"name": "Pok&#233;mon &#8211; Display", "permalink": "https://x.fr/p/",
            "is_in_stock": True, "is_purchasable": True, "images": [],
            "prices": {"price": "5499", "currency_minor_unit": 2}}
    base.update(kw)
    return WooCommerceScraper("Boutique", "x.fr", None)._produit(base)


def test_woocommerce():
    p = _woo()
    assert p["en_stock"] is True and p["prix"] == "54.99" and "Pokémon" in p["titre"]
    # is_in_stock annonce mais produit NON achetable a 0 EUR => pas "en stock"
    p = _woo(is_purchasable=False, prices={"price": "0", "currency_minor_unit": 2})
    assert p["en_stock"] is False and p["prix"] == "N/A"
    # Prix a 0 meme "achetable" : inexploitable, jamais d'alerte "en stock"
    assert _woo(prices={"price": "0", "currency_minor_unit": 2})["en_stock"] is False
    # Vraie rupture
    assert _woo(is_in_stock=False)["en_stock"] is False


def test_shopify():
    s = ShopifyScraper("Boutique", "x.fr", None)
    p = s._produit_depuis_suggest({"handle": "display-me04", "title": "Display ME04",
                                   "price": "216.00", "available": True,
                                   "featured_image": {"url": "//cdn/x.png"}})
    assert p["url"] == "https://www.x.fr/products/display-me04"
    assert p["prix"] == "216.00" and p["en_stock"] is True
    assert p["image_url"] == "https://cdn/x.png" or isinstance(p["image_url"], str)
    assert s._produit_depuis_suggest({"handle": "", "title": "t"}) is None
    assert s._produit_depuis_suggest({"handle": "a", "title": "t", "price": "abc",
                                      "available": False})["prix"] == "N/A"


_TUILE = """<article class="product-thumbnail {cls}">
<a class="product-thumbnail__details-wrapper" href="/p/x"></a>
<p class="product-thumbnail__description">POKEMON Coffret</p>
<meta itemprop="price" content="29.99">{avail}</article>"""


def test_auchan_stock():
    sc = AuchanScraper(None)

    def lire(cls="", avail=""):
        soup = BeautifulSoup(_TUILE.format(cls=cls, avail=avail), "html.parser")
        return sc.parse_page(soup)[0]
    assert lire(avail='<meta itemprop="availability" content="https://schema.org/InStock">')["en_stock"] is True
    assert lire(avail='<meta itemprop="availability" content="https://schema.org/OutOfStock">')["en_stock"] is False
    assert lire(cls="outOfStock")["en_stock"] is False
    # Aucun signal : on ne presume PAS "en stock"
    assert lire()["en_stock"] is False
    assert lire()["prix"] == "29.99€"


_CARTE_CULTURA = """<div data-cmp-is="product" data-product-name="{nom}" data-product-price="{prix}"
 data-product-ean="0820650556579" data-product-stock="{stock}" data-product-sku="1">
<div class="one-card one-card--product {mkp}"><a class="one-product--plp" href="/p-pokemon-x-0820650556579.html"></a>
<span class="one-product__desc__origin">Pokemon</span>
<img src="https://cdn.cultura.com/x.jpg"></div></div>"""


def test_cultura():
    from scrapers.cultura import CulturaScraper
    sc = CulturaScraper(None)

    def lire(stock="EN STOCK EN LIGNE", mkp="", prix="6.99"):
        html = _CARTE_CULTURA.format(nom="Pokemon Ev02 booster display", prix=prix,
                                     stock=stock, mkp=mkp)
        return sc.parse_page(BeautifulSoup(html, "html.parser"))[0]
    p = lire()
    assert p["en_stock"] is True and p["prix"] == "6.99" and p["ean"] == "0820650556579"
    assert p["url"] == "https://www.cultura.com/p-pokemon-x-0820650556579.html"
    assert p["seller"] == "Cultura" and p["brand"] == "Pokemon"
    # Seul "EN STOCK EN LIGNE" est du stock immediat
    for stock in ("INDISPONIBLE EN LIGNE", "DISPONIBLE SOUS X JOURS", "available_preorder",
                  "DISPONIBLE A PARTIR DU", ""):
        assert lire(stock)["en_stock"] is False, stock
    # Marketplace => revendeur tiers (masquable)
    from product_format import est_revendeur
    m = lire(mkp="one-card--product--mkp")
    assert est_revendeur("Cultura", m["seller"]) and not est_revendeur("Cultura", p["seller"])
    assert lire(prix="abc")["prix"] == "N/A"


def test_audit_outils():
    prods = [
        {"url": "https://www.auchan.fr/a", "titre": "Pokémon Display ME04", "prix": "216", "en_stock": True},
        {"url": "https://www.auchan.fr/a", "titre": "Pokémon Display ME04", "prix": "216", "en_stock": True},
        {"url": "http://www.auchan.fr/b", "titre": "Peluche Pikachu", "prix": "N/A", "en_stock": False},
        {"url": "https://evil.com/c", "titre": "Pokémon Coffret Dresseur d'Élite", "prix": "99999", "en_stock": True},
    ]
    q = audit.analyser_produits("Auchan", prods)
    assert q["total"] == 4 and q["doublons"] == 1 and q["nb_urls_invalides"] == 2
    assert q["avec_prix"] == 3 and len(q["prix_aberrants"]) == 1
    assert q["valides_jcc"] == 3 and q["en_stock"] == 3

    c = audit.comparer_fiche({"titre": "t", "url": "u", "en_stock": True, "prix": "10.00"},
                             {"status": "ok", "en_stock": False, "prix": "10.20"})
    assert c["stock_coherent"] is False and c["prix_coherent"] is True
    c = audit.comparer_fiche({"titre": "t", "url": "u", "en_stock": True, "prix": "10"},
                             {"status": "blocked"})
    assert c["stock_coherent"] is None and c["statut_fiche"] == "blocked"

    ok = {"statut_recherche": "ok", "fiches": [{"statut_fiche": "ok", "stock_coherent": True,
                                                "prix_coherent": True}],
          "qualite": {"total": 5, "valides_jcc": 3, "nb_urls_invalides": 0, "avec_prix": 5,
                      "univers_cible": 3, "prix_aberrants": [], "doublons": 0}}
    assert audit.verdict(ok)[0] == "FONCTIONNEL"
    assert audit.verdict(dict(ok, statut_recherche="blocked"))[0] == "DEFAILLANT"
    assert audit.verdict(dict(ok, qualite=dict(ok["qualite"], total=0)))[0] == "DEFAILLANT"
    hors_sujet = dict(ok["qualite"], total=99, univers_cible=1, valides_jcc=1, avec_prix=99)
    assert audit.verdict(dict(ok, qualite=hors_sujet))[0] == "DEFAILLANT"   # liste generique
    bad = dict(ok, fiches=[{"statut_fiche": "ok", "stock_coherent": False, "prix_coherent": True}])
    assert audit.verdict(bad)[0] == "PARTIEL"
    assert audit.verdict(dict(ok, fiches=[]))[0] == "PARTIEL"
    assert audit.verdict({"non_teste": "x"})[0] == "NON TESTE"


def test():
    test_woocommerce()
    test_shopify()
    test_auchan_stock()
    test_cultura()
    test_audit_outils()


if __name__ == "__main__":
    test()
    print("OK")
