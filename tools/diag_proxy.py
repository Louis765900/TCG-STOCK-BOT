"""Teste le filet de secours : récupère l'API Leclerc via chaque proxy configuré."""
import os
import sys
import json
import asyncio

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))
sys.path.insert(0, os.path.join(_RACINE, "desktop"))

import config
from proxy_fetch import _fournisseurs, fetch_via_proxy

URL = "https://www.e.leclerc/api/rest/live-api/product-search?text=pokemon%20booster"


async def main():
    fournisseurs = _fournisseurs()
    print("Fournisseurs configures :", [n for n, _ in fournisseurs] or "AUCUN")
    if not fournisseurs:
        print("Aucune cle -> filet de secours inactif.")
        return
    texte = await fetch_via_proxy(URL)
    if not texte:
        print("ECHEC : aucun fournisseur n'a ramene la page.")
        return
    try:
        data = json.loads(texte)
        n = len(data.get("items", [])) if isinstance(data, dict) else "?"
        print(f"SUCCES : JSON Leclerc recupere via secours ({n} items).")
    except Exception:
        print(f"Reponse recue ({len(texte)} caracteres) mais pas du JSON :")
        print(texte[:200])


if __name__ == "__main__":
    asyncio.run(main())
