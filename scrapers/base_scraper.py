"""Classe de base abstraite pour les scrapers."""
from playwright.async_api import Browser, Page
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
import logging
import config

logger = logging.getLogger(__name__)


class ScraperBlockedError(RuntimeError):
    """Le site a retourne une page de protection au lieu du contenu attendu."""

class BaseScraper(ABC):
    def __init__(self, enseigne: str, browser: Browser):
        self.enseigne = enseigne
        self.browser = browser

    @abstractmethod
    async def scraper_recherche(self) -> list[dict]:
        """
        Doit retourner une liste de dictionnaires.
        """
        pass

    @asynccontextmanager
    async def get_page_soup(self, url: str):
        """Helper pour charger une page et parser le HTML. Retourne (page, soup)."""
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=config.REQUEST_TIMEOUT_MS)
            html = await page.content()
            html_lower = html.lower()
            blocages = ("datadome", "captcha-delivery", "incapsula", "verify you are human", "access denied")
            if any(mot in html_lower for mot in blocages):
                raise ScraperBlockedError(f"[{self.enseigne}] Acces bloque par protection anti-bot")
            yield page, BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning(f"[{self.enseigne}] Erreur chargement {url}: {e}")
            yield page, None
        finally:
            try:
                await context.close()
            except Exception as e:
                logger.debug(f"[{self.enseigne}] Ignoré: erreur à la fermeture du contexte ({e})")
