"""
Testeur de boutique — dis-moi si un site est ajoutable au bot (gratuitement).

Usage :
    python tools/tester_boutique.py https://www.exemple.fr
    python tools/tester_boutique.py exemple.fr

Il teste les 2 "portes d'entrée" gratuites que le bot sait exploiter :
  - Shopify       -> /search/suggest.json   (scraper: shopify.py)
  - WooCommerce   -> /wp-json/wc/store/v1/products  (scraper: woocommerce.py)

Si c'est VERT, ajoute la boutique dans .env :
  SHOPIFY_SHOPS=...,MonNom=exemple.fr     (ou WOO_SHOPS=...,MonNom=exemple.fr)
  ENABLED_STORES=...,MonNom
"""
import asyncio
import json
import sys
from urllib.parse import urlparse

import aiohttp

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _domaine(arg: str) -> str:
    arg = arg.strip()
    if "://" in arg:
        arg = urlparse(arg).netloc
    return arg.split("/")[0].replace("www.", "")


async def _get(session, url):
    try:
        async with session.get(url, headers=UA, timeout=aiohttp.ClientTimeout(total=15),
                               allow_redirects=True) as r:
            return r.status, await r.text(errors="ignore")
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


async def tester(domaine: str):
    print(f"\n🔎 Test de « {domaine} »...\n")
    async with aiohttp.ClientSession() as s:
        for host in (f"www.{domaine}", domaine):
            # --- Shopify (recherche prédictive) ---
            st, txt = await _get(
                s, f"https://{host}/search/suggest.json"
                   "?q=pokemon&resources[type]=product&resources[limit]=3")
            if st == 200:
                try:
                    prods = json.loads(txt)["resources"]["results"]["products"]
                    if prods:
                        print(f"✅ SHOPIFY détecté ({host}) — {len(prods)} produits trouvés.")
                        print(f"   ex: {prods[0]['title'][:55]} — {prods[0].get('price')}€")
                        print(f"\n👉 À ajouter : SHOPIFY_SHOPS=...,NomCourt={domaine}")
                        return
                except (ValueError, KeyError, TypeError):
                    pass  # 200 mais pas du JSON exploitable (recherche désactivée)

            # --- WooCommerce (Store API) ---
            st, txt = await _get(
                s, f"https://{host}/wp-json/wc/store/v1/products?search=pokemon&per_page=3")
            if st == 200 and isinstance(txt, str) and txt.strip().startswith("["):
                try:
                    arr = json.loads(txt)
                    if arr:
                        print(f"✅ WOOCOMMERCE détecté ({host}) — {len(arr)} produits trouvés.")
                        print(f"   ex: {arr[0].get('name', '')[:55]}")
                        print(f"\n👉 À ajouter : WOO_SHOPS=...,NomCourt={domaine}")
                        return
                except ValueError:
                    pass

    print("❌ Pas de porte d'entrée gratuite détectée (ni Shopify, ni WooCommerce).")
    print("   Le site est peut-être en PrestaShop, protégé (Cloudflare), ou injoignable.")
    print("   -> non ajoutable automatiquement pour l'instant.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python tools/tester_boutique.py <url-ou-domaine>")
        sys.exit(1)
    asyncio.run(tester(_domaine(sys.argv[1])))
