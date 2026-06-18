"""Classe de base abstraite pour les scrapers - avec bypass anti-bot avance."""
from __future__ import annotations
from typing import TYPE_CHECKING
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from urllib.parse import quote_plus
import asyncio
import logging

if TYPE_CHECKING:  # import seulement pour les annotations (pas requis à l'exécution)
    from playwright.async_api import Browser
import config
import anti_bot_bypass
from structured_data import extraire_donnees_structurees
from http_fetch import http_get

logger = logging.getLogger(__name__)

# Surchargeable via .env
MAX_RETRIES = int(config.__dict__.get("ANTIBOT_MAX_RETRIES", 3))


class ScraperBlockedError(RuntimeError):
    """Le site a retourne une page de protection au lieu du contenu attendu."""


class BaseScraper(ABC):
    # Selecteur CSS a attendre apres goto avant de capturer le HTML.
    # Chaque scraper peut le surcharger pour s'assurer que le contenu JS est charge.
    wait_selector: str | None = None

    # Delai d'attente du wait_selector sur les pages de recherche.
    search_selector_timeout: int = 15000

    # Si True : on tente d'abord une simple requete HTTP (rapide), et on ne
    # bascule sur le navigateur + anti-bot qu'en cas de blocage. A activer pour
    # les enseignes NON protegees (Auchan, La Grande Recre). Les sites blindes
    # (Cultura, King Jouet, Smyths, Leclerc) gardent False -> navigateur direct.
    http_first: bool = False

    # True si l'enseigne a BESOIN du navigateur Playwright pour fonctionner (sites
    # blindes). Les enseignes en API JSON (Leclerc, Shopify, WooCommerce) ou en
    # HTTP simple (Auchan) le mettent a False : le bot peut alors tourner SANS
    # navigateur (mode leger, ideal pour l'appli packagee). Voir main.py.
    utilise_navigateur: bool = True

    def __init__(self, enseigne: str, browser: Browser):
        self.enseigne = enseigne
        self.browser = browser
        self._last_status: str = "ok"

    async def _fetch(self, url: str, *, wait_until: str = "domcontentloaded",
                     wait_selector: str | None = None, selector_timeout: int = 10000):
        """
        Recupere une page selon la strategie de l'enseigne.

        http_first=True -> requete HTTP rapide d'abord ; si bloquee, on retombe
        sur le navigateur + anti-bot. http_first=False -> navigateur directement.
        Renvoie le triplet (html | None, statut, blocage), comme fetch_with_bypass.
        """
        if self.http_first:
            html, statut, blocage = await http_get(url, timeout_ms=config.REQUEST_TIMEOUT_MS)
            if statut == "ok":
                return html, "ok", None
            if self.browser is None:
                # Mode leger sans navigateur : pas de repli possible, on s'arrete la.
                return None, statut, blocage
            logger.debug("[%s] HTTP insuffisant (%s) -> navigateur: %s",
                         self.enseigne, blocage, url.split("?")[0])

        if self.browser is None:
            # Enseigne navigateur mais aucun navigateur dispo (ne devrait pas arriver
            # car on ne l'active pas dans ce mode) : echec propre.
            return None, "blocked", "navigateur_indisponible"

        return await anti_bot_bypass.fetch_with_bypass(
            self.browser,
            url,
            max_retries=MAX_RETRIES,
            wait_until=wait_until,
            wait_selector=wait_selector,
            selector_timeout=selector_timeout,
        )

    @abstractmethod
    def parse_page(self, soup: BeautifulSoup) -> list[dict]:
        """Extrait la liste des produits d'UNE page de resultats de recherche."""
        ...

    def search_urls(self) -> list[str]:
        """Construit une URL de recherche par mot-cle pour cette enseigne."""
        template = config.SEARCH_URL_TEMPLATES.get(self.enseigne)
        if not template:
            return [getattr(self, "url_recherche", "")]
        return [template.format(q=quote_plus(kw)) for kw in config.SEARCH_KEYWORDS]

    async def scraper_recherche(self) -> list[dict]:
        """
        Recherche tous les mots-cles en parallele, agreege et deduplique par URL.
        Les blocages repetes sont geres par la mise en veille de l'enseigne
        (cf. store_health.py), pas par une relance du navigateur partage.
        """
        logger.info("[%s] Recherche %d mots-cles...", self.enseigne, len(config.SEARCH_KEYWORDS))
        urls = [u for u in self.search_urls() if u]
        sem = asyncio.Semaphore(config.SEARCH_CONCURRENCY)

        async def fetch(url):
            async with sem:
                html, statut, blocage = await self._fetch(
                    url,
                    wait_until="domcontentloaded",
                    wait_selector=self.wait_selector,
                    selector_timeout=self.search_selector_timeout,
                )
                if html:
                    return BeautifulSoup(html, "html.parser"), statut, blocage
                return None, statut, blocage

        resultats = await asyncio.gather(*(fetch(u) for u in urls))

        produits, vus, statuts = [], set(), []
        for soup, statut, blocage in resultats:
            statuts.append(statut)
            if not soup:
                if blocage:
                    logger.warning("[%s] Bloque par %s sur une requete.", self.enseigne, blocage)
                continue
            try:
                for prod in self.parse_page(soup):
                    url = prod.get("url", "")
                    if url and url not in vus:
                        vus.add(url)
                        produits.append(prod)
            except Exception as e:
                logger.warning("[%s] Erreur parse_page: %s", self.enseigne, e)

        if "ok" in statuts:
            self._last_status = "ok"
        elif "blocked" in statuts:
            self._last_status = "blocked"
        else:
            self._last_status = "timeout"

        logger.info("[%s] %d produits uniques (%d requetes, statut: %s).",
                    self.enseigne, len(produits), len(urls), self._last_status)
        return produits

    async def _fetch_soup(self, url: str, *, wait_until: str = "domcontentloaded",
                          wait_selector: str | None = None, selector_timeout: int = 8000):
        """
        Charge une page avec le systeme de bypass anti-bot complet.
        Retourne (soup, statut) sans etat partage - sur en parallele.
        statut: "ok" | "blocked" | "timeout".
        """
        html, statut, blocage = await self._fetch(
            url,
            wait_until=wait_until,
            wait_selector=wait_selector,
            selector_timeout=selector_timeout,
        )
        if html is None:
            return None, statut
        return BeautifulSoup(html, "html.parser"), statut

    async def scraper_produit(self, url: str) -> dict:
        """
        Verifie stock/prix/image d'une URL produit connue.

        Priorite aux donnees structurees schema.org (JSON-LD + microdata), qui
        sont communes a tous les sites et robustes. Les selecteurs CSS ne servent
        que de secours quand une info manque. Le bypass anti-bot gere le chargement.
        Retourne toujours un dict avec 'status' ("ok"/"blocked"/"timeout").
        """
        html, statut, _ = await self._fetch(url)
        if html is None:
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}

        soup = BeautifulSoup(html, "html.parser")
        data = extraire_donnees_structurees(html)

        # --- Stock : donnees structurees, sinon heuristique CSS ---
        en_stock = data.get("in_stock")
        if en_stock is None:
            indispo = soup.select_one(
                ".out-of-stock, .rupture, .indisponible, "
                "[class*=out-of-stock], [class*=unavailable]"
            )
            btn = soup.select_one(
                "button.add-to-cart, [data-button-action='add-to-cart'], "
                "[class*=add-to-cart], [class*=btn-basket]"
            )
            en_stock = bool(btn and not indispo)

        # --- Prix : structure, sinon CSS ---
        prix = data.get("price")
        if not prix:
            prix_el = soup.select_one(
                ".price, .product-price, span[itemprop='price'], [class*=price]"
            )
            prix = prix_el.get_text(strip=True) if prix_el else "N/A"

        # --- Image : structure, sinon og:image ---
        image_url = data.get("image_url", "")
        if not image_url:
            img_meta = soup.select_one("meta[itemprop='image'], meta[property='og:image']")
            image_url = img_meta.get("content", "") if img_meta else ""

        return {
            "status": "ok",
            "en_stock": bool(en_stock),
            "prix": prix,
            "image_url": image_url,
            "ean": data.get("ean", ""),
            "brand": data.get("brand", ""),
            "seller": data.get("seller", ""),
            "reference": data.get("sku", ""),
            "stock_quantity": data.get("stock_quantity"),
            "rating": data.get("rating", ""),
        }

    @asynccontextmanager
    async def get_page_soup(self, url: str):
        """Deprecated - utilise _fetch_soup a la place. Conserve pour compatibilite."""
        html, statut, blocage = await self._fetch(
            url,
            wait_until="networkidle",
            wait_selector=self.wait_selector,
            selector_timeout=15000,
        )

        if statut == "blocked":
            logger.warning("[%s] Site bloque (%s). Anti-bot bypass actif.", self.enseigne, blocage or "inconnu")
            self._last_status = "blocked"
            yield None, None
            return

        if html is None:
            logger.warning("[%s] Erreur chargement %s (timeout).", self.enseigne, url)
            self._last_status = "timeout"
            yield None, None
            return

        self._last_status = "ok"

        # Creer un contexte minimal pour compatibilite ascendante
        context = await self.browser.new_context(
            user_agent=anti_bot_bypass.choisir_user_agent()
        )
        page_virtuelle = await context.new_page()

        try:
            yield page_virtuelle, BeautifulSoup(html, "html.parser")
        finally:
            try:
                await context.close()
            except Exception:
                pass