# 📦 Empaqueter l'appli en `.exe` (et livrer la machine de Tom)

Ce guide transforme le projet Python en **un seul installateur Windows**
(`TCGStockBot-Setup.exe`) que Tom double-clique. Aucune ligne de commande, aucune
clé à saisir, aucun code à toucher de son côté.

## Pré-requis (sur TA machine de build, une seule fois)
```powershell
pip install -r requirements.txt      # inclut PySide6
pip install pyinstaller
```
Et **Inno Setup 6** (gratuit) pour fabriquer l'installateur :
https://jrsoftware.org/isdl.php  (ou `winget install JRSoftware.InnoSetup`)

## (Option) Pré-configurer pour Tom — « zéro réglage »
Pour livrer la machine **déjà branchée** à ton Discord :
1. Copie `bundled_settings.example.json` en **`bundled_settings.json`**.
2. Mets dedans l'URL du **webhook** (ou le jeton bot + l'ID du salon).
3. Ce fichier sera embarqué dans l'exe → à la 1ʳᵉ ouverture, c'est déjà configuré
   (l'assistant ne s'affiche pas).
> ⚠️ `bundled_settings.json` contient un secret : il est **gitignoré**, ne le pousse jamais.
> Si tu sautes cette étape, l'**assistant de 1ʳᵉ config** s'affiche au 1er lancement.

## Construire (tout en une commande)
```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```
Ce script :
1. lance **PyInstaller** (`TCGStockBot.spec`) → `dist\TCGStockBot\` ;
2. fait un **selftest** de l'exe (vérifie que l'IHM charge) ;
3. compile l'**installateur** → `Output\TCGStockBot-Setup.exe` (si Inno Setup est là).

> Build manuel équivalent :
> ```powershell
> pyinstaller --noconfirm TCGStockBot.spec
> iscc installer.iss
> ```

## Livrer à Tom
Envoie-lui **`Output\TCGStockBot-Setup.exe`**. Il double-clique :
- installation **sans droits administrateur** (dans son dossier utilisateur) ;
- coche éventuellement « Lancer au démarrage de Windows » (surveillance 24h/24) ;
- l'appli se lance, il clique **Démarrer**. Fermer la fenêtre la **réduit dans la
  barre des tâches** (le bot continue) ; pour vraiment quitter : clic droit sur
  l'icône → **Quitter**.

## Bon à savoir
- **Données** (base, réglages) : `%APPDATA%\TCGStockBot\` — elles **survivent** aux
  mises à jour/réinstallations.
- **Navigateur Playwright** non embarqué (inutile : les enseignes par défaut sont en
  HTTP/JSON). L'appli tourne en **mode léger**.
- **Mettre à jour** : reconstruis et renvoie le nouveau Setup ; il s'installe par-dessus.
- **Vérifier un build** sans interface : `dist\TCGStockBot\TCGStockBot.exe --selftest`.
