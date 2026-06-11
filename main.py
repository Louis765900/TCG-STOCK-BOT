"""Boucle principale de TCG-STOCK-BOT."""
import asyncio
import logging
import random
from playwright.async_api import async_playwright

import config
import database
from filter_utils import est_tcg_valide
from discord_webhook import envoyer_alerte
from cycle_report import CycleReport, StoreReport

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


async def cycle_recherche(scrapers_map: dict, cycle_num: int) -> CycleReport:
    """Scrape les pages de recherche de chaque enseigne pour découvrir de nouveaux produits."""
    rapport = CycleReport(cycle_num=cycle_num, mode="recherche")

    for enseigne, scraper in scrapers_map.items():
        store = StoreReport(enseigne=enseigne)
        try:
            produits = await scraper.scraper_recherche()

            if not produits:
                statut = scraper._last_status if scraper._last_status != "ok" else "empty"
                store.terminer(statut)
                logger.warning("[%s] Aucun produit (statut: %s).", enseigne, statut)
            else:
                store.produits_trouves = len(produits)

                for prod in produits:
                    try:
                        titre = prod["titre"]
                        url = prod["url"]
                        en_stock = prod["en_stock"]

                        if not await est_tcg_valide(titre):
                            continue

                        etat_db = await database.recuperer_produit(url)

                        if not etat_db:
                            logger.info("NOUVEAUTE [%s]: %s", enseigne, titre)
                            await database.ajouter_produit(
                                url, titre, enseigne, en_stock,
                                prix=prod.get("prix", "N/A"),
                                image_url=prod.get("image_url", ""),
                            )
                            store.nouveautes += 1
                            if en_stock:
                                await envoyer_alerte(prod, enseigne, "NOUVEAUTE")
                        else:
                            ancien_stock = bool(etat_db["en_stock"])
                            if en_stock and not ancien_stock:
                                logger.info("RESTOCK [%s]: %s", enseigne, titre)
                                await envoyer_alerte(prod, enseigne, "RESTOCK")
                                await database.mettre_a_jour_stock(url, True, prod.get("prix"))
                                store.restocks += 1
                            elif not en_stock and ancien_stock:
                                logger.info("RUPTURE [%s]: %s", enseigne, titre)
                                await database.mettre_a_jour_stock(url, False, prod.get("prix"))
                                store.ruptures += 1
                            else:
                                await database.marquer_vu(url)

                    except Exception as inner_e:
                        logger.error("[%s] Erreur produit: %s", enseigne, inner_e)

                store.terminer("healthy")

        except Exception as e:
            store.terminer("timeout")
            logger.error("[%s] Echec scraper: %s", enseigne, e)

        rapport.ajouter_store(store)
        await database.enregistrer_cycle(
            timestamp=rapport.timestamp,
            cycle_num=cycle_num,
            enseigne=enseigne,
            statut=store.statut,
            produits_trouves=store.produits_trouves,
            nouveautes=store.nouveautes,
            restocks=store.restocks,
            ruptures=store.ruptures,
            duree_s=store.duree_s,
        )

    return rapport


async def cycle_watchlist(scrapers_map: dict, cycle_num: int) -> CycleReport:
    """Vérifie le stock des URLs produit déjà connues (watchlist = table produits)."""
    rapport = CycleReport(cycle_num=cycle_num, mode="watchlist")

    tous_produits = await database.recuperer_tous_produits()
    if not tous_produits:
        logger.info("Watchlist vide — premier cycle doit être une recherche.")
        return rapport

    logger.info("Vérification watchlist: %d produits connus.", len(tous_produits))

    par_enseigne: dict[str, list] = {}
    for p in tous_produits:
        par_enseigne.setdefault(p["enseigne"], []).append(p)

    for enseigne, items in par_enseigne.items():
        scraper = scrapers_map.get(enseigne)
        if not scraper:
            logger.warning("Pas de scraper pour '%s', ignoré.", enseigne)
            continue

        store = StoreReport(enseigne=enseigne)
        store.produits_trouves = len(items)
        erreurs = 0

        for item in items:
            try:
                resultat = await scraper.scraper_produit(item["url"])
                if resultat is None:
                    erreurs += 1
                    continue

                en_stock_actuel = resultat["en_stock"]
                prix_actuel = resultat.get("prix", "N/A")
                ancien_stock = bool(item["en_stock"])

                if en_stock_actuel and not ancien_stock:
                    logger.info("RESTOCK WATCHLIST [%s]: %s", enseigne, item["titre"])
                    prod_alerte = {
                        "url": item["url"],
                        "titre": item["titre"],
                        "prix": prix_actuel,
                        "image_url": item.get("image_url", ""),
                        "en_stock": True,
                        "country": "FR",
                        "direct_links": {enseigne: item["url"]},
                    }
                    await envoyer_alerte(prod_alerte, enseigne, "RESTOCK")
                    await database.mettre_a_jour_stock(item["url"], True, prix_actuel)
                    store.restocks += 1
                elif not en_stock_actuel and ancien_stock:
                    logger.info("RUPTURE WATCHLIST [%s]: %s", enseigne, item["titre"])
                    await database.mettre_a_jour_stock(item["url"], False, prix_actuel)
                    store.ruptures += 1
                else:
                    await database.marquer_vu(item["url"])

            except Exception as e:
                logger.error("[%s] Erreur watchlist %s: %s", enseigne, item["url"], e)
                erreurs += 1

        statut = "parser_error" if erreurs > len(items) // 2 else "healthy"
        store.terminer(statut)
        rapport.ajouter_store(store)

        await database.enregistrer_cycle(
            timestamp=rapport.timestamp,
            cycle_num=cycle_num,
            enseigne=enseigne,
            statut=store.statut,
            produits_trouves=store.produits_trouves,
            nouveautes=0,
            restocks=store.restocks,
            ruptures=store.ruptures,
            duree_s=store.duree_s,
        )

    return rapport


async def main_loop():
    filtre = "Gemini + local" if config.USE_GEMINI_FILTER else "local"
    logger.info(
        "Démarrage TCG-STOCK-BOT (filtre: %s, recherche toutes les %d cycles)...",
        filtre, config.SEARCH_INTERVAL,
    )
    await database.initialiser_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        scrapers_map = {
            "Cultura": CulturaScraper(browser),
            "Leclerc": LeclercScraper(browser),
            "KingJouet": KingJouetScraper(browser),
            "Smyths": SmythsScraper(browser),
            "GrandeRecre": GrandeRecreScraper(browser),
            "Auchan": AuchanScraper(browser),
        }

        cycle_num = 0

        while True:
            cycle_num += 1
            logger.info("=== CYCLE %d ===", cycle_num)

            # Cycle 1 = toujours recherche. Ensuite watchlist sauf tous les SEARCH_INTERVAL.
            if cycle_num == 1 or cycle_num % config.SEARCH_INTERVAL == 0:
                rapport = await cycle_recherche(scrapers_map, cycle_num)
            else:
                rapport = await cycle_watchlist(scrapers_map, cycle_num)

            logger.info(rapport.resume())

            if config.RUN_ONCE:
                logger.info("RUN_ONCE actif. Arrêt.")
                break

            duree = random.randint(config.MIN_SLEEP, config.MAX_SLEEP)
            logger.info("Prochain cycle dans %ds.", duree)
            await asyncio.sleep(duree)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel.")
    except Exception as e:
        logger.critical("Erreur fatale: %s", e, exc_info=True)
