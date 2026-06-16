import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from product_format import (
    normalize_product, clean_price, clean_ean, compute_discount, format_stock,
)


def test():
    # clean_price
    assert clean_price("33.95") == "33.95€"
    assert clean_price("12,50€") == "12,50€"
    assert clean_price("N/A") == "N/A"

    # EAN : seules les longueurs valides passent
    assert clean_ean("0196214136694") == "0196214136694"
    assert clean_ean("abc") == ""

    # Remise calculée
    assert compute_discount("29.99", "39.99").startswith("-")
    assert compute_discount("39.99", "39.99") == ""  # pas de hausse

    # normalize_product porte marque + vendeur + ean
    prod = {"titre": "Coffret", "url": "https://x/pr-C1", "prix": "10",
            "en_stock": True, "ean": "0196214136694", "brand": "Pokemon",
            "seller": "Auchan", "stock_quantity": 3}
    n = normalize_product(prod, "Auchan")
    assert n["brand"] == "Pokemon"
    assert n["seller"] == "Auchan"
    assert n["ean"] == "0196214136694"
    assert n["in_stock"] is True

    # format_stock
    assert format_stock({"in_stock": False}) == "Indisponible"
    assert format_stock({"in_stock": True, "stock_quantity": 3}) == "Disponible - 3 restant(s)"
    assert format_stock({"in_stock": True, "stock_quantity": None}) == "Disponible"


if __name__ == "__main__":
    test()
    print("OK")
