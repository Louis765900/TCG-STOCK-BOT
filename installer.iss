; ============================================================================
; installer.iss — Script Inno Setup pour TCG Stock Bot
;
; Construit un vrai installateur Windows (Setup.exe) à partir du dossier
; dist\TCGStockBot produit par PyInstaller.
;
; Pré-requis : avoir lancé  pyinstaller --noconfirm TCGStockBot.spec
; Compilation : ouvrir ce fichier dans Inno Setup, ou  iscc installer.iss
; Résultat : Output\TCGStockBot-Setup.exe
;
; Installation par utilisateur (PAS besoin des droits administrateur) → idéal
; pour la machine de Tom. L'app peut se lancer au démarrage de Windows.
; ============================================================================

#define MonNom "TCG Stock Bot"
#define MaVersion "1.0.0"
#define MonEditeur "TCG Stock Bot"
#define MonExe "TCGStockBot.exe"

[Setup]
AppId={{B3F1C0A2-9E4D-4A7B-9C2E-7A1F0C3D5E91}
AppName={#MonNom}
AppVersion={#MaVersion}
AppPublisher={#MonEditeur}
DefaultDirName={localappdata}\Programs\TCG Stock Bot
DefaultGroupName={#MonNom}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=TCGStockBot-Setup
SetupIconFile=gui\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MonExe}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "startupicon"; Description: "Lancer automatiquement au démarrage de Windows (recommandé pour une surveillance 24h/24)"; GroupDescription: "Démarrage :"

[Files]
; Tout le dossier produit par PyInstaller.
Source: "dist\TCGStockBot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{group}\Désinstaller {#MonNom}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: desktopicon

[Registry]
; Démarrage automatique (clé Run de l'utilisateur courant) — optionnel via la tâche.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "TCGStockBot"; ValueData: """{app}\{#MonExe}"""; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#MonExe}"; Description: "Lancer {#MonNom} maintenant"; \
    Flags: nowait postinstall skipifsilent
