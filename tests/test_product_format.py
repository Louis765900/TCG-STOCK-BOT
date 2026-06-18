import os
import sys
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

from product_format import (
    normalize_product, clean_price, clean_ean, compute_discount, format_stock,
    est_vendeur_officiel, est_revendeur, seller_badge, cardmarket_link, ean_search_links,
    mots_cles_recherche,
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

    # Vendeur officiel vs revendeur (Chantier 20)
    assert est_vendeur_officiel("Leclerc", "E.Leclerc") is True
    assert est_vendeur_officiel("Leclerc", "") is True          # pas de marketplace = direct
    assert est_revendeur("Leclerc", "1001 Jouets") is True      # tiers = revendeur
    assert est_vendeur_officiel("LudiJeux", "") is True         # boutique = officiel
    assert seller_badge("Leclerc", "1001 Jouets").startswith("🔁")
    assert seller_badge("LudiJeux", "").startswith("✅")

    # Lien Cardmarket : bon jeu + présent dans les liens de recherche (Chantier 21)
    assert "/Pokemon/Products/Search" in cardmarket_link("ETB Pokémon Flammes Obsidiennes")
    assert "/OnePiece/Products/Search" in cardmarket_link("Display One Piece OP05")
    assert "Cardmarket" in ean_search_links("123", "Display One Piece OP05")

    # Mots-clés Cardmarket propres : on retire « scellé », langue et nom du jeu,
    # on garde les termes identifiants (type + set). (Chantier 22)
    assert mots_cles_recherche("Pokémon Display M1S scellé français") == "Display M1S"
    assert mots_cles_recherche("Display One Piece OP05 scellé FR") == "Display OP05"
    lien = cardmarket_link("Pokémon Display M1S scellé français")
    assert "scelle" not in lien.lower() and "pokemon" not in lien.split("?")[1].lower()
    assert "Display+M1S" in lien
    # Repli : un titre entièrement filtré ne casse pas (garde le titre nettoyé)
    assert mots_cles_recherche("Pokémon scellé FR") == "Pokémon scellé FR"


if __name__ == "__main__":
    test()
    print("OK")
