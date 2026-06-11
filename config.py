"""Configuration centrale de TCG-STOCK-BOT."""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
if not DISCORD_WEBHOOK_URL:
    logging.warning("⚠️ DISCORD_WEBHOOK_URL non configurée.")

DB_PATH = os.getenv("DB_PATH", "tcg_stocks.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MIN_SLEEP = int(os.getenv("MIN_SLEEP", "60"))
MAX_SLEEP = int(os.getenv("MAX_SLEEP", "180"))
USE_GEMINI_FILTER = os.getenv("USE_GEMINI_FILTER", "false").lower() in {"1", "true", "yes", "on"}
REQUEST_TIMEOUT_MS = int(os.getenv("REQUEST_TIMEOUT_MS", "30000"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in {"1", "true", "yes", "on"}
# Fréquence des cycles de recherche (discovery). Ex: 3 = 1 recherche pour 2 watchlist.
SEARCH_INTERVAL = int(os.getenv("SEARCH_INTERVAL", "3"))

# Mots-clés de recherche globaux par enseigne (Option A validée)
SEARCH_QUERIES = {
    "Cultura": "https://www.cultura.com/recherche.html?q=cartes+pokemon",
    "Leclerc": "https://www.e.leclerc/recherche?q=cartes+pokemon",
    "KingJouet": "https://www.king-jouet.com/recherche.htm?mot=cartes+pokemon",
    "Smyths": "https://www.smythstoys.com/fr/fr-fr/recherche/?text=cartes+pokemon",
    "GrandeRecre": "https://www.lagranderecre.fr/recherche?q=cartes+pokemon",
    "Auchan": "https://www.auchan.fr/recherche?text=cartes+pokemon"
}
