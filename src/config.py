"""Configuration centrale de TCG-STOCK-BOT."""
import os
import sys
import json
import logging
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration en couches (pour l'appli packagée + l'assistant de 1ère config)
# Priorité (la dernière l'emporte) :
#   1. .env (développement)
#   2. réglages pré-remplis embarqués (bundled_settings.json, à côté du code/exe)
#   3. réglages utilisateur (%APPDATA%\TCGStockBot\settings.json)
# Chaque couche est un simple JSON {CLE: valeur}. Les valeurs alimentent os.environ
# puis sont lues normalement par os.getenv ci-dessous — aucun autre code à changer.
# ---------------------------------------------------------------------------
def dossier_donnees() -> str:
    """Dossier de données de l'appli (créable). Surchargable via TCG_DATA_DIR."""
    forced = os.getenv("TCG_DATA_DIR")
    if forced:
        return forced
    if os.name == "nt" and os.getenv("APPDATA"):
        return os.path.join(os.getenv("APPDATA"), "TCGStockBot")
    return os.path.join(os.path.expanduser("~"), ".tcgstockbot")


CHEMIN_CONFIG_UTILISATEUR = os.path.join(dossier_donnees(), "settings.json")
CHEMIN_CONFIG_EMBARQUEE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "bundled_settings.json")


def _appliquer_couche(chemin: str) -> None:
    try:
        with open(chemin, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:  # JSON invalide : on ignore sans planter le bot
        logging.warning("Réglages illisibles (%s) : %s", chemin, e)
        return
    if isinstance(data, dict):
        for cle, valeur in data.items():
            if valeur is not None:
                os.environ[str(cle)] = str(valeur)


_appliquer_couche(CHEMIN_CONFIG_EMBARQUEE)
_appliquer_couche(CHEMIN_CONFIG_UTILISATEUR)


def sauver_reglages_utilisateur(reglages: dict) -> str:
    """Écrit/fusionne les réglages utilisateur (utilisé par l'assistant de l'appli).

    Retourne le chemin du fichier. Fusionne avec l'existant (ne perd rien).
    """
    os.makedirs(dossier_donnees(), exist_ok=True)
    chemin = os.path.join(dossier_donnees(), "settings.json")
    actuel = {}
    try:
        with open(chemin, encoding="utf-8") as f:
            actuel = json.load(f)
    except Exception:
        actuel = {}
    actuel.update({k: v for k, v in reglages.items() if v is not None})
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(actuel, f, ensure_ascii=False, indent=2)
    # Applique immédiatement à l'environnement courant.
    for k, v in actuel.items():
        if v is not None:
            os.environ[str(k)] = str(v)
    return chemin

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Mode "bot" (optionnel) : débloque les boutons (Acheter / recherche) et prépare
# l'autobuy. Si les deux sont renseignés, l'envoi passe par le bot ; sinon on
# garde le webhook classique. Voir discord_webhook.py.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# Rôle à mentionner sur une alerte stock (notification instantanée). Optionnel :
# si vide, pas de ping. Mettre l'identifiant du rôle Discord (Mode développeur).
DISCORD_ALERT_ROLE_ID = os.getenv("DISCORD_ALERT_ROLE_ID", "")

# Propriétaire autorisé à utiliser les commandes qui MODIFIENT l'état du bot
# (/add, /pause, /resume). Optionnel : si vide, on retombe sur "permission
# administrateur du serveur". Mettre l'identifiant utilisateur Discord (Mode dev).
DISCORD_OWNER_ID = os.getenv("DISCORD_OWNER_ID", "")

if not DISCORD_WEBHOOK_URL and not (DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID):
    logging.warning("⚠️ Aucun canal Discord configuré (ni webhook, ni bot).")

# Emplacement de la base : variable d'env > dossier de données (app empaquetée)
# > fichier local (développement). Pour l'app installée, on écrit dans un dossier
# inscriptible (%APPDATA%) plutôt qu'à côté de l'exe.
_db_env = os.getenv("DB_PATH")
if _db_env:
    DB_PATH = _db_env
elif getattr(sys, "frozen", False):
    os.makedirs(dossier_donnees(), exist_ok=True)
    DB_PATH = os.path.join(dossier_donnees(), "tcg_stocks.db")
else:
    DB_PATH = "tcg_stocks.db"
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
# [Obsolete depuis Chantier 3] Ancien anti-spam global. Conserve pour compat .env.
# La surveillance par difference d'etat n'alerte deja que sur transition, donc un
# long cooldown ne sert plus qu'a etouffer de vrais restocks. Voir ALERT_DEDUP_WINDOW.
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "21600"))

# Fenetre anti-doublon (secondes) : delai minimum entre deux alertes pour un meme
# produit. Court par defaut (10 min) : absorbe un eventuel clignotement sans rater
# un vrai restock qui reviendrait plus tard dans la journee.
ALERT_DEDUP_WINDOW = int(os.getenv("ALERT_DEDUP_WINDOW", "600"))

# Resume "heartbeat" sur Discord (secondes). Le bot poste un bilan periodique
# (produits surveilles, alertes, etat des enseignes) pour prouver qu'il tourne.
# Defaut 24h. Mettre 0 pour desactiver.
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "86400"))

# Mise en veille auto des enseignes en echec (evite de gaspiller le navigateur).
# Apres STORE_PAUSE_THRESHOLD echecs consecutifs, l'enseigne est sautee pendant
# STORE_PAUSE_DURATION secondes, puis retentee.
STORE_PAUSE_THRESHOLD = int(os.getenv("STORE_PAUSE_THRESHOLD", "3"))
STORE_PAUSE_DURATION = int(os.getenv("STORE_PAUSE_DURATION", "3600"))

# Alerte "baisse de prix" (deal) : seuil de baisse en % d'un cycle a l'autre, sur
# un produit deja en stock. Defaut 15%. Mettre 0 pour desactiver les alertes deal.
DEAL_DROP_PERCENT = int(os.getenv("DEAL_DROP_PERCENT", "15"))

# Masquer les revendeurs tiers (marketplace) sur les grandes enseignes (Leclerc,
# Auchan) : si True, seuls les produits vendus par l'enseigne elle-même ou par les
# boutiques spécialisées génèrent une alerte. False = on alerte sur tout, mais une
# pastille ✅/🔁 indique le type de vendeur dans l'alerte.
MASQUER_REVENDEURS = os.getenv("MASQUER_REVENDEURS", "false").lower() in {"1", "true", "yes", "on"}

# Retention de l'historique de prix (jours). Au-dela, les points sont purges au
# demarrage pour garder la base legere.
HISTORY_RETENTION_DAYS = int(os.getenv("HISTORY_RETENTION_DAYS", "90"))

# -----------------------------------------------------------
# Anti-bot bypass configuration
# -----------------------------------------------------------
# Nombre maximum de tentatives par requete (avec escalation du fingerprint).
# 2 par defaut : inutile d'insister 5x contre un anti-bot qui ne cedera pas, ca
# ne fait que perdre du temps. (Sert seulement aux sites en mode navigateur.)
ANTIBOT_MAX_RETRIES = int(os.getenv("ANTIBOT_MAX_RETRIES", "2"))
# Activer le warmup navigateur (emule un utilisateur sur about:blank)
ANTIBOT_WARMUP = os.getenv("ANTIBOT_WARMUP", "true").lower() in {"1", "true", "yes", "on"}
# Pool de proxies (format JSON array: '["http://user:pass@host:port", ...]')
PROXY_LIST = os.getenv("PROXY_LIST", "")

# -----------------------------------------------------------
# Filet de secours "scraping API" (ScrapingBee / ZenRows / Crawlbase)
# -----------------------------------------------------------
# Utilisé UNIQUEMENT en dernier recours, quand une requête HTTP directe est
# bloquée (ex. DataDome sur Leclerc). On essaie les fournisseurs configurés EN
# CASCADE (le 1er qui répond gagne) → on cumule les quotas gratuits et on bascule
# automatiquement si l'un échoue. Vide = désactivé (comportement 100% gratuit).
SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_KEY", "")
ZENROWS_KEY = os.getenv("ZENROWS_KEY", "")
CRAWLBASE_TOKEN = os.getenv("CRAWLBASE_TOKEN", "")
# Activer le secours par proxy payant (par défaut: actif si au moins une clé existe).
PROXY_FALLBACK = os.getenv(
    "PROXY_FALLBACK",
    "true" if (SCRAPINGBEE_KEY or ZENROWS_KEY or CRAWLBASE_TOKEN) else "false"
).lower() in {"1", "true", "yes", "on"}

# Mots-clés recherchés sur CHAQUE enseigne (découverte de produits variés).
# Surchargeable via .env : SEARCH_KEYWORDS="cartes pokemon,coffret pokemon,..."
# Ajoute ici les noms de sets récents pour suivre les dernières sorties
# (ex: "pokemon evolutions prismatiques", "pokemon flammes blanches").
_DEFAULT_KEYWORDS = [
    # Requêtes larges (fort rendement, couvrent la majorité des produits)
    "cartes pokemon",
    "pokemon booster",
    "pokemon display",
    "pokemon coffret",
    "pokemon etb",
    "coffret dresseur elite pokemon",
    "pokemon bundle",
    "pokemon tin",
    "coffret ultra premium pokemon",
    # Sets récents 2025-2026 (les plus chassés)
    "pokemon mega evolution",
    "pokemon flammes fantasmagoriques",
    "pokemon heros transcendants",
    "pokemon evolutions prismatiques",
    "pokemon foudre noire",
    "pokemon flamme blanche",
    "pokemon aventures ensemble",
    "pokemon rivalites destinees",
    "pokemon 151",
    # --- ONE PIECE Card Game (édition française) ---
    "one piece carte",
    "one piece display",
    "one piece booster",
    "one piece coffret",
    "one piece starter deck",
    "one piece premium booster",
]
_env_keywords = [k.strip() for k in os.getenv("SEARCH_KEYWORDS", "").split(",") if k.strip()]
SEARCH_KEYWORDS = _env_keywords or _DEFAULT_KEYWORDS

# Nombre de mots-cles recherches en parallele par enseigne.
SEARCH_CONCURRENCY = int(os.getenv("SEARCH_CONCURRENCY", "3"))

# Enseignes ACTIVES (les seules surveillees). Par defaut on ne garde que celles
# qui repondent vraiment (Auchan, Leclerc) : rapide et fiable. Les sites blindes
# (Cultura, KingJouet, Smyths, GrandeRecre) sont desactives car ils consomment des
# minutes pour zero resultat. Pour en reactiver un, ajoute son nom ici via .env :
#   ENABLED_STORES=Auchan,Leclerc,Cultura
ENABLED_STORES = [s.strip() for s in os.getenv(
    "ENABLED_STORES", "Auchan,Leclerc,LudiJeux,RelicTCG,CoinBarons").split(",") if s.strip()]

# Boutiques Shopify (API JSON publique, pas d'anti-bot) : {nom: domaine}. Un seul
# scraper générique les gère toutes (cf. scrapers/shopify.py). Pour en ajouter une,
# vérifie d'abord qu'elle répond sur https://www.<domaine>/products.json puis ajoute
# une ligne ici (et son nom dans ENABLED_STORES). Surchargeable via .env :
#   SHOPIFY_SHOPS="LudiJeux=ludijeux.fr,RelicTCG=relictcg.com"
_DEFAULT_SHOPIFY = {
    "LudiJeux": "ludijeux.fr",
    "RelicTCG": "relictcg.com",
}
def _parse_shops(env_val: str, defaut: dict) -> dict:
    """Parse "Nom=domaine,Nom2=domaine2" depuis .env, sinon renvoie le défaut."""
    if not env_val:
        return defaut
    shops = {}
    for paire in env_val.split(","):
        if "=" in paire:
            nom, dom = paire.split("=", 1)
            shops[nom.strip()] = dom.strip()
    return shops


SHOPIFY_SHOPS = _parse_shops(os.getenv("SHOPIFY_SHOPS", ""), _DEFAULT_SHOPIFY)

# Boutiques WooCommerce (Store API publique /wp-json/wc/store/v1). Même principe
# qu'au-dessus : un seul scraper générique (cf. scrapers/woocommerce.py). Vérifie
# qu'une boutique répond sur /wp-json/wc/store/v1/products?search=pokemon avant de
# l'ajouter ici (+ son nom dans ENABLED_STORES). Surchargeable via WOO_SHOPS.
_DEFAULT_WOO = {
    "CoinBarons": "lecoindesbarons.com",
}
WOO_SHOPS = _parse_shops(os.getenv("WOO_SHOPS", ""), _DEFAULT_WOO)

# Gabarit d'URL de recherche par enseigne. {q} est remplacé par le mot-clé encodé.
SEARCH_URL_TEMPLATES = {
    "Cultura": "https://www.cultura.com/recherche.html?q={q}",
    "Leclerc": "https://www.e.leclerc/recherche?q={q}",
    "KingJouet": "https://www.king-jouet.com/recherche.htm?mot={q}",
    "Smyths": "https://www.smythstoys.com/fr/fr-fr/recherche/?text={q}",
    "GrandeRecre": "https://www.lagranderecre.fr/catalogsearch/result/?q={q}",
    "Auchan": "https://www.auchan.fr/recherche?text={q}",
}

# Conservé pour compatibilité : URL de recherche par défaut (1 mot-clé) par enseigne.
SEARCH_QUERIES = {
    enseigne: tmpl.format(q="cartes+pokemon")
    for enseigne, tmpl in SEARCH_URL_TEMPLATES.items()
}
