"""
audit_scrapers.py - Audit REEL et reutilisable des scrapers (lecture seule).

Pour chaque enseigne : recherche (quelques mots-cles), controle de qualite des
resultats (URL, prix, pertinence JCC, doublons), puis relecture de la fiche d'un petit
echantillon de produits et comparaison recherche <-> fiche (stock, prix).

Garanties :
  - aucune ecriture en base, AUCUN envoi Discord (ni main, ni discord_webhook importes) ;
  - aucun service payant : le secours par proxy/scraping API est force a OFF ;
  - charge reduite : peu de mots-cles, echantillon limite, pauses entre fiches ;
  - aucun contournement de CAPTCHA : un blocage est REPORTE comme tel, pas combattu.

Usage :
    python tools/audit_scrapers.py                       # enseignes actives
    python tools/audit_scrapers.py --all                 # + enseignes desactivees
    python tools/audit_scrapers.py --stores Auchan,Leclerc --samples 4
    python tools/audit_scrapers.py --browser             # autorise Playwright (sites blindes)
    python tools/audit_scrapers.py --json audit.json     # export des mesures brutes

Verdicts : FONCTIONNEL / PARTIEL / DEFAILLANT / NON TESTE (necessite --browser).
"""
import argparse
import asyncio
import json
import os
import sys
import time
from urllib.parse import urlsplit

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import config  # noqa: E402

config.PROXY_FALLBACK = False   # jamais de service tiers (potentiellement payant) en audit

from filter_utils import est_tcg_valide_local, _normaliser, MOTS_UNIVERS  # noqa: E402
from product_format import parse_price  # noqa: E402
from scrapers.registry import construire_tous  # noqa: E402
from store_domains import enseigne_pour_hote  # noqa: E402

MOTS_CLES_AUDIT = ["pokemon display", "pokemon coffret", "one piece display", "one piece booster"]
TIMEOUT_ENSEIGNE_S = 240
PRIX_MAX_PLAUSIBLE = 5000.0


def _prix_float(valeur) -> float | None:
    p = parse_price(str(valeur or ""))
    return float(p) if p is not None else None


def analyser_produits(enseigne: str, produits: list[dict]) -> dict:
    """Controles de qualite sur les resultats d'une recherche (pur, testable hors reseau)."""
    n = len(produits)
    urls = [p.get("url", "") for p in produits]
    mauvaises_urls, prix_ok, prix_aberrants, valides, en_stock = [], 0, [], 0, 0
    univers = 0
    en_stock_sans_prix = 0
    sans_titre = 0
    for p in produits:
        u = urlsplit(p.get("url", ""))
        if u.scheme != "https" or enseigne_pour_hote(u.hostname or "") != enseigne:
            mauvaises_urls.append(p.get("url", ""))
        prix = _prix_float(p.get("prix"))
        if prix is not None:
            prix_ok += 1
            if not (0 < prix <= PRIX_MAX_PLAUSIBLE):
                prix_aberrants.append((p.get("titre", "")[:40], p.get("prix")))
        if not (p.get("titre") or "").strip():
            sans_titre += 1
        if est_tcg_valide_local(p.get("titre", ""), p.get("brand", "")):
            valides += 1
        if any(u in _normaliser(f"{p.get('titre', '')} {p.get('brand', '')}") for u in MOTS_UNIVERS):
            univers += 1
        if p.get("en_stock"):
            en_stock += 1
            if _prix_float(p.get("prix")) is None:
                en_stock_sans_prix += 1
    return {
        "total": n,
        "doublons": n - len(set(urls)),
        "urls_invalides": mauvaises_urls[:5],
        "nb_urls_invalides": len(mauvaises_urls),
        "avec_prix": prix_ok,
        "prix_aberrants": prix_aberrants[:5],
        "sans_titre": sans_titre,
        "valides_jcc": valides,
        "univers_cible": univers,   # titres citant Pokemon / One Piece (pertinence de la recherche)
        "en_stock": en_stock,
        "en_stock_sans_prix": en_stock_sans_prix,   # alertable mais sans prix = anomalie
    }


def comparer_fiche(recherche: dict, fiche: dict) -> dict:
    """Compare une ligne de recherche et la fiche relue (pur, testable hors reseau)."""
    res = {"titre": recherche.get("titre", "")[:50], "url": recherche.get("url", ""),
           "statut_fiche": fiche.get("status"),
           "stock_recherche": bool(recherche.get("en_stock")),
           "stock_fiche": bool(fiche.get("en_stock")) if fiche.get("status") == "ok" else None,
           "prix_recherche": recherche.get("prix"), "prix_fiche": fiche.get("prix")}
    res["stock_coherent"] = (None if res["stock_fiche"] is None
                             else res["stock_fiche"] == res["stock_recherche"])
    a, b = _prix_float(recherche.get("prix")), _prix_float(fiche.get("prix"))
    res["prix_coherent"] = (None if a is None or b is None else abs(a - b) <= max(0.5, 0.02 * a))
    return res


def verdict(r: dict) -> tuple[str, list[str]]:
    """Verdict + raisons a partir des mesures d'une enseigne."""
    raisons = []
    if r.get("non_teste"):
        return "NON TESTE", [r["non_teste"]]
    if r.get("exception"):
        return "DEFAILLANT", [f"exception: {r['exception']}"]
    if r["statut_recherche"] != "ok":
        return "DEFAILLANT", [f"recherche en statut '{r['statut_recherche']}'"]
    q = r["qualite"]
    if q["total"] == 0:
        return "DEFAILLANT", ["recherche OK mais 0 produit (parsing ou site vide)"]
    partiel = False
    # Recherche pertinente ? Les requetes portent toutes sur Pokemon / One Piece : si
    # presque aucun resultat n'en parle, la liste n'est PAS le resultat de la recherche
    # (page generique, recherche rendue cote client...).
    if q.get("univers_cible", q["total"]) / q["total"] < 0.05 and q["total"] >= 10:
        return "DEFAILLANT", ["resultats sans rapport avec la requete (recherche non exploitable)"]
    if q["valides_jcc"] == 0:
        partiel = True
        raisons.append("aucun produit ne passe le filtre JCC")
    if q["nb_urls_invalides"]:
        partiel = True
        raisons.append(f"{q['nb_urls_invalides']} URL hors domaine/https")
    # Un prix absent n'est un defaut que pour un produit "en stock" (un produit en rupture ou
    # vendu seulement par des tiers peut legitimement n'avoir aucun prix chez l'enseigne).
    if q["prix_aberrants"] or q.get("en_stock_sans_prix", 0):
        partiel = True
        raisons.append("prix aberrants ou produits en stock sans prix")
    if q["doublons"]:
        raisons.append(f"{q['doublons']} doublons")
    fiches = r["fiches"]
    if not fiches:
        partiel = True
        raisons.append("aucune fiche relue (rien a comparer)")
    else:
        ko = [f for f in fiches if f["statut_fiche"] != "ok"]
        if ko:
            partiel = True
            raisons.append(f"{len(ko)}/{len(fiches)} fiches illisibles "
                           f"({', '.join(sorted({str(f['statut_fiche']) for f in ko}))})")
        inco = [f for f in fiches if f["stock_coherent"] is False]
        if inco:
            partiel = True
            raisons.append(f"{len(inco)} incoherences de stock recherche/fiche")
        pinco = [f for f in fiches if f["prix_coherent"] is False]
        if pinco:
            partiel = True
            raisons.append(f"{len(pinco)} incoherences de prix recherche/fiche")
    return ("PARTIEL" if partiel else "FONCTIONNEL"), raisons


def _echantillon(produits: list[dict], n: int) -> list[dict]:
    """Echantillon varie : produits JCC valides, moitie en stock / moitie en rupture."""
    valides = [p for p in produits if est_tcg_valide_local(p.get("titre", ""), p.get("brand", ""))]
    stock = [p for p in valides if p.get("en_stock")]
    rupt = [p for p in valides if not p.get("en_stock")]
    choix = stock[: (n + 1) // 2] + rupt[: n // 2]
    for p in valides:           # complete si un des deux groupes manque
        if len(choix) >= n:
            break
        if p not in choix:
            choix.append(p)
    return choix[:n]


async def auditer(nom: str, scraper, samples: int, pause: float) -> dict:
    r = {"enseigne": nom, "statut_recherche": "?", "duree_recherche_s": 0.0,
         "qualite": {}, "fiches": [], "exemples": []}
    if getattr(scraper, "utilise_navigateur", True) and scraper.browser is None:
        r["non_teste"] = "enseigne a navigateur (Playwright) : relancer avec --browser"
        return r
    try:
        t0 = time.perf_counter()
        produits = await asyncio.wait_for(scraper.scraper_recherche(), TIMEOUT_ENSEIGNE_S)
        r["duree_recherche_s"] = round(time.perf_counter() - t0, 1)
        r["statut_recherche"] = getattr(scraper, "_last_status", "ok")
        r["qualite"] = analyser_produits(nom, produits)
        r["exemples"] = [{"titre": p.get("titre", "")[:60], "prix": p.get("prix"),
                          "en_stock": p.get("en_stock"), "url": p.get("url")}
                         for p in _echantillon(produits, 3)]
        for p in _echantillon(produits, samples):
            t1 = time.perf_counter()
            try:
                fiche = await asyncio.wait_for(scraper.scraper_produit(p["url"]), 90)
            except Exception as e:  # noqa: BLE001
                fiche = {"status": f"exception:{type(e).__name__}"}
            c = comparer_fiche(p, fiche)
            c["duree_s"] = round(time.perf_counter() - t1, 1)
            r["fiches"].append(c)
            await asyncio.sleep(pause)
    except Exception as e:  # noqa: BLE001
        r["exception"] = f"{type(e).__name__}: {e}"
    return r


def rendre_markdown(resultats: list[dict]) -> str:
    lignes = ["| Enseigne | Verdict | Recherche | Produits (JCC) | En stock | Fiches OK | Stock coherent | Prix coherent | Remarques |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in resultats:
        v, raisons = verdict(r)
        r["verdict"], r["raisons"] = v, raisons
        q = r.get("qualite") or {}
        f = r["fiches"]
        ok = sum(1 for x in f if x["statut_fiche"] == "ok")
        sc = [x["stock_coherent"] for x in f if x["stock_coherent"] is not None]
        pc = [x["prix_coherent"] for x in f if x["prix_coherent"] is not None]
        lignes.append(
            f"| {r['enseigne']} | **{v}** | {r['statut_recherche']} ({r['duree_recherche_s']}s) | "
            f"{q.get('total', '-')} ({q.get('valides_jcc', '-')}) | {q.get('en_stock', '-')} | "
            f"{ok}/{len(f)} | {sum(sc)}/{len(sc)} | {sum(pc)}/{len(pc)} | {'; '.join(raisons) or '-'} |")
    return "\n".join(lignes)


async def principal(args) -> list[dict]:
    config.SEARCH_KEYWORDS = MOTS_CLES_AUDIT[: args.keywords]
    pw = browser = None
    if args.browser:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
    try:
        tous = construire_tous(browser)
        if args.stores:
            noms = [s.strip() for s in args.stores.split(",") if s.strip()]
        elif args.all:
            noms = list(tous)
        else:
            noms = [s for s in config.ENABLED_STORES if s in tous]
        inconnus = [n for n in noms if n not in tous]
        if inconnus:
            print("Enseignes inconnues :", ", ".join(inconnus))
        resultats = []
        for nom in [n for n in noms if n in tous]:
            print(f"-> audit {nom}...", flush=True)
            resultats.append(await auditer(nom, tous[nom], args.samples, args.pause))
        return resultats
    finally:
        if browser:
            await browser.close()
        if pw:
            await pw.stop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stores", help="liste separee par des virgules")
    ap.add_argument("--all", action="store_true", help="inclut les enseignes desactivees")
    ap.add_argument("--keywords", type=int, default=4, help="nb de mots-cles (max 4)")
    ap.add_argument("--samples", type=int, default=4, help="nb de fiches relues par enseigne")
    ap.add_argument("--pause", type=float, default=1.0, help="pause entre fiches (s)")
    ap.add_argument("--browser", action="store_true", help="autorise Playwright")
    ap.add_argument("--json", help="ecrit les mesures brutes dans ce fichier")
    args = ap.parse_args()
    resultats = asyncio.run(principal(args))
    print()
    print(rendre_markdown(resultats))
    for r in resultats:
        for e in r.get("exemples", []):
            print(f"  [{r['enseigne']}] {e['titre']} | {e['prix']} | stock={e['en_stock']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultats, f, ensure_ascii=False, indent=2, default=str)
        print("\nMesures ecrites dans", args.json)


if __name__ == "__main__":
    main()
