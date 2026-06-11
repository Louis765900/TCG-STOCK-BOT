"""Classe de base abstraite pour les scrapers."""
from playwright.async_api import Browser, Page
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from urllib.parse import quote_plus
import asyncio
import logging
import config

logger = logging.getLogger(__name__)

try:
    from playwright_stealth import Stealth
    _STEALTH = Stealth()
except Exception:
    _STEALTH = None

BLOCAGES = (
    "datadome", "captcha-delivery", "captcha", "incapsula", "imperva",
    "verify you are human", "access denied", "cloudflare", "bot protection",
)


class ScraperBlockedError(RuntimeError):
    """Le site a retourne une page de protection au lieu du contenu attendu."""


class BaseScraper(ABC):
    # Sélecteur CSS à attendre après goto avant de capturer le HTML.
    # Chaque scraper peut le surcharger pour s'assurer que le contenu JS est chargé.
    wait_selector: str | None = None

    # Délai d'attente du wait_selector sur les pages de recherche.
    search_selector_timeout: int = 15000

    def __init__(self, enseigne: str, browser: Browser):
        self.enseigne = enseigne
        self.browser = browser
        self._last_status: str = "ok"

    @abstractmethod
    def parse_page(self, soup: BeautifulSoup) -> list[dict]:
        """Extrait la liste des produits d'UNE page de résultats de recherche."""
        ...

    def search_urls(self) -> list[str]:
        """Construit une URL de recherche par mot-clé pour cette enseigne."""
        template = config.SEARCH_URL_TEMPLATES.get(self.enseigne)
        if not template:
            return [getattr(self, "url_recherche", "")]
        return [template.format(q=quote_plus(kw)) for kw in config.SEARCH_KEYWORDS]

    async def scraper_recherche(self) -> list[dict]:
        """
        Recherche tous les mots-clés en parallèle, agrège et déduplique par URL.
        Met à jour self._last_status (ok si au moins une page a répondu).
        """
        logger.info("[%s] Recherche %d mots-clés...", self.enseigne, len(config.SEARCH_KEYWORDS))
        urls = [u for u in self.search_urls() if u]
        sem = asyncio.Semaphore(config.SEARCH_CONCURRENCY)

        async def fetch(url):
            async with sem:
                return await self._fetch_soup(
                    url, wait_until="networkidle",
                    wait_selector=self.wait_selector,
                    selector_timeout=self.search_selector_timeout,
                )

        resultats = await asyncio.gather(*(fetch(u) for u in urls))

        produits, vus, statuts = [], set(), []
        for soup, statut in resultats:
            statuts.append(statut)
            if not soup:
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

        logger.info("[%s] %d produits uniques (%d requêtes, statut: %s).",
                    self.enseigne, len(produits), len(urls), self._last_status)
        return produits

    async def _fetch_soup(self, url: str, *, wait_until: str = "domcontentloaded",
                          wait_selector: str | None = None, selector_timeout: int = 8000):
        """
        Charge une page et renvoie (soup, statut) sans état partagé — sûr en parallèle.
        statut: "ok" | "blocked" | "timeout". Plus léger que get_page_soup (pas de
        networkidle par défaut), pensé pour les vérifications de fiches produit.
        """
        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        try:
            if _STEALTH:
                await _STEALTH.apply_stealth_async(page)
            await page.goto(url, wait_until=wait_until, timeout=config.REQUEST_TIMEOUT_MS)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=selector_timeout)
                except Exception:
                    pass
            html = await page.content()
            if any(mot in html.lower() for mot in BLOCAGES):
                return None, "blocked"
            return BeautifulSoup(html, "html.parser"), "ok"
        except Exception as e:
            logger.debug("[%s] _fetch_soup erreur sur %s: %s", self.enseigne, url, e)
            return None, "timeout"
        finally:
            try:
                await context.close()
            except Exception:
                pass

    async def scraper_produit(self, url: str) -> dict:
        """
        Vérifie stock/prix/image d'une URL produit connue via schema.org + sélecteurs
        génériques. Retourne toujours un dict avec 'status' ("ok"/"blocked"/"timeout").
        """
        soup, statut = await self._fetch_soup(url)
        if soup is None:
            return {"status": statut, "en_stock": False, "prix": "N/A", "image_url": ""}

        avail_meta = soup.select_one("meta[itemprop='availability']")
        if avail_meta:
            en_stock = "instock" in avail_meta.get("content", "").lower()
        else:
            indispo = soup.select_one(
                ".out-of-stock, .rupture, .indisponible, "
                "[class*=out-of-stock], [class*=unavailable]"
            )
            btn = soup.select_one(
                "button.add-to-cart, [data-button-action='add-to-cart'], "
                "[class*=add-to-cart], [class*=btn-basket]"
            )
            en_stock = bool(btn and not indispo)

        prix_meta = soup.select_one("meta[itemprop='price']")
        if prix_meta and prix_meta.get("content"):
            prix = prix_meta.get("content") + "€"
        else:
            prix_el = soup.select_one(
                ".price, .product-price, span[itemprop='price'], [class*=price]"
            )
            prix = prix_el.get_text(strip=True) if prix_el else "N/A"

        img_meta = soup.select_one("meta[itemprop='image'], meta[property='og:image']")
        image_url = img_meta.get("content", "") if img_meta else ""

        return {"status": "ok", "en_stock": en_stock, "prix": prix, "image_url": image_url}

    @asynccontextmanager
    async def get_page_soup(self, url: str):
        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            if _STEALTH:
                await _STEALTH.apply_stealth_async(page)

            await page.goto(url, wait_until="networkidle", timeout=config.REQUEST_TIMEOUT_MS)

            if self.wait_selector:
                try:
                    await page.wait_for_selector(self.wait_selector, timeout=15000)
                except Exception:
                    logger.debug(
                        "[%s] wait_selector '%s' non trouvé dans les délais.",
                        self.enseigne, self.wait_selector,
                    )

            html = await page.content()
            html_lower = html.lower()

            if any(mot in html_lower for mot in BLOCAGES):
                raise ScraperBlockedError(
                    f"[{self.enseigne}] Accès bloqué par protection anti-bot"
                )

            self._last_status = "ok"
            yield page, BeautifulSoup(html, "html.parser")

        except ScraperBlockedError:
            logger.warning(
                "[%s] Site bloqué (anti-bot). Stealth actif: %s",
                self.enseigne, _STEALTH is not None,
            )
            self._last_status = "blocked"
            yield page, None

        except Exception as e:
            logger.warning("[%s] Erreur chargement %s: %s", self.enseigne, url, e)
            self._last_status = "timeout"
            yield page, None

        finally:
            try:
                await context.close()
            except Exception as e:
                logger.debug("[%s] Ignoré: erreur fermeture contexte (%s)", self.enseigne, e)
