# Denoiser

Riduzione del rumore per foto **RAW** (NEF, CR2/CR3, ARW, RAF, DNG e tutti i formati letti da LibRaw),
**JPG**, **PNG** e **TIFF**. Funziona interamente in locale, senza servizi esterni.

## Come si ottiene l'eseguibile per Windows

Ogni push su GitHub avvia la build automatica (*Actions → Test e build Windows*).
Al termine, nella pagina della build, l'artefatto **Denoiser-windows** contiene uno zip:
estrailo e avvia `Denoiser\Denoiser.exe`. Nella stessa cartella c'è `denoiser-cli.exe`
per l'uso da riga di comando.

## Come funziona

### RAW: denoise sui dati del sensore (livello 3)

Per i sensori Bayer (quasi tutte le fotocamere tranne le Fujifilm X-Trans) il rumore viene
tolto **prima della demosaicizzazione**:

1. il rumore del sensore viene misurato sulla foto stessa (modello Poisson-gaussiano
   `varianza = a·segnale + b`, stimato sui quattro piani del mosaico Bayer): nessun profilo
   per fotocamera, quindi funziona anche con modelli nuovi;
2. la trasformata di Anscombe generalizzata rende il rumore uniforme (deviazione 1);
3. i piani vengono separati in luminanza e colore e ripuliti con forze indipendenti;
4. i dati ripuliti vengono riscritti nel RAW e sviluppati da LibRaw.

Con **forza 1** si toglie esattamente il rumore misurato. Sui test con rumore sintetico il
livello 3 rende circa 1 dB meglio del denoise sull'immagine già sviluppata.

Per gli altri sensori si usa il **livello 2** (denoise dopo lo sviluppo), con il rumore
misurato tramite un "gemello di rumore": un rumore sintetico con le stesse caratteristiche
viene fatto passare per lo stesso sviluppo, così da sapere esattamente come appare dopo la
demosaicizzazione. Il livello 2 si può anche scegliere manualmente.

### JPG/PNG/TIFF

Il rumore viene stimato dalle zone uniformi della foto e rimosso separatamente su luminanza
e colore. Il rumore dei JPG è già stato elaborato dalla fotocamera: spesso serve una forza
un po' più alta di 1.

### Algoritmi

| Algoritmo | Caratteristiche |
|---|---|
| **Wavelet** | Veloce, ottimo sul colore; predefinito |
| **Non-Local Means** | Preserva bene trame e bordi; più lento |
| **Bilaterale** | Molto veloce; a forze alte effetto «acquerello» |
| **DRUNet** (neurale) | Riceve il livello di rumore misurato: in genere la qualità più alta |
| **SCUNet** (neurale) | Addestrata su rumore reale: ottima sui JPG; stima il rumore da sola |

`denoiser-cli algoritmi` elenca tutti i parametri.

Risultati indicativi sui test sintetici (PSNR, più alto è meglio):

| | Rumoroso | Wavelet | DRUNet | SCUNet |
|---|---|---|---|---|
| RAW, livello 3 | 27,9 dB | 31,1 | **32,6** | 30,9 |
| RAW, livello 2 | 27,9 dB | 29,8 | 31,0 | **32,6** |
| JPG | 26,3 dB | 33,3 | **36,2** | 35,7 |

### Modelli neurali (in locale)

I modelli **non sono inclusi** nell'applicazione: alla prima scelta di DRUNet o SCUNet l'app
propone di scaricarli dalle release ufficiali di [KAIR](https://github.com/cszn/KAIR)
(DRUNet 125 MB, licenza MIT; SCUNet 69 MB, licenza Apache 2.0). Il file viene verificato con
un'impronta SHA-256 e convertito in ONNX sul tuo computer; da quel momento tutto funziona offline.

- I file `.pth` vengono letti senza PyTorch e senza eseguire codice contenuto nel file.
- L'elaborazione usa la **GPU** tramite DirectML (qualsiasi scheda video su Windows) e ripiega
  automaticamente sulla CPU se la GPU non è utilizzabile. Senza GPU le reti sono lente
  (minuti per una foto da 24 MP).
- Da riga di comando: `denoiser-cli modelli elenca` e `denoiser-cli modelli scarica`.
- I modelli si trovano in `%LOCALAPPDATA%\Denoiser\modelli` (o in `DENOISER_MODELS_DIR`).

## Interfaccia grafica

Tema scuro, tutto in italiano. Flusso in tre passi: **apri → guarda al 100% → esporta**.

Le scorciatoie sono sempre in vista: ogni pulsante della barra in alto mostra il proprio tasto
(es. *Apri file…* `Ctrl+O`), una striscia sotto la foto ricorda i comandi della vista
(disattivabile da *Visualizza → Mostra i tasti sotto la foto*) e **F1** apre la guida con l'elenco completo.

- **Apri** (Ctrl+O), trascina una foto nella finestra o scegli tra i **file recenti** nella
  pagina iniziale. Trascinando più foto o una cartella si apre *Elabora più file*.
- La foto si apre **al 100% al centro**: il rumore si giudica a pixel reali. La **linea** separa
  *prima* (sinistra) e *dopo* (destra); trascina la maniglia, sposta la foto, rotellina per lo zoom,
  doppio clic per scegliere il punto da controllare.
- **Confronto** (tasto `\`): tendina → solo dopo → solo prima → **rumore tolto** (la differenza
  amplificata ×4: se vedi contorni, la forza è eccessiva). Tieni premuto **Spazio** per vedere l'originale.
- L'anteprima mostra quando è *da aggiornare* o *in calcolo*, e quanta parte del rumore stimato è stata tolta.
- Pannello a destra: **Foto** (giudizio sul rumore misurato), **Punto di partenza** (preset, con
  «(modificato)» quando li cambi; *Salva come preset…* sceglie le sezioni da salvare), **Riduzione del
  rumore** (Grana, Macchie di colore, Recupero dettaglio, pixel caldi, metodo e regolazioni avanzate),
  **Sviluppo RAW**, **Salvataggio** (con l'anteprima del percorso finale). La spiegazione del controllo
  sotto il mouse compare in fondo al pannello; doppio clic su un cursore = valore consigliato.
- I modelli neurali si scaricano dal pannello o facendo clic sull'avviso nell'anteprima, con avanzamento.
- **Esporta** (Ctrl+E) o **Esporta come…** (Ctrl+Maiusc+E). Al termine un avviso offre *Apri cartella*,
  *Mostra il file*, *Apri la foto*. Le operazioni lunghe si interrompono con **Esc** o *Interrompi*:
  nessun file resta scritto a metà.
- **Elabora più file…** (Ctrl+B): file e cartelle (anche sottocartelle), preset, cosa fare se il file
  esiste, avanzamento con tempo stimato, interruzione e riepilogo degli errori.
- **Annulla / Ripeti** (Ctrl+Z / Ctrl+Y) per tutte le regolazioni; *Valori consigliati* ripristina il denoise.
- **Aiuto → Guida rapida** (F1) riassume l'uso e tutte le scorciatoie.

| Scorciatoia | Azione |
|---|---|
| Ctrl+O | Apri |
| Ctrl+E / Ctrl+Maiusc+E | Esporta / Esporta come |
| Ctrl+B | Elabora più file |
| Ctrl+Z / Ctrl+Y | Annulla / Ripeti |
| Ctrl+0 / Ctrl+1 / Ctrl+2 | Adatta / 100% / 200% |
| Ctrl + / Ctrl − | Zoom |
| Frecce (+ Maiusc) | Sposta la vista |
| Spazio (tenuto) | Mostra l'originale |
| `\` | Cambia confronto |
| Esc | Interrompe l'operazione in corso |
| F1 | Guida rapida |

## Formati di uscita e metadati

- **TIFF** (8/16 bit), **PNG** (8/16 bit), **JPEG**.
- **DNG** (solo da RAW), per continuare a lavorare in Lightroom, darktable e simili:
  - al livello 3 contiene i **dati del sensore già ripuliti**: il programma di fotoritocco
    esegue la propria demosaicizzazione e restano liberi bilanciamento del bianco, esposizione
    e profili colore, come con il RAW originale;
  - al livello 2 (o con sensori non Bayer) è un DNG lineare, con il bilanciamento del bianco
    già applicato.
- I **metadati** dell'originale (data, fotocamera, obiettivo, esposizione, GPS, parole chiave…)
  vengono copiati con [ExifTool](https://exiftool.org), incluso nel pacchetto per Windows.
  Le impostazioni di denoise usate vengono registrate nella descrizione del file.

## Riga di comando

```
denoiser-cli elabora FOTO_O_CARTELLE... [opzioni]
denoiser-cli analizza FOTO          # informazioni e rumore stimato
denoiser-cli algoritmi              # algoritmi e parametri
denoiser-cli modelli elenca | scarica [drunet|scunet|tutti]
denoiser-cli preset elenca | salva NOME [opzioni]
```

Esempi:

```
denoiser-cli elabora D:\Foto\Serata --preset "Forte (ISO alti)" --formato tiff
denoiser-cli elabora DSC_0001.NEF --algoritmo nlm --luminanza 0.8 --colore 1.2 --param search_window=15
denoiser-cli elabora D:\Foto --ricorsivo --formato jpeg --qualita 92 --nome "{nome}_{metodo}_{iso}"
denoiser-cli elabora DSC_0001.NEF --algoritmo drunet --formato dng
```

Nel nome del file di uscita si possono usare `{nome}`, `{metodo}`, `{iso}`, `{data}`.
La cartella di uscita predefinita è `denoised` accanto alla foto originale; i file esistenti
non vengono sovrascritti (si aggiunge `_1`, `_2`, …) a meno di `--sovrascrivi`.

## Fotocamere non supportate da LibRaw

Le fotocamere appena uscite (o formati come i NEF Nikon «alta efficienza») possono non essere
ancora supportate da LibRaw. In questo caso, se è installato
[Adobe DNG Converter](https://helpx.adobe.com/camera-raw/using/adobe-dng-converter.html)
(gratuito), l'app converte automaticamente il file in DNG e lo apre. Il percorso si può
indicare nel pannello *Sviluppo RAW* o con `--dng-converter`.

Nota: i NEF «alta efficienza» sono compressi con perdita; per la massima qualità del denoise
conviene scattare con compressione «senza perdita».

## Limiti attuali

- Si assume che JPG/PNG/TIFF siano in sRGB (i profili colore incorporati non vengono convertiti).
- Con la wavelet l'anteprima di una zona può differire leggermente dall'esportazione
  dell'intera foto (la soglia si adatta al contenuto).
- Il DNG lineare (livello 2) ha il bilanciamento del bianco già applicato.
- Le reti neurali sono addestrate su immagini sRGB: sui dati del sensore (livello 3) funzionano
  molto bene nei test sintetici, ma vanno verificate su foto reali.
- Senza ExifTool vengono copiati solo i metadati essenziali dei JPG.

## Sviluppo

```
python -m venv .venv
.venv\Scripts\activate            # Windows (su Linux/macOS: source .venv/bin/activate)
pip install -e ".[gui,dev]"
pytest
denoiser-gui                      # interfaccia
denoiser analizza foto.nef        # riga di comando
pyinstaller packaging/denoiser.spec --noconfirm   # eseguibile (richiede ".[build]")
```

I test usano immagini sintetiche, compresi DNG Bayer generati con rumore noto
(`tests/synthetic.py`), così da misurare oggettivamente il miglioramento (PSNR).
Le reti ricostruite in ONNX vengono confrontate con implementazioni di riferimento numpy;
con `DENOISER_TEST_WEIGHTS=<cartella con i .pth>` si eseguono anche i test con i pesi reali.

## Prossimi passi

- Collaudo e taratura sui NEF reali della Nikon Z5 II e sui JPG reali.
