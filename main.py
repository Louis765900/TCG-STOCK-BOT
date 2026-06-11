"""Boucle principale de TCG-STOCK-BOT."""
import asyncio
import logging
import random
from playwright.async_api import async_playwright

import config
import database
from filter_utils import est_tcg_valide
from discord_webhook import envoyer_alerte

# Importation de tous les scrapers
from scrapers.cultura import CulturaScraper
from scrapers.leclerc import LeclercScraper
from scrapers.kingjouet import KingJouetScraper
from scrapers.smyths import SmythsScraper
from scrapers.granderecre import GrandeRecreScraper
from scrapers.auchan import AuchanScraper

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

async def main_loop():
    filtre = "Gemini + local" if config.USE_GEMINI_FILTER else "local"
    logger.info(f"Démarrage de TCG-STOCK-BOT (multi-enseignes, filtre {filtre})...")
    await database.initialiser_db()

    async with async_playwright() as p:
        # Lancement du navigateur
        browser = await p.chromium.launch(headless=True)
        
        # Initialisation de la liste des scrapers
        scrapers = [
            CulturaScraper(browser),
            LeclercScraper(browser),
            KingJouetScraper(browser),
            SmythsScraper(browser),
            GrandeRecreScraper(browser),
            AuchanScraper(browser)
        ]

        while True:
            logger.info("=== Nouveau cycle de vérification globale ===")
            
            for scraper in scrapers:
                try:
                    produits = await scraper.scraper_recherche()
                    
                    if not produits:
                        logger.warning(f"[{scraper.enseigne}] Aucun produit trouvé. Le site a peut-être changé ou bloqué la requête.")
                        continue
                        
                    for prod in produits:
                        try:
                            titre = prod["titre"]
                            url = prod["url"]
                            en_stock = prod["en_stock"]
                            
                            # Filtre TCG local, avec validation Gemini optionnelle.
                            if not await est_tcg_valide(titre):
                                continue
                                
                            # Vérifier l'état en BDD
                            etat_db = await database.recuperer_produit(url)
                            
                            if not etat_db:
                                # NOUVEAUTÉ
                                logger.info(f"🚨 NOUVEAUTÉ DÉTECTÉE [{scraper.enseigne}]: {titre} - En stock: {en_stock}")
                                await database.ajouter_produit(url, titre, scraper.enseigne, en_stock)
                                
                                # On alerte les nouveautés uniquement si elles sont en stock (ou selon la logique métier)
                                if en_stock:
                                    await envoyer_alerte(prod, scraper.enseigne, "NOUVEAUTE")
                            else:
                                # PRODUIT CONNU
                                ancien_stock = bool(etat_db["en_stock"])
                                
                                if en_stock and not ancien_stock:
                                    # RESTOCK
                                    logger.info(f"🔥 RESTOCK DÉTECTÉ [{scraper.enseigne}]: {titre}")
                                    await envoyer_alerte(prod, scraper.enseigne, "RESTOCK")
                                    await database.mettre_a_jour_stock(url, True)
                                    
                                elif not en_stock and ancien_stock:
                                    # RUPTURE
                                    logger.info(f"📉 Rupture de stock [{scraper.enseigne}]: {titre}")
                                    await database.mettre_a_jour_stock(url, False)
                                    
                                else:
                                    # Pas de changement, on met juste à jour le timestamp
                                    await database.marquer_vu(url)
                                    
                        except Exception as inner_e:
                            logger.error(f"Erreur lors du traitement d'un produit chez {scraper.enseigne}: {inner_e}")
                            
                except Exception as e:
                    # Résilience : si un scraper échoue (ex: Timeout), on passe au suivant sans planter le bot
                    logger.error(f"Échec critique du scraper {scraper.enseigne} : {e}", exc_info=True)

            # Pause aléatoire entre deux cycles complets
            if config.RUN_ONCE:
                logger.info("RUN_ONCE actif. Arrêt après un cycle.")
                break

            duree_sommeil = random.randint(config.MIN_SLEEP, config.MAX_SLEEP)
            logger.info(f"Cycle terminé. Attente de {duree_sommeil} secondes avant le prochain cycle...")
            await asyncio.sleep(duree_sommeil)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel du bot.")
    except Exception as e:
        logger.critical(f"Erreur fatale de la boucle principale : {e}", exc_info=True)
