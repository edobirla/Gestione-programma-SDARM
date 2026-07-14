 # Gestione programma SDARM — creare i pacchetti di installazione

PyInstaller **non può** creare il pacchetto di un sistema operativo da un
altro: la build per Mac si fa su un Mac, quella per Windows su un PC Windows.
Entrambe sono un solo comando.

## macOS (su questo Mac)

```bash
bash packaging/build_mac.sh
```

Risultato in `dist/`:
- `Gestione programma SDARM.app` — l'applicazione
- `Gestione programma SDARM.dmg` — il disco di installazione: si apre e si
  trascina l'app in **Applications**.

> Nota Gatekeeper: l'app non è firmata con un certificato Apple Developer.
> Al primo avvio su un altro Mac: **clic destro sull'app → Apri → Apri**
> (basta una volta sola).

## Windows (su un qualsiasi PC Windows)

1. Copia l'intera cartella del progetto sul PC (chiavetta, cloud…).
2. Installa **Python 3.13** da https://www.python.org/downloads/windows/ —
   in quella pagina cerca la riga "Python 3.13.x" più recente (es. "Python
   3.13.14") e clicca **esattamente** "Download Windows installer
   (**64-bit**)", spuntando **"Add python.exe to PATH"** — serve solo per la
   build, non per usare l'app poi.
   ⚠️ **Non scaricare Python 3.14** (l'ultima versione, in cima alla
   pagina): alcune librerie usate dall'app non hanno ancora un pacchetto
   pronto per Python così recente, e la build fallisce chiedendo un
   compilatore C++ che normalmente non serve installare.
   ⚠️ **Non scaricare Python 3.12**: da qualche tempo non ha più un
   installer per Windows (solo codice sorgente) — Python 3.13 è oggi l'unica
   versione con installer pronto e piena compatibilità con l'app.
   ⚠️ **Non scegliere "Windows installer (ARM64)"**, anche se il PC che
   stai usando ha un processore ARM (Snapdragon/Copilot+): un'app compilata
   con quella versione funziona SOLO su altri PC ARM, non sui normali PC
   Intel/AMD del comitato. La versione 64-bit (x64) invece funziona ovunque
   — anche sui PC ARM, tramite emulazione. Lo script sceglie sempre l'x64 da
   solo (anche se sul PC c'è già un Python ARM64) e ti avvisa chiaramente se
   manca.
3. Doppio clic su `packaging\build_windows.bat`.

Risultato in `dist\`:
- `Gestione programma SDARM\` — la cartella dell'app (si avvia con
  `Gestione programma SDARM.exe`)
- `Gestione programma SDARM-windows.zip` — lo zip da distribuire: si scompatta
  dove si vuole (es. in Documenti) e si crea un collegamento all'exe.
- Se sul PC è installato [Inno Setup 6](https://jrsoftware.org/isdl.php)
  (facoltativo), viene creato anche un vero installer:
  `dist\Installer\GestioneProgrammaSDARM-Setup.exe`.

> Nota SmartScreen: al primo avvio Windows può mostrare "PC protetto da
> Windows" — clic su **Ulteriori informazioni → Esegui comunque**.

## Cosa contiene il pacchetto

Solo l'app e le **5 Bibbie** (it, ro, es, en, pt). Tutto il resto — inni,
basi musicali, suoni, musica di pausa, lezione, template grafici — lo
configura ogni utente dalle Impostazioni (il tutorial al primo avvio guida
i passi principali).

I dati dell'utente (impostazioni, scalette salvate, cronologia, Bibbie
importate) vengono scritti in:
- macOS: `~/Library/Application Support/Gestione programma SDARM/`
- Windows: `%APPDATA%\Gestione programma SDARM\`
