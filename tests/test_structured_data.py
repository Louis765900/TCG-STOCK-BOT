import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structured_data import extraire_donnees_structurees

JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Coffret ETB Pokemon",
 "brand":{"@type":"Brand","name":"Pokemon"},"sku":"C1","gtin13":"0820650559013",
 "image":["https://cdn/x.jpg"],
 "aggregateRating":{"ratingValue":"4.7","reviewCount":"212"},
 "offers":{"@type":"Offer","price":"54.99","priceCurrency":"EUR",
   "availability":"https://schema.org/InStock","seller":{"name":"Auchan"}}}
</script></head></html>
"""

MICRO = """
<div itemscope itemtype="https://schema.org/Product">
  <span itemprop="name">Booster Pokemon</span>
  <meta itemprop="availability" content="https://schema.org/OutOfStock">
  <meta itemprop="price" content="4.99">
</div>
"""


def test():
    d = extraire_donnees_structurees(JSONLD)
    assert d["title"].startswith("Coffret")
    assert d["price"] == "54.99"
    assert d["in_stock"] is True
    assert d["ean"] == "0820650559013"
    assert d["brand"] == "Pokemon"
    assert d["seller"] == "Auchan"
    assert d["rating"] == "4.7"

    d2 = extraire_donnees_structurees(MICRO)
    assert d2["in_stock"] is False
    assert d2["price"] == "4.99"
    assert d2["title"] == "Booster Pokemon"

    # Robustesse : pas de crash
    assert extraire_donnees_structurees("<html></html>") == {}
    assert extraire_donnees_structurees(None) == {}


if __name__ == "__main__":
    test()
    print("OK")
