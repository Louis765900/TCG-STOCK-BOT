"""
anti_bot_bypass.py - Couche d'evasion anti-bot pour TCG-STOCK-BOT.

Objectif honnete : reduire le taux de blocage sur les sites e-commerce en
presentant un navigateur Chrome credible et un comportement humain, pas
"casser" DataDome/Cloudflare (qui s'appuient surtout sur le fingerprint TLS
serveur et du ML comportemental qu'un patch JS ne defait pas).

Ce qui est reellement fait ici :
  1. Une IDENTITE coherente par contexte : l'User-Agent, les Client Hints
     (Sec-CH-UA), la plateforme, le hardware (cores/RAM) et le GPU WebGL
     racontent tous la MEME histoire. L'incoherence est le 1er signal de bot.
  2. Masquage des marqueurs d'automatisation (navigator.webdriver, etc.).
  3. Comportement humain leger : delais, scroll, mouvements souris.
  4. Reutilisation des cookies de session par domaine (evite de redeclencher
     un challenge a chaque requete).
  5. Retries avec escalade douce : nouvelle identite, eventuel proxy, et
     "amorcage" de la page d'accueil pour recolter les cookies avant la cible.

API publique (utilisee par scrapers/base_scraper.py) :
  - CHROMIUM_ARGS : liste d'arguments de lancement Chromium.
  - fetch_with_bypass(browser, url, ...) -> (html|None, statut, blocage)
  - choisir_user_agent() -> str
  - creer_contexte_stealth(...) / detecter_type_blocage(...) / sleep_humain(...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("anti_bot")

# =============================================================================
# POOL D'IDENTITES (Chrome recent sur Windows uniquement)
# -----------------------------------------------------------------------------
# On ne melange QUE des Chrome : le navigateur reel est Chromium, donc annoncer
# un UA Firefox/Safari creerait une incoherence moteur immediate.
# =============================================================================

CHROME_VERSIONS = ["131", "132", "133", "134", "135", "136"]

# Couples (vendor, renderer) WebGL realistes et coherents entre eux.
WEBGL_CARDS = [
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)",
     "ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1600, "height": 900},
    {"width": 1680, "height": 1050},
]

# Tailles d'ecran physiques credibles (>= viewport visible).
SCREENS = [
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
    {"width": 1536, "height": 864},
    {"width": 1366, "height": 768},
]

HARDWARE_CONCURRENCY = [4, 8, 8, 12, 16]
DEVICE_MEMORY = [8, 8, 16]

FR_LOCALE = "fr-FR"
FR_TIMEZONE = "Europe/Paris"
FR_GEO = {"latitude": 48.8566, "longitude": 2.3522}
ACCEPT_LANGUAGE = "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"


def _ua_for_version(version: str) -> str:
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"
    )


USER_AGENTS = [_ua_for_version(v) for v in CHROME_VERSIONS]


# =============================================================================
# ARGUMENTS CHROMIUM
# -----------------------------------------------------------------------------
# Set volontairement minimal et SUR. On NE desactive PAS le GPU (sinon le
# fingerprint WebGL spoofe devient incoherent) et on NE desactive PAS la
# securite web (dangereux pour la machine, et detectable).
# =============================================================================

CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--no-service-autorun",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--disable-translate",
    "--disable-popup-blocking",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-pings",
]


# =============================================================================
# IDENTITE COHERENTE
# =============================================================================

def choisir_user_agent() -> str:
    """Retourne un User-Agent Chrome/Windows aleatoire (compat base_scraper)."""
    return random.choice(USER_AGENTS)


def _nouvelle_identite() -> dict:
    """
    Genere un profil de navigateur entierement coherent : tous les champs
    derivent de la meme version de Chrome et du meme materiel.
    """
    version = random.choice(CHROME_VERSIONS)
    vendor, renderer = random.choice(WEBGL_CARDS)
    return {
        "ua": _ua_for_version(version),
        "chrome_major": version,
        "viewport": random.choice(VIEWPORTS),
        "screen": random.choice(SCREENS),
        "hardware_concurrency": random.choice(HARDWARE_CONCURRENCY),
        "device_memory": random.choice(DEVICE_MEMORY),
        "webgl_vendor": vendor,
        "webgl_renderer": renderer,
    }


def _client_hints(chrome_major: str) -> str:
    """Construit l'en-tete Sec-CH-UA au format reel (version MAJEURE seule)."""
    return (
        f'"Chromium";v="{chrome_major}", '
        f'"Google Chrome";v="{chrome_major}", '
        f'"Not?A_Brand";v="99"'
    )


def _headers(ident: dict) -> dict:
    return {
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,image/apng,*/*;q=0.8,"
                   "application/signed-exchange;v=b3;q=0.7"),
        "Accept-Language": ACCEPT_LANGUAGE,
        "Sec-Ch-Ua": _client_hints(ident["chrome_major"]),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


# =============================================================================
# SCRIPT STEALTH
# -----------------------------------------------------------------------------
# Injecte AVANT le chargement de toute page. Lit __antibot_cfg (valeurs figees
# par contexte : pas de Math.random() dans les getters, qui serait un signal
# de bot car une vraie valeur materielle est stable).
# =============================================================================

_STEALTH_BODY = r"""
(() => {
    const cfg = window.__antibot_cfg || {};

    const define = (obj, prop, value) => {
        try {
            Object.defineProperty(obj, prop, { get: () => value, configurable: true });
        } catch (e) { /* deja non-configurable : on laisse */ }
    };

    // 1. navigator.webdriver === false (valeur d'un vrai Chrome non automatise)
    define(navigator, 'webdriver', false);

    // 2. Hardware coherent avec l'identite (valeurs FIXES, pas aleatoires)
    if (cfg.hardware_concurrency) define(navigator, 'hardwareConcurrency', cfg.hardware_concurrency);
    if (cfg.device_memory) define(navigator, 'deviceMemory', cfg.device_memory);
    define(navigator, 'maxTouchPoints', 0);

    // 3. Langues
    define(navigator, 'languages', ['fr-FR', 'fr', 'en-US', 'en']);

    // 4. Plugins / mimeTypes : shim PDF d'un Chrome reel
    const mkPlugin = (name, filename, desc) => {
        const p = { name, filename, description: desc, length: 1 };
        p[0] = { type: 'application/pdf', suffixes: 'pdf', description: desc };
        return p;
    };
    const plugins = [
        mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
    ];
    define(navigator, 'plugins', plugins);
    define(navigator, 'mimeTypes', [
        { type: 'application/pdf', suffixes: 'pdf', description: '' },
        { type: 'text/pdf', suffixes: 'pdf', description: '' },
    ]);

    // 5. Permissions : 'notifications' doit refleter Notification.permission
    if (navigator.permissions && navigator.permissions.query) {
        const orig = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (desc) => {
            if (desc && desc.name === 'notifications') {
                return Promise.resolve({
                    state: (window.Notification && Notification.permission) || 'default',
                    onchange: null,
                });
            }
            return orig(desc);
        };
    }

    // 6. WebGL : vendor/renderer coherents (UNMASKED_VENDOR=37445, RENDERER=37446)
    const patchGL = (proto) => {
        if (!proto) return;
        const orig = proto.getParameter;
        proto.getParameter = function (param) {
            if (param === 37445 && cfg.webgl_vendor) return cfg.webgl_vendor;
            if (param === 37446 && cfg.webgl_renderer) return cfg.webgl_renderer;
            return orig.call(this, param);
        };
    };
    patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
    patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);

    // 7. window.chrome : objet present sur un vrai Chrome
    if (!window.chrome) {
        Object.defineProperty(window, 'chrome', { value: {}, configurable: true });
    }
    if (!window.chrome.runtime) {
        try { window.chrome.runtime = {}; } catch (e) {}
    }
})();
"""


def _build_init_script(ident: dict) -> str:
    cfg = {
        "hardware_concurrency": ident["hardware_concurrency"],
        "device_memory": ident["device_memory"],
        "webgl_vendor": ident["webgl_vendor"],
        "webgl_renderer": ident["webgl_renderer"],
    }
    return f"window.__antibot_cfg = {json.dumps(cfg)};\n{_STEALTH_BODY}"


# =============================================================================
# PROXY POOL (optionnel, via env PROXY_LIST = JSON array)
# =============================================================================

def _charger_proxies() -> list:
    raw = os.getenv("PROXY_LIST", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [p for p in data if isinstance(p, str) and p]
    except (json.JSONDecodeError, TypeError):
        logger.warning("PROXY_LIST mal formatee (JSON array attendu), ignoree.")
    return []


PROXY_POOL = _charger_proxies()


def choisir_proxy() -> Optional[str]:
    return random.choice(PROXY_POOL) if PROXY_POOL else None


# =============================================================================
# PERSISTANCE DES COOKIES DE SESSION (par domaine, en memoire, TTL 15 min)
# =============================================================================

_SESSION_TTL = 900  # secondes
_SESSION_STORE: dict[str, dict] = {}


def _domaine(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def sauvegarder_cookies(domain: str, cookies: list) -> None:
    if cookies:
        _SESSION_STORE[domain] = {"cookies": cookies, "ts": time.time()}
        logger.debug("Cookies memorises pour %s (%d).", domain, len(cookies))


def charger_cookies(domain: str) -> Optional[list]:
    entry = _SESSION_STORE.get(domain)
    if entry and (time.time() - entry["ts"]) < _SESSION_TTL:
        return entry["cookies"]
    _SESSION_STORE.pop(domain, None)
    return None


# =============================================================================
# DETECTION DE BLOCAGE
# =============================================================================

BLOCK_PATTERNS = {
    "datadome": ["datadome", "geo.captcha-delivery.com", "interstitial.captcha"],
    "cloudflare": ["cf-challenge", "challenge-platform", "__cf_chl", "cf-mitigated",
                   "checking your browser before"],
    "imperva": ["incapsula", "_incapsula_", "imperva"],
    "akamai": ["ak_bmsc", "_abck", "akamai bot manager"],
    "captcha": ["recaptcha", "hcaptcha", "g-recaptcha", "h-captcha", "funcaptcha", "geetest"],
    "generic_bot": [
        "verify you are human", "access denied", "you have been blocked",
        "automated access", "please confirm you are human", "unusual traffic",
        "detected unusual activity", "request blocked",
    ],
}


def detecter_type_blocage(html: Optional[str]) -> Optional[str]:
    """Identifie l'anti-bot a partir du HTML, ou None si la page semble normale."""
    if not html or not html.strip():
        return "empty"
    low = html.lower()
    # Une vraie page de resultats contient generalement beaucoup de contenu ;
    # une page de challenge est courte. On exige aussi un motif connu.
    for block_type, patterns in BLOCK_PATTERNS.items():
        if any(p in low for p in patterns):
            return block_type
    return None


# =============================================================================
# COMPORTEMENT HUMAIN
# =============================================================================

async def sleep_humain(min_s: float = 0.5, max_s: float = 2.0) -> None:
    await asyncio.sleep(min_s + random.random() * (max_s - min_s))


async def _mouvements_souris(page: Page) -> None:
    try:
        for _ in range(random.randint(2, 4)):
            await page.mouse.move(
                random.randint(80, 900), random.randint(80, 600),
                steps=random.randint(5, 12),
            )
            await asyncio.sleep(0.04 + random.random() * 0.12)
    except Exception:
        pass


async def _scroll_naturel(page: Page, intensite: float = 1.0) -> None:
    try:
        steps = random.randint(5, 12)
        for _ in range(steps):
            await page.mouse.wheel(0, random.randint(120, 320) * intensite)
            await asyncio.sleep(0.05 + random.random() * 0.18)
        if random.random() < 0.3:
            await page.mouse.wheel(0, -random.randint(80, 220))
    except Exception:
        pass


# =============================================================================
# CREATION DU CONTEXTE STEALTH
# =============================================================================

async def creer_contexte_stealth(
    browser: Browser,
    *,
    identite: Optional[dict] = None,
    proxy: Optional[str] = None,
    seed_cookies: Optional[list] = None,
    extra_headers: Optional[dict] = None,
    user_agent: Optional[str] = None,
) -> tuple[BrowserContext, dict]:
    """
    Cree un BrowserContext avec une identite coherente et le script stealth.
    Retourne (context, identite). `user_agent` force l'UA (compat ascendante).
    """
    ident = identite or _nouvelle_identite()
    if user_agent:
        ident = dict(ident)
        ident["ua"] = user_agent
        m = re.search(r"Chrome/(\d+)", user_agent)
        if m:
            ident["chrome_major"] = m.group(1)

    ctx_opts: dict = {
        "user_agent": ident["ua"],
        "viewport": ident["viewport"],
        "screen": ident["screen"],
        "locale": FR_LOCALE,
        "timezone_id": FR_TIMEZONE,
        "geolocation": FR_GEO,
        "permissions": ["geolocation"],
        "color_scheme": "light",
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "extra_http_headers": _headers(ident),
    }
    if extra_headers:
        ctx_opts["extra_http_headers"].update(extra_headers)
    if proxy:
        ctx_opts["proxy"] = {"server": proxy}

    context = await browser.new_context(**ctx_opts)
    await context.add_init_script(_build_init_script(ident))

    if seed_cookies:
        try:
            await context.add_cookies(seed_cookies)
        except Exception as e:
            logger.debug("Injection cookies ignoree: %s", e)

    return context, ident


# =============================================================================
# FETCH AVEC BYPASS
# =============================================================================

# Escalade douce : a chaque tentative on durcit un peu la strategie.
def _strategie(tentative: int) -> dict:
    return {
        # On amorce la page d'accueil (meme domaine) des la 2e tentative :
        # technique legitime et efficace pour recolter les cookies de session.
        "amorcer_accueil": tentative >= 2,
        # Le proxy n'entre en jeu qu'a partir de la 3e tentative (s'il existe).
        "use_proxy": tentative >= 3 and bool(PROXY_POOL),
    }


async def fetch_with_bypass(
    browser: Browser,
    url: str,
    max_retries: int = 5,
    *,
    wait_until: str = "domcontentloaded",
    wait_selector: Optional[str] = None,
    selector_timeout: int = 10000,
    timeout_ms: Optional[int] = None,
    force_session_reuse: bool = True,
    **_ignore,
) -> tuple[Optional[str], str, Optional[str]]:
    """
    Charge `url` avec retries et escalade anti-bot.

    Retourne (html, statut, blocage) :
      - ("<html>", "ok", None)            -> succes
      - (None, "blocked", "<type>")       -> page de protection detectee
      - (None, "timeout", "<raison>")     -> timeout / erreur reseau
    """
    from config import REQUEST_TIMEOUT_MS

    timeout = timeout_ms or REQUEST_TIMEOUT_MS
    domain = _domaine(url)
    base_url = re.match(r"(https?://[^/]+)", url)
    base_url = base_url.group(1) if base_url else None
    dernier_blocage: Optional[str] = None
    statut_final = "timeout"

    for tentative in range(1, max_retries + 1):
        strat = _strategie(tentative)
        proxy = choisir_proxy() if strat["use_proxy"] else None

        seed = charger_cookies(domain) if (force_session_reuse and tentative == 1) else None

        logger.debug("Tentative %d/%d %s (proxy=%s)",
                     tentative, max_retries, url.split("?")[0], bool(proxy))

        context = None
        try:
            context, _ident = await creer_contexte_stealth(
                browser, proxy=proxy, seed_cookies=seed,
            )
            page = await context.new_page()
            await sleep_humain(0.6, 1.8)

            # Amorcage de la page d'accueil pour recolter les cookies anti-bot.
            if strat["amorcer_accueil"] and base_url and base_url not in url.rstrip("/"):
                try:
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=timeout)
                    await sleep_humain(1.0, 2.5)
                    await _scroll_naturel(page, 0.4)
                except Exception:
                    pass

            await page.goto(url, wait_until=wait_until, timeout=timeout)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=selector_timeout)
                except Exception:
                    pass

            await sleep_humain(0.4, 1.2)
            await _scroll_naturel(page, 0.6)
            await _mouvements_souris(page)

            html = await page.content()
            blocage = detecter_type_blocage(html)

            # Sur challenge JS (DataDome/Cloudflare), le cookie tombe parfois
            # apres un court delai : on attend et on recharge une fois.
            if blocage in ("datadome", "cloudflare") and tentative < max_retries:
                await sleep_humain(3.0, 5.0)
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=timeout)
                    await sleep_humain(0.5, 1.5)
                    html = await page.content()
                    blocage = detecter_type_blocage(html)
                except Exception:
                    pass

            if blocage:
                dernier_blocage = blocage
                statut_final = "blocked"
                logger.warning("Tentative %d bloquee (%s) sur %s.",
                               tentative, blocage, url.split("?")[0])
                await sleep_humain(1.5, 4.0)
                continue

            # Succes : on memorise les cookies pour les requetes suivantes.
            try:
                sauvegarder_cookies(domain, await context.cookies())
            except Exception:
                pass

            return html, "ok", None

        except Exception as e:
            err = str(e).lower()
            if "timeout" in err:
                dernier_blocage = "timeout"
            elif "net::" in err or "err_" in err:
                dernier_blocage = "network_error"
            elif "closed" in err:
                dernier_blocage = "context_closed"
            else:
                dernier_blocage = "error"
            statut_final = "timeout"
            logger.debug("Tentative %d erreur (%s): %s", tentative, dernier_blocage, e)
            await sleep_humain(1.5, 3.5)
            continue

        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    return None, statut_final, dernier_blocage
