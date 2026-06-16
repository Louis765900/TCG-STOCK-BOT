@echo off
REM ============================================================
REM  Lance TCG-STOCK-BOT et le RELANCE automatiquement s'il
REM  s'arrete (crash, coupure reseau, etc.). Pour un fonctionnement 24h/24.
REM  Double-clique ce fichier, ou lance-le depuis le Planificateur de taches.
REM  Pour arreter pour de bon : ferme la fenetre.
REM ============================================================
cd /d "%~dp0"

REM Active l'environnement virtuel s'il existe
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

:loop
echo [%date% %time%] Demarrage du bot...
python main.py
echo [%date% %time%] Bot arrete (code %errorlevel%). Redemarrage dans 15s...
timeout /t 15 /nobreak >nul
goto loop
