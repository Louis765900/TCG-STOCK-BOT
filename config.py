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
# Nombre de fiches produit vérifiées en parallèle pendant un cycle watchlist.
WATCHLIST_CONCURRENCY = int(os.getenv("WATCHLIST_CONCURRENCY", "5"))
# Blocages consécutifs sur une enseigne avant d'abandonner le reste du cycle.
MAX_BLOCKS_BEFORE_SKIP = int(os.getenv("MAX_BLOCKS_BEFORE_SKIP", "3"))
# Activer le graphique d'historique des prix dans les alertes Discord.
ENABLE_PRICE_CHART = os.getenv("ENABLE_PRICE_CHART", "true").lower() in {"1", "true", "yes", "on"}
# Délai minimum (secondes) entre deux alertes pour un même produit. Anti-spam.
# Défaut 6h: empêche un produit qui "clignote" de flooder le salon Discord.
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "21600"))

# Mots-clés recherchés sur CHAQUE enseigne (découverte de produits variés).
# Surchargeable via .env : SEARCH_KEYWORDS="cartes pokemon,coffret pokemon,..."
# Ajoute ici les noms de sets récents pour suivre les dernières sorties
# (ex: "pokemon evolutions prismatiques", "pokemon flammes blanches").
_DEFAULT_KEYWORDS = [
    "cartes pokemon",
    "coffret pokemon",
    "elite trainer box pokemon",
    "booster pokemon",
    "display pokemon",
    "bundle pokemon",
    "tin pokemon",
]
_env_keywords = [k.strip() for k in os.getenv("SEARCH_KEYWORDS", "").split(",") if k.strip()]
SEARCH_KEYWORDS = _env_keywords or _DEFAULT_KEYWORDS

# Nombre de mots-clés recherchés en parallèle par enseigne.
SEARCH_CONCURRENCY = int(os.getenv("SEARCH_CONCURRENCY", "3"))

# Gabarit d'URL de recherche par enseigne. {q} est remplacé par le mot-clé encodé.
SEARCH_URL_TEMPLATES = {
    "Cultura": "https://www.cultura.com/recherche.html?q={q}",
    "Leclerc": "https://www.e.leclerc/recherche?q={q}",
    "KingJouet": "https://www.king-jouet.com/recherche.htm?mot={q}",
    "Smyths": "https://www.smythstoys.com/fr/fr-fr/recherche/?text={q}",
    "GrandeRecre": "https://www.lagranderecre.fr/recherche?q={q}",
    "Auchan": "https://www.auchan.fr/recherche?text={q}",
}

# Conservé pour compatibilité : URL de recherche par défaut (1 mot-clé) par enseigne.
SEARCH_QUERIES = {
    enseigne: tmpl.format(q="cartes+pokemon")
    for enseigne, tmpl in SEARCH_URL_TEMPLATES.items()
}
