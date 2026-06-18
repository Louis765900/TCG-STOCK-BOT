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

# curl_cffi imite l'empreinte TLS/JA3 + HTTP2 d'un vrai Chrome : beaucoup de
# protections (DataDome, Cloudflare) ne voient plus un "bot Python". On l'utilise
# en PRIORITÉ ; si indisponible/en échec, on retombe sur aiohttp (comportement
# historique). Voir _fetch_once.
try:
    from curl_cffi.requests import AsyncSession as _CurlSession
    _CURL_OK = True
except Exception:  # pragma: no cover - curl_cffi absent
    _CURL_OK = False

# Profil de navigateur imité par curl_cffi (alias glissant vers un Chrome récent).
_IMPERSONATE = "chrome"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]

_ACCEPT_HTML = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8")
_ACCEPT_JSON = "application/json, text/plain, */*"
_ACCEPT_LANG = "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"

# Codes HTTP typiques d'un blocage anti-bot.
_CODES_BLOQUES = {401, 403, 405, 429, 451, 503}

# Codes de throttling temporaire : on RÉESSAIE (avec attente) au lieu d'abandonner.
# Beaucoup d'enseignes (ex. Leclerc) répondent 429/503 quand on enchaîne trop de
# requêtes d'un coup, mais acceptent si on patiente une seconde.
_CODES_THROTTLE = {429, 503}
_MAX_RETRIES_THROTTLE = 2


def _headers_aiohttp(accept: str) -> dict:
    """En-têtes navigateur pour le repli aiohttp (curl_cffi gère les siens)."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": accept,
        "Accept-Language": _ACCEPT_LANG,
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


async def _fetch_once(url: str, accept: str, extra: Optional[dict], timeout_s: float):
    """
    Un GET. Retourne (status_code, texte, headers_dict).

    curl_cffi (impersonation Chrome) en priorité ; repli aiohttp en cas
    d'indisponibilité ou d'erreur.
    """
    if _CURL_OK:
        try:
            entetes = {"Accept": accept, "Accept-Language": _ACCEPT_LANG}
            if extra:
                entetes.update(extra)
            async with _CurlSession() as s:
                r = await s.get(url, headers=entetes, impersonate=_IMPERSONATE,
                                timeout=timeout_s, allow_redirects=True)
                return r.status_code, r.text, dict(r.headers)
        except Exception as e:  # repli silencieux sur aiohttp
            logger.debug("curl_cffi échec (%s) → repli aiohttp pour %s", e, url)

    h = _headers_aiohttp(accept)
    if extra:
        h.update(extra)
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=h, allow_redirects=True) as resp:
            return resp.status, await resp.text(errors="ignore"), dict(resp.headers)


async def _fetch_avec_backoff(url: str, accept: str, extra: Optional[dict], timeout_s: float):
    """GET avec retry sur throttling 429/503 (respecte Retry-After). (status, texte|None)."""
    status, texte = 0, None
    for tentative in range(_MAX_RETRIES_THROTTLE + 1):
        status, texte, hdrs = await _fetch_once(url, accept, extra, timeout_s)
        if status in _CODES_THROTTLE and tentative < _MAX_RETRIES_THROTTLE:
            entete = hdrs.get("Retry-After") or hdrs.get("retry-after")
            delai = None
            if entete:
                try:
                    delai = min(float(entete), 8.0)
                except ValueError:
                    delai = None
            if delai is None:
                delai = 1.2 * (tentative + 1) + random.uniform(0, 0.6)
            logger.debug("Throttle %s sur %s — pause %.1fs (essai %d).",
                         status, url, delai, tentative + 1)
            await asyncio.sleep(delai)
            continue
        return status, texte
    return status, None  # dernier essai encore throttlé


async def http_get(url: str, *, timeout_ms: int = 30000) -> tuple[Optional[str], str, Optional[str]]:
    """Recupere une page en HTTP simple. Voir l'en-tete du module pour le format."""
    timeout_s = max(timeout_ms / 1000, 5)
    try:
        status, html = await _fetch_avec_backoff(url, _ACCEPT_HTML, None, timeout_s)
    except asyncio.TimeoutError:
        return None, "timeout", "timeout"
    except Exception as e:
        logger.debug("Erreur HTTP %s: %s", url, e)
        return None, "timeout", "network_error"

    if status in _CODES_BLOQUES:
        return await _secours_html(url, f"http_{status}")
    if status >= 400 or html is None:
        return None, "timeout", f"http_{status}"
    if len(html) < 200:
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
    timeout_s = max(timeout_ms / 1000, 5)
    try:
        status, texte = await _fetch_avec_backoff(url, _ACCEPT_JSON, headers, timeout_s)
    except asyncio.TimeoutError:
        return None, "timeout", "timeout"
    except Exception as e:
        logger.debug("Erreur HTTP JSON %s: %s", url, e)
        return None, "timeout", "network_error"

    if status in _CODES_BLOQUES:
        return await _secours_json(url, f"http_{status}")
    if status >= 400 or texte is None:
        return None, "timeout", f"http_{status}"

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
