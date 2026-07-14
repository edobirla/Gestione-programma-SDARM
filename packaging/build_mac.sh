#!/bin/bash
# Build macOS: crea "Gestione programma SDARM.app" e il DMG di installazione.
# Uso:  bash packaging/build_mac.sh
#
# NOTA: l'intera build (PyInstaller, firma, DMG) avviene in una cartella
# temporanea FUORI da iCloud. Il progetto vive sul Desktop (sincronizzato
# con iCloud) e iCloud interferisce in due modi documentati:
#   1. riaggiunge attributi estesi ai file mentre la build gira → codesign
#      fallisce con "resource fork ... detritus not allowed";
#   2. ricrea file dentro dist/ mentre li si cancella → "rm: Directory not
#      empty" e la build muore al primo passo.
# Senza almeno la firma ad-hoc l'app non parte sui Mac Apple Silicon.
set -e
cd "$(dirname "$0")/.."

echo "── Dipendenze ──────────────────────────────────────────"
python3 -m pip install -q -r requirements.txt pyinstaller

echo "── Icona ───────────────────────────────────────────────"
[ -f assets/app_icon.icns ] || python3 packaging/generate_icon.py

echo "── Build (PyInstaller, in cartella temporanea) ─────────"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 -m PyInstaller packaging/ProgrammaServizio.spec --noconfirm \
        --distpath "$TMP/dist" --workpath "$TMP/build"

APP_TMP="$TMP/dist/Gestione programma SDARM.app"
[ -d "$APP_TMP" ] || { echo "ERRORE: .app non creata"; exit 1; }

echo "── Firma ad-hoc ────────────────────────────────────────"
xattr -cr "$APP_TMP" 2>/dev/null || true
find "$APP_TMP" -name "._*" -delete 2>/dev/null || true
codesign -s - --force --deep "$APP_TMP"
codesign -v "$APP_TMP"

echo "── DMG ─────────────────────────────────────────────────"
DMG_TMP="$TMP/Gestione programma SDARM.dmg"
STAGE="$TMP/stage"
mkdir -p "$STAGE"
cp -R "$APP_TMP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Gestione programma SDARM" -srcfolder "$STAGE" \
        -ov -format UDZO "$DMG_TMP" >/dev/null

echo "── Copia risultati in dist/ ────────────────────────────"
mkdir -p dist
rm -rf "dist/Gestione programma SDARM.app" 2>/dev/null || true
rm -f  "dist/Gestione programma SDARM.dmg" 2>/dev/null || true
cp -R "$APP_TMP" "dist/Gestione programma SDARM.app"
cp    "$DMG_TMP" "dist/Gestione programma SDARM.dmg"

echo
echo "Fatto!"
echo "  App:  dist/Gestione programma SDARM.app"
echo "  DMG:  dist/Gestione programma SDARM.dmg   (trascina l'app in Applications per installarla)"
