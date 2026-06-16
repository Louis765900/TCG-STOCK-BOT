"""Normalisation des produits et liens utiles pour les alertes Discord."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus
import re


COUNTRY_FLAGS = {
    "FR": "🇫🇷",
    "ES": "🇪🇸",
    "DE": "🇩🇪",
    "IT": "🇮🇹",
    "UK": "🇬🇧",
    "US": "🇺🇸",
}

STORE_LABELS = {
    "Auchan": "Auchan",
    "Cultura": "Cultura",
    "GrandeRecre": "La Grande Récré",
    "KingJouet": "King Jouet",
    "Leclerc": "E.Leclerc",
    "Smyths": "Smyths Toys",
}

STORE_COLORS = {
    "Amazon": 0xFF9900,
    "Auchan": 0xE30613,
    "Cultura": 0x1F6FEB,
    "GrandeRecre": 0xE30613,
    "KingJouet": 0xE30613,
    "Leclerc": 0x0066CC,
    "Smyths": 0x009FE3,
}


def normalize_product(prod: dict, enseigne: str) -> dict:
    """Retourne un produit avec tous les champs attendus par l'embed."""
    title = clean_text(prod.get("titre") or prod.get("title") or "Produit inconnu")
    store = prod.get("enseigne") or enseigne
    country = (prod.get("country") or "FR").upper()

    normalized = {
        "title": title,
        "url": prod.get("url", ""),
        "image_url": prod.get("image_url", ""),
        "store": store,
        "store_label": STORE_LABELS.get(store, store),
        "country": country,
        "country_flag": COUNTRY_FLAGS.get(country, country),
        "reference": clean_text(prod.get("reference") or extract_reference(prod.get("url", "")) or "Référence inconnue"),
        "detailed_reference": clean_text(prod.get("detailed_reference") or title),
        "price": clean_price(prod.get("prix") or prod.get("price")),
        "old_price": clean_price(prod.get("old_price")),
        "discount": clean_discount(prod.get("discount")),
        "in_stock": bool(prod.get("en_stock")),
        "stock_quantity": normalize_stock_quantity(prod.get("stock_quantity")),
        "ean": clean_ean(prod.get("ean")),
        "brand": clean_text(prod.get("brand")),
        "seller": clean_text(prod.get("seller")),
        "direct_links": prod.get("direct_links") or {},
    }

    if not normalized["discount"]:
        normalized["discount"] = compute_discount(normalized["price"], normalized["old_price"])

    if normalized["url"] and normalized["store_label"] not in normalized["direct_links"]:
        normalized["direct_links"][normalized["store_label"]] = normalized["url"]

    return normalized


def clean_text(value: object) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def clean_price(value: object) -> str:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return "N/A"
    if "€" in text:
        return text
    if re.search(r"\d", text):
        return f"{text}€"
    return text


def clean_discount(value: object) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return text if "%" in text else f"{text}%"


def normalize_stock_quantity(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None
    return max(quantity, 0)


def clean_ean(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) in {8, 12, 13, 14} else ""


def extract_reference(url: str) -> str:
    text = clean_text(url)
    if not text:
        return ""
    match = re.search(r"/pr-([a-zA-Z0-9-]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"([A-Z]?\d{8,}|[a-f0-9-]{24,})", text, re.IGNORECASE)
    return match.group(1) if match else ""


def compute_discount(price: str, old_price: str) -> str:
    current = parse_price(price)
    old = parse_price(old_price)
    if current is None or old is None or old <= current:
        return ""
    discount = (old - current) / old * Decimal("100")
    return f"-{discount.quantize(Decimal('0.01'))}%"


def parse_price(value: str) -> Decimal | None:
    match = re.search(r"\d+(?:[,.]\d+)?", value or "")
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def ean_search_links(ean: str, fallback_title: str) -> dict[str, str]:
    query = ean or fallback_title
    encoded = quote_plus(query)
    return {
        "Google": f"https://www.google.com/search?q={encoded}",
        "eBay": f"https://www.ebay.fr/sch/i.html?_nkw={encoded}",
    }


def format_stock(product: dict) -> str:
    if not product["in_stock"]:
        return "Indisponible"
    quantity = product.get("stock_quantity")
    if quantity is None:
        return "Disponible"
    if quantity <= 0:
        return "Indisponible"
    return f"Disponible - {quantity} restant(s)"


def markdown_links(links: dict[str, str]) -> str:
    cleaned = [(clean_text(label), clean_text(url)) for label, url in links.items() if url]
    if not cleaned:
        return "Aucun lien"
    return " | ".join(f"[{label}]({url})" for label, url in cleaned)
