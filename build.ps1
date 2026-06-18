# =============================================================================
# build.ps1 — Construit l'application puis (si possible) l'installateur.
#
#   1. PyInstaller  -> dist\TCGStockBot\TCGStockBot.exe (+ dépendances)
#   2. Selftest     -> vérifie que l'exe démarre et charge l'IHM
#   3. Inno Setup   -> Output\TCGStockBot-Setup.exe (si iscc est installé)
#
# Usage :  powershell -ExecutionPolicy Bypass -File build.ps1
# =============================================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/3] PyInstaller…" -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean TCGStockBot.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué." }

$exe = "dist\TCGStockBot\TCGStockBot.exe"
if (-not (Test-Path $exe)) { throw "Exécutable introuvable : $exe" }

Write-Host "[2/3] Selftest de l'exe…" -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
& $exe --selftest
$code = $LASTEXITCODE
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
if ($code -ne 0) { throw "Selftest de l'exe échoué (code $code)." }
Write-Host "    OK." -ForegroundColor Green

Write-Host "[3/3] Installateur Inno Setup…" -ForegroundColor Cyan
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($p in @("C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                     "C:\Program Files\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if ($iscc) {
    & $iscc installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué." }
    Write-Host "Installateur : Output\TCGStockBot-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup (iscc) introuvable — étape ignorée." -ForegroundColor Yellow
    Write-Host "Installe-le depuis https://jrsoftware.org/isdl.php puis relance, " -NoNewline
    Write-Host "ou ouvre installer.iss dans Inno Setup."
}

Write-Host "`nTerminé. L'appli est dans dist\TCGStockBot\." -ForegroundColor Green
