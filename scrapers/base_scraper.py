"""Classe de base abstraite pour les scrapers."""
from playwright.async_api import Browser, Page
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
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

    def __init__(self, enseigne: str, browser: Browser):
        self.enseigne = enseigne
        self.browser = browser

    @abstractmethod
    async def scraper_recherche(self) -> list[dict]:
        pass

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

            yield page, BeautifulSoup(html, "html.parser")

        except ScraperBlockedError:
            logger.warning(
                "[%s] Site bloqué (anti-bot). Stealth actif: %s",
                self.enseigne, _STEALTH is not None,
            )
            yield page, None

        except Exception as e:
            logger.warning("[%s] Erreur chargement %s: %s", self.enseigne, url, e)
            yield page, None

        finally:
            try:
                await context.close()
            except Exception as e:
                logger.debug("[%s] Ignoré: erreur fermeture contexte (%s)", self.enseigne, e)
