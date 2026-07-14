; Inno Setup script (opzionale) — crea un vero installer Windows.
; Usato automaticamente da build_windows.bat se Inno Setup 6 è installato
; (https://jrsoftware.org/isdl.php). Non è obbligatorio: lo zip prodotto
; dalla build funziona già da solo.

#define AppName "Gestione programma SDARM"
#define AppVersion "1.0.0"

[Setup]
AppId={{8F4E7B12-5C33-4A5D-9E21-3B7C1A9D64E2}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\Installer
OutputBaseFilename=GestioneProgrammaSDARM-Setup
SetupIconFile=..\assets\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul Desktop"; GroupDescription: "Icone aggiuntive:"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Avvia {#AppName}"; Flags: nowait postinstall skipifsilent
