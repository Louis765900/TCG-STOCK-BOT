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
from product_format import STORE_COLORS, parse_price
from price_chart import generer_graphique_prix

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


# ----------------------------------------------------------------------------
# Helpers prix + graphique + alerte
# ----------------------------------------------------------------------------
async def _enregistrer_prix(url: str, prix_str: str, en_stock: bool):
    """Ajoute un point d'historique si le prix est numérique."""
    valeur = parse_price(prix_str)
    if valeur is not None:
        await database.enregistrer_prix(url, float(valeur), en_stock)


async def _alerter(prod: dict, enseigne: str, type_alerte: str):
    """Envoie une alerte Discord avec le graphique d'historique si disponible."""
    chart = None
    if config.ENABLE_PRICE_CHART:
        historique = await database.recuperer_historique_prix(prod.get("url", ""))
        chart = generer_graphique_prix(
            historique, prod.get("titre", ""), STORE_COLORS.get(enseigne, 0xE30613)
        )
    await envoyer_alerte(prod, enseigne, type_alerte, chart_png=chart)


# ----------------------------------------------------------------------------
# Cycle de découverte (pages recherche)
# ----------------------------------------------------------------------------
async def cycle_recherche(scrapers_map: dict, cycle_num: int) -> CycleReport:
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

                        # Historique de prix seedé dès la découverte.
                        await _enregistrer_prix(url, prod.get("prix", "N/A"), en_stock)

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
                                await _alerter(prod, enseigne, "NOUVEAUTE")
                        else:
                            ancien_stock = bool(etat_db["en_stock"])
                            if prod.get("image_url"):
                                await database.mettre_a_jour_image(url, prod["image_url"])

                            if en_stock and not ancien_stock:
                                logger.info("RESTOCK [%s]: %s", enseigne, titre)
                                await database.mettre_a_jour_stock(url, True, prod.get("prix"))
                                await _alerter(prod, enseigne, "RESTOCK")
                                store.restocks += 1
                            elif not en_stock and ancien_stock:
                                logger.info("RUPTURE [%s]: %s", enseigne, titre)
                                await database.mettre_a_jour_stock(url, False, prod.get("prix"))
                                store.ruptures += 1
                            else:
                                await database.mettre_a_jour_stock(url, en_stock, prod.get("prix"))

                    except Exception as inner_e:
                        logger.error("[%s] Erreur produit: %s", enseigne, inner_e)

                store.terminer("healthy")

        except Exception as e:
            store.terminer("timeout")
            logger.error("[%s] Echec scraper: %s", enseigne, e)

        rapport.ajouter_store(store)
        await _logger_store(cycle_num, rapport.timestamp, store)

    return rapport


# ----------------------------------------------------------------------------
# Cycle watchlist (vérification des URLs connues, en parallèle)
# ----------------------------------------------------------------------------
async def cycle_watchlist(scrapers_map: dict, cycle_num: int) -> CycleReport:
    rapport = CycleReport(cycle_num=cycle_num, mode="watchlist")

    tous_produits = await database.recuperer_tous_produits()
    if not tous_produits:
        logger.info("Watchlist vide — premier cycle doit être une recherche.")
        return rapport

    logger.info("Vérification watchlist: %d produits connus.", len(tous_produits))

    par_enseigne: dict[str, list] = {}
    for p in tous_produits:
        par_enseigne.setdefault(p["enseigne"], []).append(p)

    sem = asyncio.Semaphore(config.WATCHLIST_CONCURRENCY)

    for enseigne, items in par_enseigne.items():
        scraper = scrapers_map.get(enseigne)
        if not scraper:
            logger.warning("Pas de scraper pour '%s', ignoré.", enseigne)
            continue

        store = StoreReport(enseigne=enseigne)
        store.produits_trouves = len(items)
        etat = {"blocages": 0, "stop": False}

        async def verifier(item):
            async with sem:
                if etat["stop"]:
                    return item, {"status": "skipped"}
                res = await scraper.scraper_produit(item["url"])
            if res["status"] in ("blocked", "timeout"):
                etat["blocages"] += 1
                if etat["blocages"] >= config.MAX_BLOCKS_BEFORE_SKIP:
                    if not etat["stop"]:
                        logger.warning(
                            "[%s] %d blocages — abandon du reste du cycle pour cette enseigne.",
                            enseigne, etat["blocages"],
                        )
                    etat["stop"] = True
            return item, res

        resultats = await asyncio.gather(*(verifier(i) for i in items))

        ok, erreurs = 0, 0
        for item, res in resultats:
            statut = res.get("status")
            if statut != "ok":
                if statut in ("blocked", "timeout"):
                    erreurs += 1
                continue
            ok += 1
            try:
                await _traiter_resultat_watchlist(enseigne, item, res, store)
            except Exception as e:
                logger.error("[%s] Erreur traitement %s: %s", enseigne, item["url"], e)

        if etat["stop"] or (erreurs and erreurs >= len(items) // 2 and ok == 0):
            store.terminer("blocked")
        elif erreurs > ok:
            store.terminer("parser_error")
        else:
            store.terminer("healthy")

        rapport.ajouter_store(store)
        await _logger_store(cycle_num, rapport.timestamp, store)

    return rapport


async def _traiter_resultat_watchlist(enseigne: str, item: dict, res: dict, store: StoreReport):
    """Applique la logique stock/prix/alerte pour un produit vérifié."""
    url = item["url"]
    en_stock_actuel = res["en_stock"]
    prix_actuel = res.get("prix", "N/A")
    ancien_stock = bool(item["en_stock"])

    await _enregistrer_prix(url, prix_actuel, en_stock_actuel)

    # Backfill image si elle manquait (corrige les vieilles entrées sans image).
    image_url = res.get("image_url") or item.get("image_url", "")
    if res.get("image_url"):
        await database.mettre_a_jour_image(url, res["image_url"])

    prod_alerte = {
        "url": url,
        "titre": item["titre"],
        "prix": prix_actuel,
        "image_url": image_url,
        "en_stock": en_stock_actuel,
        "country": "FR",
        "direct_links": {enseigne: url},
    }

    if en_stock_actuel and not ancien_stock:
        logger.info("RESTOCK WATCHLIST [%s]: %s", enseigne, item["titre"])
        await database.mettre_a_jour_stock(url, True, prix_actuel)
        await _alerter(prod_alerte, enseigne, "RESTOCK")
        store.restocks += 1
    elif not en_stock_actuel and ancien_stock:
        logger.info("RUPTURE WATCHLIST [%s]: %s", enseigne, item["titre"])
        await database.mettre_a_jour_stock(url, False, prix_actuel)
        store.ruptures += 1
    else:
        await database.mettre_a_jour_stock(url, en_stock_actuel, prix_actuel)


async def _logger_store(cycle_num: int, timestamp: float, store: StoreReport):
    await database.enregistrer_cycle(
        timestamp=timestamp,
        cycle_num=cycle_num,
        enseigne=store.enseigne,
        statut=store.statut,
        produits_trouves=store.produits_trouves,
        nouveautes=store.nouveautes,
        restocks=store.restocks,
        ruptures=store.ruptures,
        duree_s=store.duree_s,
    )


# ----------------------------------------------------------------------------
# Boucle principale
# ----------------------------------------------------------------------------
async def main_loop():
    filtre = "Gemini + local" if config.USE_GEMINI_FILTER else "local"
    logger.info(
        "Démarrage TCG-STOCK-BOT (filtre: %s, recherche toutes les %d cycles, "
        "concurrence watchlist: %d)...",
        filtre, config.SEARCH_INTERVAL, config.WATCHLIST_CONCURRENCY,
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
        try:
            while True:
                cycle_num += 1
                logger.info("=== CYCLE %d ===", cycle_num)

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
        finally:
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel.")
    except Exception as e:
        logger.critical("Erreur fatale: %s", e, exc_info=True)
