"""Gestion des notifications Discord."""
import aiohttp
import logging
from config import DISCORD_WEBHOOK_URL
from product_format import (
    STORE_COLORS,
    ean_search_links,
    format_stock,
    markdown_links,
    normalize_product,
)

logger = logging.getLogger(__name__)


async def envoyer_alerte(produit: dict, enseigne: str, type_alerte: str):
    """
    Envoie un webhook Discord au format deal/stock.
    type_alerte: "NOUVEAUTE" ou "RESTOCK"
    """
    if not DISCORD_WEBHOOK_URL:
        return

    embed = build_alert_embed(produit, enseigne, type_alerte)
    payload = {"embeds": [embed]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as response:
                if response.status not in [200, 204]:
                    logger.error(f"Erreur Webhook Discord: {response.status}")
    except Exception as e:
        logger.error(f"Exception Discord: {e}")


def build_alert_embed(produit: dict, enseigne: str, type_alerte: str) -> dict:
    """Construit l'embed Discord sans l'envoyer."""
    product = normalize_product(produit, enseigne)
    alert_label = "Nouveau" if type_alerte == "NOUVEAUTE" else "Restock"
    price_value = product["price"]
    if product["discount"]:
        price_value = f"{price_value} ({product['discount']})"

    ean_value = product["ean"] or "Non renseigné"
    search_links = ean_search_links(product["ean"], product["title"])

    embed = {
        "title": build_embed_title(product),
        "url": product["url"],
        "color": STORE_COLORS.get(product["store"], 0xE30613),
        "description": f"**{product['detailed_reference']}**",
        "fields": [
            {"name": "Référence", "value": product["reference"], "inline": False},
            {"name": "Prix", "value": price_value, "inline": True},
            {"name": "Stock", "value": format_stock(product), "inline": True},
            {"name": "EAN", "value": ean_value, "inline": False},
            {"name": "Recherche", "value": markdown_links(search_links), "inline": False},
            {"name": "Liens directs", "value": markdown_links(product["direct_links"]), "inline": False},
        ],
        "footer": {"text": f"TCG-STOCK-BOT - {alert_label} - {product['store_label']}"},
    }

    if product["image_url"]:
        embed["thumbnail"] = {"url": product["image_url"]}

    return embed


def build_embed_title(product: dict) -> str:
    price = product["price"] if product["price"] != "N/A" else "Prix N/A"
    return (
        f"{product['country_flag']} {product['store_label']} - "
        f"{price} - {product['reference']} - {product['title']}"
    )
