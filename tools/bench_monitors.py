"""
bench_monitors.py - Mesure reelle des performances des monitors (lecture seule).

Pour chaque enseigne : base temporaire -> 1 cycle de DECOUVERTE (silencieux) puis N cycles de
WATCHLIST, en comptant les requetes HTTP reellement emises et la duree. Option --parite :
compare, produit par produit, la lecture groupee (catalogue) a la lecture individuelle
(fiche) pour mesurer la fiabilite.

Garanties : aucun envoi Discord (envoyer_alerte remplace par un enregistreur), aucun proxy
payant, base temporaire supprimee. Charge limitee (peu de cycles, pauses entre cycles).

Usage :
    python tools/bench_monitors.py --stores Dracaugames,CoinBarons --cycles 2
    python tools/bench_monitors.py --stores Dracaugames --sans-lot      # ancien mode
    python tools/bench_monitors.py --stores CoinBarons --parite --json bench.json
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
import time

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config  # noqa: E402

config.PROXY_FALLBACK = False
config.ENABLE_PRICE_CHART = False

import database  # noqa: E402
import http_fetch  # noqa: E402
import main  # noqa: E402
from scrapers.registry import construire_tous  # noqa: E402

ALERTES: list = []


async def _enregistreur(prod, enseigne, type_alerte, chart_png=None):
    ALERTES.append((enseigne, type_alerte, prod.get("url")))
    return True


class Compteur:
    """Compte les requetes HTTP reelles (niveau le plus bas de http_fetch)."""

    def __init__(self):
        self.n = 0
        self._reel = http_fetch._get_sans_redirection

    async def _compte(self, *a, **k):
        self.n += 1
        return await self._reel(*a, **k)

    def __enter__(self):
        http_fetch._get_sans_redirection = self._compte
        return self

    def __exit__(self, *e):
        http_fetch._get_sans_redirection = self._reel


async def bench_enseigne(nom: str, scraper, cycles: int, pause: float, parite: bool) -> dict:
    fd, chemin = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.DB_PATH = chemin
    await database.initialiser_db()
    main._sante = main.StoreHealth(seuil=99, pause_s=1)
    r = {"enseigne": nom, "lot": bool(getattr(config, "WATCHLIST_LOT", False)
                                       and hasattr(scraper, "scraper_lot"))}
    try:
        with Compteur() as c:
            t0 = time.perf_counter()
            rap = await main.cycle_recherche({nom: scraper}, 1)
            r["decouverte_s"] = round(time.perf_counter() - t0, 1)
            r["decouverte_req"] = c.n
            r["statut_decouverte"] = rap.stores[0].statut if rap.stores else "?"
        produits = await database.recuperer_tous_produits()
        r["produits"] = len(produits)
        r["en_stock"] = sum(1 for p in produits if p["en_stock"])
        r["watchlist"] = []
        for i in range(cycles):
            await asyncio.sleep(pause)
            with Compteur() as c:
                t0 = time.perf_counter()
                rap = await main.cycle_watchlist({nom: scraper}, 2 + i)
                r["watchlist"].append({
                    "duree_s": round(time.perf_counter() - t0, 1), "requetes": c.n,
                    "statut": rap.stores[0].statut if rap.stores else "?",
                    "restocks": sum(s.restocks for s in rap.stores),
                    "ruptures": sum(s.ruptures for s in rap.stores)})
        if parite and hasattr(scraper, "scraper_lot"):
            r["parite"] = await _parite(scraper, [p["url"] for p in produits])
    finally:
        await database.fermer()
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(chemin + ext)
            except OSError:
                pass
    return r


async def _parite(scraper, urls: list[str]) -> dict:
    """Lecture groupee vs lecture individuelle, produit par produit."""
    with Compteur() as c:
        lot = await scraper.scraper_lot(urls)
        req_lot = c.n
    ecarts, comparables, via_lot = [], 0, 0
    for u in urls:
        res_lot = lot.get(u)
        if not res_lot or res_lot.get("status") != "ok":
            continue
        via_lot += 1
        indiv = await scraper.scraper_produit(u)
        if indiv.get("status") != "ok":
            continue
        comparables += 1
        if bool(res_lot["en_stock"]) != bool(indiv["en_stock"]) or (
                res_lot["prix"] != indiv["prix"]):
            ecarts.append({"url": u, "lot": [res_lot["en_stock"], res_lot["prix"]],
                           "individuel": [indiv["en_stock"], indiv["prix"]]})
        await asyncio.sleep(0.2)
    return {"requetes_lot": req_lot, "lus_en_lot": via_lot, "comparables": comparables,
            "ecarts": ecarts[:10], "nb_ecarts": len(ecarts)}


def rendre(resultats: list[dict]) -> str:
    lignes = ["| Enseigne | Mode | Produits | Découverte (req / s) | Watchlist (req / s) | Statut | Parité |",
              "|---|---|---|---|---|---|---|"]
    for r in resultats:
        w = r.get("watchlist") or [{}]
        moy_req = sum(x.get("requetes", 0) for x in w) / max(len(w), 1)
        moy_s = sum(x.get("duree_s", 0) for x in w) / max(len(w), 1)
        p = r.get("parite")
        par = (f"{p['comparables'] - p['nb_ecarts']}/{p['comparables']} identiques "
               f"({p['requetes_lot']} req)") if p else "-"
        lignes.append(
            f"| {r['enseigne']} | {'lot' if r['lot'] else 'fiche par fiche'} | {r.get('produits', '-')} "
            f"({r.get('en_stock', '-')} en stock) | {r.get('decouverte_req', '-')} / {r.get('decouverte_s', '-')} s "
            f"| {moy_req:.0f} / {moy_s:.1f} s | {r.get('statut_decouverte', '?')}/{w[-1].get('statut', '?')} | {par} |")
    return "\n".join(lignes)


async def principal(args):
    main.envoyer_alerte = _enregistreur
    if args.sans_lot:
        config.WATCHLIST_LOT = False
    tous = construire_tous(None)
    res = []
    for nom in [s.strip() for s in args.stores.split(",") if s.strip()]:
        if nom not in tous:
            print("Enseigne inconnue :", nom)
            continue
        print(f"-> bench {nom}...", flush=True)
        res.append(await bench_enseigne(nom, tous[nom], args.cycles, args.pause, args.parite))
    return res


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stores", default="Dracaugames,CoinBarons,LudiJeux,RelicTCG")
    ap.add_argument("--cycles", type=int, default=2, help="cycles de watchlist mesures")
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--sans-lot", action="store_true", help="desactive la lecture groupee")
    ap.add_argument("--parite", action="store_true", help="compare lot vs individuel")
    ap.add_argument("--json")
    args = ap.parse_args()
    res = asyncio.run(principal(args))
    print()
    print(rendre(res))
    print(f"\nAlertes simulees pendant le bench : {len(ALERTES)} (aucun envoi reel)")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main_cli()
