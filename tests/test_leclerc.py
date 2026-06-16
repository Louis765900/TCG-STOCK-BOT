import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.leclerc import LeclercScraper

# Item JSON représentatif de l'API Leclerc (hors-ligne, pas de réseau).
ITEM = {
    "id": "0196214136694", "sku": "0196214136694",
    "slug": "pokemon-me03-pack-3-boosters",
    "label": "Pokémon ME03 : pack 3 boosters",
    "attributeGroups": [{"attributes": [
        {"code": "marque", "value": {"label": "Pokémon"}},
    ]}],
    "variants": [{
        "attributes": [{"code": "image1", "value": {"url": "https://media/x"}}],
        "offers": [
            {"isDefault": True, "stock": 10, "shop": {"label": "ZOOMICI"},
             "basePrice": {"price": {"price": 3395}}},
            {"isDefault": True, "stock": 15, "shop": {"label": "Stock e-commerce"},
             "basePrice": {"price": {"price": 2662}}},
            {"stock": 0, "shop": {"label": "RUPTURE"},
             "basePrice": {"price": {"price": 2000}}},  # moins cher mais HORS stock
        ],
    }],
}


def test():
    p = LeclercScraper(browser=None)._produit_depuis_item(ITEM)
    # Doit choisir l'offre EN STOCK la moins chère (26.62), pas la 20.00 hors stock.
    assert p["prix"] == "26.62", p["prix"]
    assert p["seller"] == "Stock e-commerce", p["seller"]
    assert p["en_stock"] is True
    assert p["ean"] == "0196214136694"
    assert p["brand"] == "Pokémon"
    assert p["url"] == "https://www.e.leclerc/fp/pokemon-me03-pack-3-boosters-0196214136694"
    assert p["image_url"] == "https://media/x"

    # Item sans offre -> indisponible, pas de crash
    item_vide = dict(ITEM, variants=[{"attributes": [], "offers": []}])
    p2 = LeclercScraper(browser=None)._produit_depuis_item(item_vide)
    assert p2["en_stock"] is False and p2["prix"] == "N/A"


if __name__ == "__main__":
    test()
    print("OK")
