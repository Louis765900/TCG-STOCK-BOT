@echo off
REM ============================================================
REM  TCG-STOCK-BOT - Lanceur terminal (24h/24)
REM  Double-clique ce fichier pour demarrer le bot.
REM   - 1er lancement : installe les dependances automatiquement.
REM   - Relance le bot tout seul s'il s'arrete (crash, coupure reseau...).
REM  Pour arreter pour de bon : ferme cette fenetre.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

REM --- Choix de Python (py launcher sinon python) ---
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

REM --- Verifie que Python est installe ---
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou absent du PATH.
    echo Installe Python 3 depuis https://www.python.org/downloads/ ^(coche "Add to PATH"^).
    pause
    exit /b 1
)

REM --- Active un venv s'il existe (sinon Python systeme) ---
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

REM --- Dependances : installees une seule fois (marqueur .deps_ok) ---
if not exist ".deps_ok" (
    echo Installation des dependances ^(uniquement la 1re fois, patiente un peu^)...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERREUR] L'installation des dependances a echoue.
        pause
        exit /b 1
    )
    echo ok> .deps_ok
)

REM --- Avertissement si la config Discord manque ---
if not exist ".env" (
    echo [ATTENTION] Aucun fichier .env trouve.
    echo Copie ".env.example" en ".env" et renseigne ton webhook/jeton Discord.
    echo.
)

REM --- Boucle 24h/24 : relance le bot s'il s'arrete ---
:loop
echo [%date% %time%] Demarrage du bot... (Ctrl+C pour arreter)
%PY% src\main.py
echo [%date% %time%] Bot arrete (code %errorlevel%). Redemarrage dans 15s...
timeout /t 15 /nobreak >nul
goto loop
