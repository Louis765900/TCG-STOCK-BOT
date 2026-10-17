"""Boucle principale de TCG-STOCK-BOT."""
import asyncio
import logging
import random
import time
import config
import database
import bot_state
from filter_utils import est_tcg_valide, est_tcg_valide_local
from discord_webhook import envoyer_alerte, envoyer_message
from stock_state import (evaluer_transition, RESTOCK, RUPTURE, ConfirmationRupture,
                         ConfirmationPrix, calculer_pause)
from store_health import StoreHealth
from cycle_report import CycleReport, StoreReport
from product_format import STORE_COLORS, parse_price, est_revendeur
from price_chart import generer_graphique_prix

from scrapers.registry import construire_tous

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

# Suivi de la santé des enseignes : met en veille celles qui échouent en boucle.
_sante = StoreHealth(seuil=config.STORE_PAUSE_THRESHOLD, pause_s=config.STORE_PAUSE_DURATION)

# Confirmation des ruptures (anti faux restock) : cf. stock_state.ConfirmationRupture.
_confirmation = ConfirmationRupture(config.RUPTURE_CONFIRMATIONS)

# Confirmation des baisses de prix (anti fausse "DEAL") : cf. stock_state.ConfirmationPrix.
_confirmation_prix = ConfirmationPrix(config.PRIX_CONFIRMATIONS)

# Compteur d'alertes RÉELLEMENT envoyées sur Discord (≠ nombre de produits
# découverts). Incrémenté seulement quand une alerte part vraiment.
_compteur_alertes = {"total": 0}


# ----------------------------------------------------------------------------
# Helpers prix + graphique + alerte
# ----------------------------------------------------------------------------
async def _enregistrer_prix(url: str, prix_str: str, en_stock: bool):
    """Ajoute un point d'historique si le prix est numérique."""
    valeur = parse_price(prix_str)
    if valeur is not None:
        await database.enregistrer_prix(url, float(valeur), en_stock)


async def _alerter(prod: dict, enseigne: str, type_alerte: str):
    """
    Envoie une alerte Discord (avec graphique si dispo).

    La surveillance par différence d'état (cf. stock_state.py) garantit déjà qu'on
    n'alerte que sur une transition. Ici on ajoute seulement une courte fenêtre
    anti-doublon (ALERT_DEDUP_WINDOW) pour absorber un éventuel clignotement, sans
    étouffer un vrai restock qui reviendrait plus tard.
    """
    if bot_state.alertes_en_pause():
        logger.info("Alertes en pause (/pause) — '%s' ignoré.", prod.get("titre", ""))
        return

    # Masquage optionnel des revendeurs tiers (marketplace) si activé dans .env.
    if config.MASQUER_REVENDEURS and est_revendeur(enseigne, prod.get("seller", "")):
        logger.info("Revendeur masqué [%s]: %s (vendeur: %s)",
                    enseigne, prod.get("titre", ""), prod.get("seller", "?"))
        return

    url = prod.get("url", "")
    now = time.time()

    # Reservation ATOMIQUE du droit d'alerter (un seul UPDATE conditionnel) : deux
    # detections simultanees du meme produit ne peuvent plus produire deux alertes.
    ancienne = await database.reserver_alerte(url, now, config.ALERT_DEDUP_WINDOW)
    if ancienne is None:
        logger.info("Alerte ignorée (doublon, fenêtre %dmin) [%s]: %s",
                    config.ALERT_DEDUP_WINDOW // 60, enseigne, prod.get("titre", ""))
        return

    chart = None
    if config.ENABLE_PRICE_CHART:
        historique = await database.recuperer_historique_prix(url)
        chart = generer_graphique_prix(
            historique, prod.get("titre", ""), STORE_COLORS.get(enseigne, 0xE30613)
        )
    livree = await envoyer_alerte(prod, enseigne, type_alerte, chart_png=chart)
    if livree is False:
        # Envoi echoue : on rend la reservation, la prochaine detection pourra
        # re-alerter au lieu d'etre etouffee par un faux "doublon".
        await database.enregistrer_alerte(url, ancienne)
        logger.error("Alerte NON livrée, réservation restituée [%s]: %s",
                     enseigne, prod.get("titre", ""))
        return
    _compteur_alertes["total"] += 1


# ----------------------------------------------------------------------------
# Cycle de découverte (pages recherche)
# ----------------------------------------------------------------------------
async def cycle_recherche(scrapers_map: dict, cycle_num: int,
                          amorcage: bool = False) -> CycleReport:
    """
    amorcage=True (1er démarrage, base vide) : on enregistre les produits SANS
    alerter, pour éviter d'inonder Discord de dizaines d'alertes au lancement.
    """
    rapport = CycleReport(cycle_num=cycle_num, mode="recherche")

    # Amorcage PAR ENSEIGNE : une enseigne qui n'a encore aucun produit en base (nouvelle
    # enseigne ajoutee a une installation existante) est decouverte en silence, comme au
    # tout premier lancement. Sinon, activer une enseigne inonderait Discord de "nouveautes"
    # qui ne sont que du catalogue deja en rayon.
    deja_connues = {p["enseigne"] for p in await database.recuperer_tous_produits()}
    modes_connus = {e: await database.lire_meta(f"decouverte:{e}") for e in scrapers_map}

    async def une_enseigne(enseigne, scraper):
        if _sante.en_veille(enseigne):
            logger.info("[%s] En veille (~%dmin restantes), cycle sauté.",
                        enseigne, _sante.minutes_restantes(enseigne))
            return

        store = StoreReport(enseigne=enseigne)
        silencieux = amorcage or enseigne not in deja_connues
        if silencieux and not amorcage:
            logger.info("[%s] Première découverte de cette enseigne : amorçage silencieux.",
                        enseigne)
        try:
            produits = await scraper.scraper_recherche()

            # Changement de mode de decouverte vers un mode PLUS COMPLET (ex. recherche
            # predictive -> collections) : le catalogue decouvert est largement un stock deja
            # en rayon, pas des nouveautes. Cycle d'adoption silencieux (une seule fois). Le
            # repli inverse (collections -> recherche) ne change rien : ce que la recherche
            # voit est un sous-ensemble de ce qui est deja connu.
            mode = getattr(scraper, "mode_decouverte", None)
            if (produits and mode == "collections" and modes_connus.get(enseigne) != "collections"
                    and not silencieux):
                silencieux = True
                logger.warning("[%s] Passage à la découverte par collections : cycle d'adoption "
                               "silencieux (%d produits, aucune alerte « nouveauté »).",
                               enseigne, len(produits))

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

                        if not await est_tcg_valide(titre, prod.get("brand", "")):
                            continue

                        # Historique de prix seedé dès la découverte.
                        await _enregistrer_prix(url, prod.get("prix", "N/A"), en_stock)

                        etat_db = await database.recuperer_produit(url)

                        if not etat_db:
                            # Découverte d'un nouveau produit.
                            logger.info("NOUVEAUTE [%s]: %s", enseigne, titre)
                            await database.ajouter_produit(
                                url, titre, enseigne, en_stock,
                                prix=prod.get("prix", "N/A"),
                                image_url=prod.get("image_url", ""),
                            )
                            store.nouveautes += 1
                            if en_stock and not silencieux:
                                await _alerter(prod, enseigne, "NOUVEAUTE")
                        else:
                            # Produit déjà connu : la recherche ne fait QUE rafraîchir
                            # prix/image. Le stock (restock/rupture) est géré par la
                            # watchlist qui lit la fiche produit, source fiable. Évite
                            # le clignotement dû aux tuiles de recherche imprécises.
                            if prod.get("image_url"):
                                await database.mettre_a_jour_image(url, prod["image_url"])
                            await database.mettre_a_jour_stock(
                                url, bool(etat_db["en_stock"]), prod.get("prix")
                            )

                    except Exception as inner_e:
                        logger.error("[%s] Erreur produit: %s", enseigne, inner_e)

                store.terminer("healthy")
                mode = getattr(scraper, "mode_decouverte", None)
                if mode and (modes_connus.get(enseigne) is None or mode == "collections"):
                    await database.ecrire_meta(f"decouverte:{enseigne}", mode)

        except Exception as e:
            store.terminer("timeout")
            logger.error("[%s] Echec scraper: %s", enseigne, e)

        if _sante.enregistrer(enseigne, store.statut):
            logger.warning("[%s] Mise en veille %dmin (échecs répétés).",
                           enseigne, config.STORE_PAUSE_DURATION // 60)
        rapport.ajouter_store(store)
        await _logger_store(cycle_num, rapport.timestamp, store)

    # Les enseignes sont independantes : on les traite EN PARALLELE (la duree du
    # cycle devient celle de la plus lente, pas la somme de toutes).
    await asyncio.gather(*(une_enseigne(e, sc) for e, sc in scrapers_map.items()))
    rapport.terminer()
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

    async def une_enseigne(enseigne, items):
        scraper = scrapers_map.get(enseigne)
        if not scraper:
            logger.warning("Pas de scraper pour '%s', ignoré.", enseigne)
            return
        if _sante.en_veille(enseigne):
            logger.info("[%s] En veille (~%dmin restantes), watchlist sautée.",
                        enseigne, _sante.minutes_restantes(enseigne))
            return

        # Produits disparus (confirmes introuvables) : relus seulement a l'echeance.
        maintenant = time.time()
        items = [i for i in items if (i.get("prochaine_verif") or 0) <= maintenant]
        if not items:
            return

        # Concurrence PAR enseigne : on reste poli avec chaque site tout en
        # interrogeant toutes les enseignes en meme temps.
        sem = asyncio.Semaphore(
            min(config.WATCHLIST_CONCURRENCY, getattr(scraper, "CONCURRENCE_WATCHLIST", 99)))
        store = StoreReport(enseigne=enseigne)
        store.produits_trouves = len(items)
        etat = {"blocages": 0, "stop": False}

        # Lecture GROUPEE (catalogue / liste) : une poignee de requetes pour toute la boutique.
        # Les produits que le lot ne tranche pas ("a_verifier" ou absents) sont relus un par
        # un : on ne devine jamais un stock.
        lot: dict = {}
        if config.WATCHLIST_LOT and hasattr(scraper, "scraper_lot"):
            try:
                lot = await scraper.scraper_lot([i["url"] for i in items]) or {}
            except Exception as e:
                logger.error("[%s] Lecture groupée en échec (%s) : lecture individuelle.",
                             enseigne, e)
                lot = {}
        store.lus_en_lot = sum(1 for i in items
                               if lot.get(i["url"], {}).get("status", "a_verifier") != "a_verifier")
        if lot:
            logger.info("[%s] Lecture groupée : %d/%d produits sans requête individuelle.",
                        enseigne, store.lus_en_lot, len(items))

        async def verifier(item):
            groupe = lot.get(item["url"])
            if groupe is not None and groupe.get("status") != "a_verifier":
                return item, groupe
            async with sem:
                if etat["stop"]:
                    return item, {"status": "skipped"}
                try:
                    res = await scraper.scraper_produit(item["url"])
                except Exception as e:
                    # Un bug de parsing sur UNE fiche ne doit pas faire perdre tout le
                    # cycle de l'enseigne : on la traite comme "inconnue" (etat inchange).
                    logger.error("[%s] Exception scraper_produit %s: %s", enseigne, item["url"], e)
                    res = {"status": "inconnu"}
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

        ok, erreurs, inconnus, absents = 0, 0, 0, 0
        for item, res in resultats:
            statut = res.get("status")
            if statut != "ok":
                if statut == "not_found":
                    absents += 1
                    try:
                        await _constat_introuvable(enseigne, item, store)
                    except Exception as e:
                        logger.error("[%s] Erreur constat disparition %s: %s",
                                     enseigne, item["url"], e)
                elif statut in ("blocked", "timeout"):
                    erreurs += 1
                elif statut == "inconnu":
                    # Fiche lue mais stock indeterminable : on ne touche PAS a l'etat
                    # (ni restock ni rupture), mais on le compte pour detecter une
                    # enseigne dont la page a change (tout "inconnu" != "healthy").
                    inconnus += 1
                continue
            ok += 1
            try:
                if item.get("introuvables") or item.get("prochaine_verif"):
                    await database.reinitialiser_introuvable(item["url"])
                await _traiter_resultat_watchlist(enseigne, item, res, store)
            except Exception as e:
                logger.error("[%s] Erreur traitement %s: %s", enseigne, item["url"], e)

        if etat["stop"] or (erreurs and erreurs >= len(items) // 2 and ok == 0):
            store.terminer("blocked")
        elif erreurs + inconnus + absents > ok:
            store.terminer("parser_error")
        else:
            store.terminer("healthy")

        if _sante.enregistrer(enseigne, store.statut):
            logger.warning("[%s] Mise en veille %dmin (échecs répétés).",
                           enseigne, config.STORE_PAUSE_DURATION // 60)
        rapport.ajouter_store(store)
        await _logger_store(cycle_num, rapport.timestamp, store)

    await asyncio.gather(*(une_enseigne(e, it) for e, it in par_enseigne.items()))
    rapport.terminer()
    return rapport


async def _constat_introuvable(enseigne: str, item: dict, store: StoreReport):
    """Un produit n'est PAS declare disparu sur un seul 404 (page en maintenance, produit
    depublie quelques minutes) : il faut DISPARU_MIN_ECHECS constats consecutifs ET une
    absence continue d'au moins DISPARU_APRES_HEURES. Il est alors declare "disparu" : relu
    seulement toutes les DISPARU_RECHECK_HEURES, SANS toucher a son dernier etat de stock connu
    (une disparition n'est pas une rupture). Les regles de retour sont dans
    `_traiter_resultat_watchlist` (REAPPARITION_ALERTE_HEURES)."""
    url = item["url"]
    n, depuis = await database.marquer_introuvable(url)
    if n >= config.DISPARU_MIN_ECHECS and time.time() - depuis >= config.DISPARU_APRES_HEURES * 3600:
        deja = bool(item.get("prochaine_verif"))
        # L'etat de stock n'est PAS touche : disparaitre n'est pas une rupture constatee.
        await database.marquer_disparu(url, time.time() + config.DISPARU_RECHECK_HEURES * 3600)
        if not deja:
            logger.warning("Produit disparu [%s] après %d constats / %.0f h (stock inchangé): %s",
                           enseigne, n, (time.time() - depuis) / 3600, item["titre"])


async def _traiter_resultat_watchlist(enseigne: str, item: dict, res: dict, store: StoreReport):
    """Applique la logique stock/prix/alerte pour un produit vérifié."""
    url = item["url"]
    en_stock_actuel = res["en_stock"]
    prix_actuel = res.get("prix", "N/A")
    ancien_stock = bool(item["en_stock"])

    # Garde-fou : un produit hors-cible (jouet, livre, food…) peut subsister en base
    # s'il a été ajouté avant un durcissement du filtre. On re-valide ici (titre +
    # marque fraîche) AVANT toute alerte : si ce n'est pas du JCC Pokémon scellé, on
    # le purge et on n'alerte jamais. C'est le filet qui garantit zéro alerte parasite.
    if not item.get("manuel") and not est_tcg_valide_local(item["titre"], res.get("brand", "")):
        logger.info("Purge watchlist (hors-cible) [%s]: %s", enseigne, item["titre"])
        await database.supprimer_produit(url)
        return

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
        # Champs enrichis (donnees structurees schema.org), si disponibles.
        "ean": res.get("ean", ""),
        "brand": res.get("brand", ""),
        "seller": res.get("seller", ""),
        "reference": res.get("reference", ""),
        "stock_quantity": res.get("stock_quantity"),
    }

    # Décision centralisée : on n'agit que sur une vraie transition d'état.
    # (Cette fonction n'est appelée que sur une lecture fiable, statut "ok".)
    action = evaluer_transition(ancien_stock, en_stock_actuel)

    # REAPPARITION d'une fiche declaree "disparue" != CHANGEMENT DE DISPONIBILITE.
    # Son stock en base est le DERNIER ETAT REEL connu (la disparition ne l'a pas modifie) ;
    # seule la comparaison de cet etat avec la lecture actuelle dit s'il y a eu un changement :
    #   - rupture connue  -> en stock : vraie transition => RESTOCK (chemin normal) ;
    #   - en stock connu  -> en stock : AUCUN changement de disponibilite => jamais RESTOCK.
    #     Simple reapparition : comptee, journalisee, et signalee par une alerte distincte
    #     "REAPPARITION" uniquement si ALERTER_REAPPARITION et absence >= REAPPARITION_ALERTE_HEURES ;
    #   - en stock connu  -> rupture : chemin normal (rupture confirmee, sans alerte).
    if item.get("prochaine_verif"):
        store.reapparitions += 1
        depuis = item.get("introuvable_depuis") or item.get("disparu_depuis") or time.time()
        absence_h = (time.time() - depuis) / 3600
        logger.info("RÉAPPARITION [%s]: %s (absent %.0f h, stock connu %s -> lu %s)", enseigne,
                    item["titre"], absence_h, "en stock" if ancien_stock else "rupture",
                    "en stock" if en_stock_actuel else "rupture")
        if (en_stock_actuel and ancien_stock and config.ALERTER_REAPPARITION
                and absence_h >= config.REAPPARITION_ALERTE_HEURES):
            await _alerter(prod_alerte, enseigne, "REAPPARITION")

    if ancien_stock:
        # Une rupture n'est actee qu'apres N lectures "indisponible" consecutives.
        if not _confirmation.rupture_confirmee(url, en_stock_actuel) and not en_stock_actuel:
            logger.info("Rupture à confirmer [%s]: %s", enseigne, item["titre"])
            await database.mettre_a_jour_stock(url, True, prix_actuel)
            return
    else:
        _confirmation.oublier(url)

    if action == RESTOCK:
        logger.info("RESTOCK WATCHLIST [%s]: %s", enseigne, item["titre"])
        await database.mettre_a_jour_stock(url, True, prix_actuel)
        await _alerter(prod_alerte, enseigne, "RESTOCK")
        store.restocks += 1
    elif action == RUPTURE:
        logger.info("RUPTURE WATCHLIST [%s]: %s", enseigne, item["titre"])
        await database.mettre_a_jour_stock(url, False, prix_actuel)
        store.ruptures += 1
    else:
        # Pas de changement de stock : on regarde une éventuelle BAISSE DE PRIX
        # (deal) sur un produit déjà en stock, par rapport au prix précédent.
        if en_stock_actuel and config.DEAL_DROP_PERCENT > 0:
            ancien_prix = parse_price(item.get("prix"))
            nouveau_prix = parse_price(prix_actuel)
            if ancien_prix and nouveau_prix and nouveau_prix < ancien_prix:
                baisse = float((ancien_prix - nouveau_prix) / ancien_prix * 100)
                if baisse >= config.DEAL_DROP_PERCENT:
                    if not _confirmation_prix.confirme(url, str(nouveau_prix)):
                        # Premiere lecture de ce prix : on garde l'ancien prix en base
                        # (reference de comparaison) et on attend la confirmation.
                        logger.info("Baisse de prix à confirmer [%s]: %s (-%.0f%%)",
                                    enseigne, item["titre"], baisse)
                        await database.mettre_a_jour_stock(url, en_stock_actuel, None)
                        return
                    logger.info("DEAL [%s]: %s (-%.0f%%)", enseigne, item["titre"], baisse)
                    prod_deal = dict(prod_alerte, old_price=str(ancien_prix))
                    await _alerter(prod_deal, enseigne, "DEAL")
                else:
                    _confirmation_prix.oublier(url)
            else:
                _confirmation_prix.oublier(url)
        await database.mettre_a_jour_stock(url, en_stock_actuel, prix_actuel)


async def _purger_watchlist() -> int:
    """Nettoie la base des produits hors-cible (déchets accumulés avant durcissement
    du filtre : bières, Smartbox, livres, jouets…). Title-only (la marque n'est pas
    stockée) ; un produit douteux sera de toute façon re-validé en watchlist. Tourne
    à chaque démarrage : self-healing, sans risque pour les vrais produits JCC."""
    produits = await database.recuperer_tous_produits()
    purges = 0
    for p in produits:
        if not p.get("manuel") and not est_tcg_valide_local(p["titre"]):
            await database.supprimer_produit(p["url"])
            logger.info("Purge démarrage (hors-cible) [%s]: %s", p["enseigne"], p["titre"])
            purges += 1
    if purges:
        logger.warning("Purge démarrage : %d produits hors-cible retirés (%d conservés).",
                       purges, len(produits) - purges)
    return purges


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
# Heartbeat : résumé périodique sur Discord (preuve de vie)
# ----------------------------------------------------------------------------
def _build_heartbeat_embed(nb_surveilles: int, restocks: int, nouveautes: int,
                           cycles: int, dernier_rapport) -> dict:
    sains, bloques = [], []
    if dernier_rapport is not None:
        sains = [s.enseigne for s in dernier_rapport.stores if s.statut == "healthy"]
        bloques = [s.enseigne for s in dernier_rapport.stores
                   if s.statut in ("blocked", "timeout", "parser_error", "empty")]
    return {
        "title": "💓 TCG-STOCK-BOT — résumé",
        "color": 0x2ECC71,
        "fields": [
            {"name": "Produits surveillés", "value": str(nb_surveilles), "inline": True},
            {"name": "Cycles", "value": str(cycles), "inline": True},
            {"name": "Restocks", "value": str(restocks), "inline": True},
            {"name": "Nouveautés", "value": str(nouveautes), "inline": True},
            {"name": "Enseignes OK", "value": ", ".join(sains) or "—", "inline": False},
            {"name": "Enseignes en difficulté", "value": ", ".join(bloques) or "—", "inline": False},
        ],
        "footer": {"text": "Bot en vie ✅"},
    }


async def _envoyer_heartbeat(restocks: int, nouveautes: int, cycles: int, dernier_rapport):
    try:
        produits = await database.recuperer_tous_produits()
        embed = _build_heartbeat_embed(len(produits), restocks, nouveautes, cycles, dernier_rapport)
        await envoyer_message(embed)
        logger.info("Heartbeat envoyé (%d produits surveillés).", len(produits))
    except Exception as e:
        logger.warning("Échec envoi heartbeat: %s", e)


# ----------------------------------------------------------------------------
# Boucle principale
# ----------------------------------------------------------------------------
async def _dormir(duree: float, stop_event):
    """Sommeil interruptible : se réveille immédiatement si l'arrêt est demandé."""
    if stop_event is None:
        await asyncio.sleep(duree)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=duree)
    except asyncio.TimeoutError:
        pass


async def main_loop(stop_event=None):
    """Boucle principale.

    `stop_event` (asyncio.Event, optionnel) : si fourni, l'appli/IHM peut demander
    un arrêt propre en le déclenchant — la boucle sort et libère les ressources.
    Sans argument, comportement CLI inchangé (tourne jusqu'à Ctrl+C / RUN_ONCE).
    """
    filtre = "Gemini + local" if config.USE_GEMINI_FILTER else "local"
    logger.info(
        "Démarrage TCG-STOCK-BOT (filtre: %s, recherche toutes les %d cycles, "
        "concurrence watchlist: %d)...",
        filtre, config.SEARCH_INTERVAL, config.WATCHLIST_CONCURRENCY,
    )
    await database.initialiser_db()
    purges = await database.purger_historique_prix(config.HISTORY_RETENTION_DAYS)
    if purges:
        logger.info("Historique de prix purgé : %d points anciens supprimés.", purges)
    # Nettoie les produits hors-cible déjà en base (déchets pré-filtre).
    await _purger_watchlist()

    # Mode bot (optionnel) : démarre la passerelle qui écoute les clics de boutons
    # (fondation autobuy). L'envoi des alertes reste géré par discord_webhook.
    bot_task = None
    if config.DISCORD_BOT_TOKEN and config.DISCORD_CHANNEL_ID:
        try:
            import discord_bot
            bot_task = asyncio.create_task(discord_bot.demarrer())
            logger.info("Mode bot Discord activé (boutons + écoute autobuy).")
        except ImportError:
            logger.warning("discord.py non installé — mode bot ignoré "
                           "(pip install discord.py).")

    # Scrapers construits SANS navigateur d'abord ; on ne lance Playwright que si une
    # enseigne activée en a réellement besoin (sites blindés). Les 5 sources par
    # défaut sont en HTTP/JSON → aucun navigateur (mode léger, idéal appli packagée).
    tous_scrapers = construire_tous(None)
    scrapers_map = {k: v for k, v in tous_scrapers.items() if k in config.ENABLED_STORES}
    ignorees = [k for k in tous_scrapers if k not in scrapers_map]
    logger.info("Enseignes actives : %s%s", ", ".join(scrapers_map) or "AUCUNE",
                f" (désactivées : {', '.join(ignorees)})" if ignorees else "")
    if not scrapers_map:
        logger.error("Aucune enseigne active (ENABLED_STORES vide ?). Arrêt.")
        return

    # Navigateur seulement si une enseigne activée en a besoin.
    playwright_ctx = None
    browser = None
    if any(getattr(s, "utilise_navigateur", True) for s in scrapers_map.values()):
        # Import paresseux : en mode léger (sources HTTP), Playwright n'est jamais
        # requis — pratique pour l'app empaquetée qui ne l'embarque pas forcément.
        from playwright.async_api import async_playwright
        playwright_ctx = await async_playwright().start()
        browser = await playwright_ctx.chromium.launch(headless=True)
        for s in scrapers_map.values():
            s.browser = browser
        logger.info("Navigateur Playwright lancé (une enseigne protégée est activée).")
    else:
        logger.info("Mode léger : aucune enseigne protégée → pas de navigateur lancé.")

    cycle_num = 0
    # Compteurs pour le heartbeat (réinitialisés à chaque résumé envoyé).
    hb_restocks, hb_nouveautes, hb_cycles = 0, 0, 0
    derniere_heartbeat = time.time()
    dernier_rapport = None
    alertes_total = 0
    _compteur_alertes["total"] = 0

    # Amorçage : si la base est vide au démarrage, le 1er cycle remplit la
    # watchlist SANS alerter (évite l'inondation au lancement officiel).
    amorcage_initial = len(await database.recuperer_tous_produits()) == 0
    if amorcage_initial:
        logger.info("Base vide : 1er cycle en AMORÇAGE silencieux (aucune alerte).")

    bot_state.set_status(running=True, demarre_a=time.time(), cycle=0,
                         alertes_total=0, dernier_resume="", enseignes={})
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                logger.info("Arrêt demandé — sortie propre de la boucle.")
                break
            cycle_num += 1
            debut_cycle = time.time()
            logger.info("=== CYCLE %d ===", cycle_num)

            # Résilience : une erreur inattendue dans un cycle ne doit JAMAIS
            # tuer le bot. On logge et on passe au cycle suivant.
            try:
                est_recherche = (cycle_num == 1 or cycle_num % config.SEARCH_INTERVAL == 0)
                if est_recherche:
                    rapport = await cycle_recherche(
                        scrapers_map, cycle_num,
                        amorcage=(cycle_num == 1 and amorcage_initial),
                    )
                else:
                    rapport = await cycle_watchlist(scrapers_map, cycle_num)

                resume = rapport.resume()
                logger.info(resume)
                dernier_rapport = rapport
                hb_cycles += 1
                hb_restocks += sum(s.restocks for s in rapport.stores)
                hb_nouveautes += sum(s.nouveautes for s in rapport.stores)
                # Compteur basé sur les alertes RÉELLEMENT envoyées (pas les
                # nouveautés : l'amorçage silencieux n'envoie rien).
                alertes_total = _compteur_alertes["total"]

                # Statut live pour l'interface graphique.
                try:
                    produits = await database.recuperer_tous_produits()
                    bot_state.set_status(
                        cycle=cycle_num,
                        mode="recherche" if est_recherche else "watchlist",
                        produits=len(produits),
                        alertes_total=alertes_total,
                        dernier_resume=resume,
                        enseignes={s.enseigne: s.statut for s in rapport.stores},
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error("Erreur cycle %d (le bot continue): %s", cycle_num, e,
                             exc_info=True)

            if config.RUN_ONCE:
                logger.info("RUN_ONCE actif. Arrêt.")
                break

            # Heartbeat périodique (preuve de vie + bilan).
            if (config.HEARTBEAT_INTERVAL > 0
                    and time.time() - derniere_heartbeat >= config.HEARTBEAT_INTERVAL):
                await _envoyer_heartbeat(hb_restocks, hb_nouveautes, hb_cycles, dernier_rapport)
                hb_restocks, hb_nouveautes, hb_cycles = 0, 0, 0
                derniere_heartbeat = time.time()

            duree = calculer_pause(time.time() - debut_cycle, config.MIN_SLEEP,
                                   config.MAX_SLEEP, config.MIN_CYCLE_GAP, random.random())
            logger.info("Cycle en %.1fs ; prochain cycle dans %.0fs.",
                        time.time() - debut_cycle, duree)
            await _dormir(duree, stop_event)
    finally:
        bot_state.set_status(running=False)
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright_ctx is not None:
            try:
                await playwright_ctx.stop()
            except Exception:
                pass
        try:
            from discord_webhook import fermer_session
            await fermer_session()
            await database.fermer()
        except Exception:
            pass
        if bot_task is not None:
            import discord_bot
            try:
                await discord_bot.arreter()
            except Exception:
                pass
            bot_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Arrêt manuel.")
    except Exception as e:
        logger.critical("Erreur fatale: %s", e, exc_info=True)
