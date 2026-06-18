"""
http_fetch.py - Recuperation HTTP legere (sans navigateur).

Pour les sites NON proteges (ex. Auchan, La Grande Recre), une simple requete
HTTP suffit : c'est ~50x plus rapide qu'un navigateur Playwright et ca casse
rarement. On reserve le navigateur + anti-bot aux sites blindes (fallback).

http_get() renvoie le meme triplet que anti_bot_bypass.fetch_with_bypass :
    (html | None, statut, blocage)
  - ("<html>", "ok", None)        : page recuperee, semble normale
  - (None, "blocked", "<raison>") : protection / page vide
  - (None, "timeout", "<raison>") : timeout ou erreur reseau
Ainsi http_get est interchangeable avec le fetch navigateur.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import random
from typing import Optional

import aiohttp

from anti_bot_bypass import detecter_type_blocage

logger = logging.getLogger("http_fetch")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]

# Codes HTTP typiques d'un blocage anti-bot.
_CODES_BLOQUES = {401, 403, 405, 429, 451, 503}

# Codes de throttling temporaire : on RÉESSAIE (avec attente) au lieu d'abandonner.
# Beaucoup d'enseignes (ex. Leclerc) répondent 429/503 quand on enchaîne trop de
# requêtes d'un coup, mais acceptent si on patiente une seconde.
_CODES_THROTTLE = {429, 503}
_MAX_RETRIES_THROTTLE = 2


async def _get_avec_backoff(session, url):
    """
    GET en respectant le throttling : sur 429/503, attend (Retry-After si fourni,
    sinon court backoff) puis réessaie. Retourne (status_code, texte | None).
    """
    for tentative in range(_MAX_RETRIES_THROTTLE + 1):
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status in _CODES_THROTTLE and tentative < _MAX_RETRIES_THROTTLE:
                entete = resp.headers.get("Retry-After")
                delai = None
                if entete:
                    try:
                        delai = min(float(entete), 8.0)
                    except ValueError:
                        delai = None
                if delai is None:
                    delai = 1.2 * (tentative + 1) + random.uniform(0, 0.6)
                logger.debug("Throttle %s sur %s — pause %.1fs (essai %d).",
                             resp.status, url, delai, tentative + 1)
                await asyncio.sleep(delai)
                continue
            return resp.status, await resp.text(errors="ignore")
    return resp.status, None  # dernier essai encore throttlé


def _headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        # On ne demande pas 'br' : aiohttp ne sait decoder brotli que si la lib
        # brotli est installee. gzip/deflate sont gérés nativement.
        "Accept-Encoding": "gzip, deflate",
        "Sec-Ch-Ua": '"Chromium";v="136", "Google Chrome";v="136", "Not?A_Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


async def http_get(url: str, *, timeout_ms: int = 30000) -> tuple[Optional[str], str, Optional[str]]:
    """Recupere une page en HTTP simple. Voir l'en-tete du module pour le format."""
    timeout = aiohttp.ClientTimeout(total=max(timeout_ms / 1000, 5))
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=_headers()) as session:
            status, html = await _get_avec_backoff(session, url)
            if status in _CODES_BLOQUES:
                return await _secours_html(url, f"http_{status}")
            if status >= 400 or html is None:
                return None, "timeout", f"http_{status}"
    except asyncio.TimeoutError:
        return None, "timeout", "timeout"
    except aiohttp.ClientError as e:
        logger.debug("Erreur HTTP %s: %s", url, e)
        return None, "timeout", "network_error"

    if not html or len(html) < 200:
        return await _secours_html(url, "empty")

    blocage = detecter_type_blocage(html)
    if blocage:
        return await _secours_html(url, blocage)

    return html, "ok", None


async def _secours_html(url: str, blocage: str):
    """Dernier recours : tente via un proxy anti-bot, sinon renvoie 'blocked'."""
    from proxy_fetch import fetch_via_proxy, disponible
    if disponible():
        texte = await fetch_via_proxy(url)
        if texte and len(texte) >= 200 and not detecter_type_blocage(texte):
            return texte, "ok", None
    return None, "blocked", blocage


async def http_get_json(url: str, *, timeout_ms: int = 30000,
                        headers: Optional[dict] = None) -> tuple[Optional[object], str, Optional[str]]:
    """
    Variante JSON : renvoie (data, statut, blocage) pour une API JSON.
    Utilisée par les enseignes exposant une vraie API (ex. Leclerc).
    """
    h = {"User-Agent": random.choice(_USER_AGENTS),
         "Accept": "application/json, text/plain, */*",
         "Accept-Language": "fr-FR,fr;q=0.9"}
    if headers:
        h.update(headers)
    timeout = aiohttp.ClientTimeout(total=max(timeout_ms / 1000, 5))
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=h) as session:
            status, texte = await _get_avec_backoff(session, url)
            if status in _CODES_BLOQUES:
                return await _secours_json(url, f"http_{status}")
            if status >= 400 or texte is None:
                return None, "timeout", f"http_{status}"
    except asyncio.TimeoutError:
        return None, "timeout", "timeout"
    except aiohttp.ClientError as e:
        logger.debug("Erreur HTTP JSON %s: %s", url, e)
        return None, "timeout", "network_error"

    try:
        return _json.loads(texte), "ok", None
    except (ValueError, TypeError):
        # Pas du JSON => probablement une page de challenge anti-bot.
        return await _secours_json(url, "not_json")


async def _secours_json(url: str, blocage: str):
    """Dernier recours JSON : tente via un proxy anti-bot puis parse le JSON."""
    from proxy_fetch import fetch_via_proxy, disponible
    if disponible():
        texte = await fetch_via_proxy(url)
        if texte:
            try:
                return _json.loads(texte), "ok", None
            except (ValueError, TypeError):
                pass
    return None, "blocked", blocage
