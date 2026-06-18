"""Gestion des notifications Discord (transport webhook OU bot)."""
import json
import asyncio
import time
import aiohttp
import logging
from config import (
    DISCORD_WEBHOOK_URL, DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID, DISCORD_ALERT_ROLE_ID,
)
from product_format import (
    STORE_COLORS,
    ean_search_links,
    format_stock,
    markdown_links,
    normalize_product,
    seller_badge,
)

logger = logging.getLogger(__name__)

CHART_FILENAME = "price_history.png"
DISCORD_API = "https://discord.com/api/v10"

# Throttle : Discord limite les envois. On espace et on sérialise pour éviter 429.
_MIN_INTERVAL_S = 1.2
_envoi_lock = asyncio.Lock()
_dernier_envoi = 0.0


def _mode_bot() -> bool:
    """Vrai si un bot est configuré : il débloque les boutons et l'autobuy."""
    return bool(DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)


async def _post_avec_retry(session, url, *, headers=None, **kwargs) -> bool:
    """POST avec respect du 429 (retry_after). Retourne True si livré."""
    for tentative in range(4):
        async with session.post(url, headers=headers, **kwargs) as response:
            if response.status in (200, 201, 204):
                return True
            if response.status == 429:
                try:
                    data = await response.json()
                    retry_after = float(data.get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                logger.warning("Discord 429 — pause %.1fs (tentative %d).",
                               retry_after, tentative + 1)
                await asyncio.sleep(retry_after + 0.3)
                continue
            texte = await response.text()
            logger.error("Erreur Discord: %s — %s", response.status, texte[:200])
            return False
    logger.error("Discord: abandon après plusieurs 429.")
    return False


def _bouton_lien(label: str, url: str) -> dict:
    """Bouton Discord de type 'lien' (ouvre une URL, aucun backend requis)."""
    return {"type": 2, "style": 5, "label": label[:80], "url": url}


def build_buy_components(product: dict) -> list:
    """
    Construit la rangée de boutons d'une alerte : Acheter + recherches + Autobuy.
    Réservé au mode bot (un webhook simple ne peut pas envoyer de boutons).

    Le bouton "Autobuy" est interactif (custom_id) : ses clics sont reçus par
    discord_bot.py via la passerelle. Les autres sont de simples liens.
    """
    boutons = []
    if product.get("url"):
        boutons.append(_bouton_lien("🛒 Acheter", product["url"]))
    for label, url in ean_search_links(product["ean"], product["title"]).items():
        boutons.append(_bouton_lien(label, url))
    # Bouton interactif (fondation autobuy), géré par le bot gateway.
    boutons.append({"type": 2, "style": 1, "label": "⚡ Autobuy (bientôt)",
                    "custom_id": "autobuy"})
    return [{"type": 1, "components": boutons[:5]}]  # max 5 boutons par rangée


def _payload_multipart(payload: dict, chart_png: bytes) -> aiohttp.FormData:
    form = aiohttp.FormData()
    form.add_field("payload_json", json.dumps(payload), content_type="application/json")
    form.add_field("files[0]", chart_png, filename=CHART_FILENAME, content_type="image/png")
    return form


async def _envoyer_via_webhook(session, payload, chart_png):
    """Transport historique : webhook simple (sans boutons)."""
    if chart_png:
        await _post_avec_retry(session, DISCORD_WEBHOOK_URL,
                               data=_payload_multipart(payload, chart_png))
    else:
        await _post_avec_retry(session, DISCORD_WEBHOOK_URL, json=payload)


async def _envoyer_via_bot(session, payload, chart_png):
    """Transport bot : poste dans un canal, supporte les boutons/composants."""
    url = f"{DISCORD_API}/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    if chart_png:
        await _post_avec_retry(session, url, headers=headers,
                               data=_payload_multipart(payload, chart_png))
    else:
        await _post_avec_retry(session, url, headers=headers, json=payload)


async def envoyer_alerte(produit: dict, enseigne: str, type_alerte: str,
                         chart_png: bytes | None = None):
    """
    Envoie une alerte stock sur Discord.

    Choisit automatiquement le transport :
      - bot configuré  -> message avec boutons (Acheter, recherches) ;
      - sinon          -> webhook classique (le lien reste dans l'embed).
    type_alerte: "NOUVEAUTE" ou "RESTOCK". Sérialisé + throttlé anti-429.
    """
    if not (_mode_bot() or DISCORD_WEBHOOK_URL):
        return

    embed = build_alert_embed(produit, enseigne, type_alerte, with_chart=bool(chart_png))
    payload = {"embeds": [embed]}

    # Ping de rôle : mention en tête de message => notification instantanée.
    if DISCORD_ALERT_ROLE_ID:
        payload["content"] = f"<@&{DISCORD_ALERT_ROLE_ID}>"
        payload["allowed_mentions"] = {"roles": [str(DISCORD_ALERT_ROLE_ID)]}

    if _mode_bot():
        components = build_buy_components(normalize_product(produit, enseigne))
        if components:
            payload["components"] = components

    await _envoyer(payload, chart_png)


async def envoyer_message(embed: dict):
    """Envoie un embed simple (ex. résumé/heartbeat), via bot ou webhook."""
    await _envoyer({"embeds": [embed]})


async def poster_embed(embed: dict, content: str = "") -> bool:
    """
    Envoi ponctuel et autonome d'un embed (utilisé par le compositeur de l'IHM).

    Contrairement à `_envoyer`, n'utilise PAS le verrou de throttle partagé : il est
    sûr de l'appeler depuis une autre boucle asyncio que celle du bot. Faible
    fréquence (envoi manuel) → pas de risque de 429. Retourne True si livré.
    """
    if not (_mode_bot() or DISCORD_WEBHOOK_URL):
        logger.warning("Envoi impossible : aucun canal Discord configuré.")
        return False
    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content
    try:
        async with aiohttp.ClientSession() as session:
            if _mode_bot():
                url = f"{DISCORD_API}/channels/{DISCORD_CHANNEL_ID}/messages"
                headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
                return await _post_avec_retry(session, url, headers=headers, json=payload)
            return await _post_avec_retry(session, DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        logger.error("Exception envoi embed: %s", e)
        return False


async def _envoyer(payload: dict, chart_png: bytes | None = None):
    """Coeur d'envoi : throttle anti-429 + choix du transport (bot/webhook)."""
    if not (_mode_bot() or DISCORD_WEBHOOK_URL):
        return

    global _dernier_envoi
    async with _envoi_lock:
        ecoule = time.monotonic() - _dernier_envoi
        if ecoule < _MIN_INTERVAL_S:
            await asyncio.sleep(_MIN_INTERVAL_S - ecoule)
        try:
            async with aiohttp.ClientSession() as session:
                if _mode_bot():
                    await _envoyer_via_bot(session, payload, chart_png)
                else:
                    await _envoyer_via_webhook(session, payload, chart_png)
        except Exception as e:
            logger.error("Exception Discord: %s", e)
        finally:
            _dernier_envoi = time.monotonic()


def build_alert_embed(produit: dict, enseigne: str, type_alerte: str,
                      with_chart: bool = False) -> dict:
    """Construit l'embed Discord sans l'envoyer."""
    product = normalize_product(produit, enseigne)
    alert_label = {
        "NOUVEAUTE": "Nouveau",
        "RESTOCK": "Restock",
        "DEAL": "Baisse de prix",
    }.get(type_alerte, type_alerte)
    price_value = product["price"]
    if product["discount"]:
        price_value = f"{price_value} ({product['discount']})"

    ean_value = product["ean"] or "Non renseigné"
    search_links = ean_search_links(product["ean"], product["title"])

    fields = [
        {"name": "Référence", "value": product["reference"], "inline": False},
        {"name": "Prix", "value": price_value, "inline": True},
        {"name": "Stock", "value": format_stock(product), "inline": True},
    ]
    # Champs enrichis affiches seulement s'ils sont renseignes.
    if product.get("brand"):
        fields.append({"name": "Marque", "value": product["brand"], "inline": True})
    fields.append({"name": "Vendeur",
                   "value": seller_badge(product["store"], product.get("seller", "")),
                   "inline": True})
    fields += [
        {"name": "EAN", "value": ean_value, "inline": False},
        {"name": "Recherche", "value": markdown_links(search_links), "inline": False},
        {"name": "Liens directs", "value": markdown_links(product["direct_links"]), "inline": False},
    ]

    embed = {
        "title": build_embed_title(product),
        "url": product["url"],
        "color": STORE_COLORS.get(product["store"], 0xE30613),
        "description": f"**{product['detailed_reference']}**",
        "fields": fields,
        "footer": {"text": f"TCG-STOCK-BOT - {alert_label} - {product['store_label']}"},
    }

    if product["image_url"]:
        embed["thumbnail"] = {"url": product["image_url"]}

    if with_chart:
        embed["image"] = {"url": f"attachment://{CHART_FILENAME}"}

    return embed


def build_embed_title(product: dict) -> str:
    price = product["price"] if product["price"] != "N/A" else "Prix N/A"
    return (
        f"{product['country_flag']} {product['store_label']} - "
        f"{price} - {product['reference']} - {product['title']}"
    )
