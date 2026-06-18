"""
proxy_fetch.py — Filet de secours via des "scraping APIs" (proxies anti-bot).

Quand une requête HTTP directe est bloquée (ex. DataDome sur Leclerc), on
réessaie en passant par un service tiers qui sait franchir les protections :
ScrapingBee, ZenRows ou Crawlbase. On les essaie EN CASCADE (le premier qui
répond gagne) → on cumule les quotas gratuits et on bascule si l'un échoue.

C'est un DERNIER RECOURS : appelé seulement sur blocage, donc très peu de
requêtes → consommation de crédits minime. Vide = désactivé (100% gratuit).
"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

import aiohttp

import config

logger = logging.getLogger("proxy_fetch")


def _fournisseurs() -> list[tuple[str, str]]:
    """Liste ordonnée (nom, gabarit d'URL) des fournisseurs configurés."""
    out: list[tuple[str, str]] = []
    if config.SCRAPINGBEE_KEY:
        out.append((
            "ScrapingBee",
            "https://app.scrapingbee.com/api/v1/"
            f"?api_key={config.SCRAPINGBEE_KEY}&render_js=false&url={{u}}",
        ))
    if config.ZENROWS_KEY:
        out.append((
            "ZenRows",
            f"https://api.zenrows.com/v1/?apikey={config.ZENROWS_KEY}&url={{u}}",
        ))
    if config.CRAWLBASE_TOKEN:
        out.append((
            "Crawlbase",
            f"https://api.crawlbase.com/?token={config.CRAWLBASE_TOKEN}&url={{u}}",
        ))
    return out


def disponible() -> bool:
    return config.PROXY_FALLBACK and bool(_fournisseurs())


async def fetch_via_proxy(url: str, *, timeout_ms: int = 45000) -> str | None:
    """
    Récupère `url` via le premier fournisseur qui répond. Retourne le corps
    (texte) ou None si tous échouent / aucun configuré.
    """
    if not disponible():
        return None
    cible = quote_plus(url)
    timeout = aiohttp.ClientTimeout(total=max(timeout_ms / 1000, 10))
    for nom, gabarit in _fournisseurs():
        url_proxy = gabarit.format(u=cible)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url_proxy) as resp:
                    if resp.status != 200:
                        logger.warning("[secours %s] HTTP %s — fournisseur suivant.",
                                       nom, resp.status)
                        continue
                    texte = await resp.text(errors="ignore")
            if texte and len(texte) >= 50:
                logger.info("[secours %s] OK pour %s", nom, url)
                return texte
            logger.warning("[secours %s] réponse vide — fournisseur suivant.", nom)
        except Exception as e:
            logger.warning("[secours %s] erreur (%s) — fournisseur suivant.", nom, e)
    logger.warning("Tous les fournisseurs de secours ont échoué pour %s", url)
    return None
