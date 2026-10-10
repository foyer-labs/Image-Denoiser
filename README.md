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

`denoiser-cli algoritmi` elenca tutti i parametri.

## Interfaccia grafica

- **Apri** (Ctrl+O) o trascina una foto nella finestra.
- La **linea bianca** separa *prima* (a sinistra) e *dopo* (a destra): trascinala.
- **Rotellina** per lo zoom, **trascina** per spostarti, **doppio clic** per passare
  da «adatta alla finestra» a 100%. Il rumore si giudica al 100%: l'anteprima del denoise
  viene calcolata sulla zona visibile quando lo zoom è sufficiente.
- Tutti i parametri sono nel pannello a destra; passa il mouse su un controllo per la spiegazione.
- **Esporta** (Ctrl+E) salva con le impostazioni di *Uscita*; **Elabora più file…** (Ctrl+B)
  applica le impostazioni correnti a più foto.
- **Preset**: quelli predefiniti cambiano solo il denoise; *Salva preset…* salva tutto.

## Riga di comando

```
denoiser-cli elabora FOTO_O_CARTELLE... [opzioni]
denoiser-cli analizza FOTO          # informazioni e rumore stimato
denoiser-cli algoritmi              # algoritmi e parametri
denoiser-cli preset elenca | salva NOME [opzioni]
```

Esempi:

```
denoiser-cli elabora D:\Foto\Serata --preset "Forte (ISO alti)" --formato tiff
denoiser-cli elabora DSC_0001.NEF --algoritmo nlm --luminanza 0.8 --colore 1.2 --param search_window=15
denoiser-cli elabora D:\Foto --ricorsivo --formato jpeg --qualita 92 --nome "{nome}_{metodo}_{iso}"
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

- Uscita in TIFF, PNG e JPEG; l'uscita **DNG** arriverà in una fase successiva.
- I metadati EXIF vengono copiati solo da JPG a JPG; la copia completa (anche dai RAW) con
  ExifTool arriverà in una fase successiva. Le impostazioni usate vengono comunque registrate
  nella descrizione del file.
- Si assume che JPG/PNG/TIFF siano in sRGB (i profili colore incorporati non vengono convertiti).
- Con la wavelet l'anteprima di una zona può differire leggermente dall'esportazione
  dell'intera foto (la soglia si adatta al contenuto).

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

## Prossime fasi

1. Motore neurale locale (ONNX Runtime con DirectML/CUDA): DRUNet, poi SCUNet/NAFNet.
2. Uscita DNG.
3. Copia completa dei metadati con ExifTool.
4. Taratura sui NEF reali della Nikon Z5 II.
