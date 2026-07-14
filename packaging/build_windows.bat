@echo off
REM ============================================================
REM  Gestione programma SDARM — build per Windows (un solo doppio clic)
REM
REM  Prerequisito UNICO: Python 3.13, versione **Windows installer (64-bit)**,
REM  da python.org (durante l'installazione spunta "Add python.exe to PATH").
REM
REM  NON scaricare Python 3.14 (l'ultima versione in home page): alcune
REM  librerie usate dall'app non hanno ancora un pacchetto pronto per
REM  versioni cosi' nuove.
REM  NON scaricare Python 3.12: da tempo non ha piu' un installer Windows
REM  (solo codice sorgente).
REM  NON scegliere la versione "ARM64", anche se questo PC ha un processore
REM  ARM (Snapdragon/Copilot+): un'app compilata con quella gira SOLO su
REM  altri PC ARM. La versione 64-bit (x64) invece gira ovunque — sia sui
REM  normali PC Intel/AMD sia (tramite emulazione) sui PC ARM. Questo script
REM  sceglie sempre l'x64 da solo, anche se sul PC c'e' gia' un Python ARM64.
REM
REM  Risultato:
REM    dist\Gestione programma SDARM\            la cartella dell'app
REM    dist\Gestione programma SDARM-windows.zip lo zip da distribuire
REM    dist\Installer\GestioneProgrammaSDARM-Setup.exe  (solo se Inno Setup
REM                                                 e' installato, opzionale)
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ── Controllo versione e architettura di Python ─────────
set "PY_PATH="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0find_python.ps1"`) do set "PY_PATH=%%P"

if not defined PY_PATH (
    echo.
    echo ============================================================
    echo  Serve Python 3.13 in versione a 64 bit ^(x64^).
    echo.
    echo  Scaricalo da:
    echo    https://www.python.org/downloads/windows/
    echo  In quella pagina cerca la riga "Python 3.13.x" piu' recente
    echo  ^(es. "Python 3.13.14"^) e clicca esattamente:
    echo    "Download Windows installer (64-bit)"
    echo.
    echo  NON scaricare Python 3.14 ^(non ancora compatibile con alcune
    echo  librerie dell'app^) ne' Python 3.12 ^(non ha piu' un installer^).
    echo  NON scegliere "Windows installer (ARM64)", anche se questo PC
    echo  ha un processore ARM: serve la versione x64 per essere sicuri
    echo  che l'app funzioni anche sugli altri PC del comitato.
    echo.
    echo  Durante l'installazione spunta "Add python.exe to PATH".
    echo  Poi rilancia questo file: build_windows.bat
    echo ============================================================
    echo.
    pause
    exit /b 1
)
set "PY="%PY_PATH%""
for /f "tokens=*" %%I in ('%PY% --version') do echo Uso: %%I  ^(%PY_PATH%^)

echo ── Dipendenze ──────────────────────────────────────────
%PY% -m pip install --quiet --upgrade pip
%PY% -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 ( echo ERRORE installazione dipendenze & pause & exit /b 1 )

echo ── Build (PyInstaller) ─────────────────────────────────
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PY% -m PyInstaller packaging\ProgrammaServizio.spec --noconfirm --distpath dist --workpath build
if errorlevel 1 ( echo ERRORE build & pause & exit /b 1 )

if not exist "dist\Gestione programma SDARM\Gestione programma SDARM.exe" (
    echo ERRORE: eseguibile non creato
    pause
    exit /b 1
)

echo ── Zip di distribuzione ────────────────────────────────
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Gestione programma SDARM' -DestinationPath 'dist\Gestione programma SDARM-windows.zip' -Force"

echo ── Installer (opzionale, se Inno Setup e' presente) ────
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
    "%ISCC%" /Qp packaging\installer.iss
    echo Creato anche: dist\Installer\GestioneProgrammaSDARM-Setup.exe
) else (
    echo Inno Setup non trovato: salto l'installer .exe ^(lo zip basta:
    echo si scompatta dove si vuole e si avvia "Gestione programma SDARM.exe"^).
)

echo.
echo ============================================================
echo  Fatto!
echo    dist\Gestione programma SDARM\             cartella dell'app
echo    dist\Gestione programma SDARM-windows.zip  zip da distribuire
echo ============================================================
pause
