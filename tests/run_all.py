"""Lance tous les tests du dossier tests/. Usage : python tests/run_all.py"""
import importlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))       # cœur du bot
sys.path.insert(0, os.path.join(ROOT, "desktop"))   # appli graphique (tests GUI)
sys.path.insert(0, HERE)

noms = sorted(f[:-3] for f in os.listdir(HERE)
              if f.startswith("test_") and f.endswith(".py"))

ok = fail = 0
for nom in noms:
    try:
        module = importlib.import_module(nom)
        module.test()
        print(f"PASS  {nom}")
        ok += 1
    except Exception:
        print(f"FAIL  {nom}")
        traceback.print_exc()
        fail += 1

print(f"\n=== {ok} réussis, {fail} échoués sur {len(noms)} ===")
sys.exit(1 if fail else 0)
