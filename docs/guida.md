# Guida all'uso

[← Torna al README](../README.md)

- [La finestra](#la-finestra)
- [Aprire una foto](#aprire-una-foto)
- [Guardare il risultato](#guardare-il-risultato)
- [Regolare la riduzione del rumore](#regolare-la-riduzione-del-rumore)
- [Reti neurali (IA)](#reti-neurali-ia)
- [Sviluppo dei RAW](#sviluppo-dei-raw)
- [Salvare](#salvare)
- [Elaborare più foto](#elaborare-più-foto)
- [Preset](#preset)
- [Scorciatoie da tastiera](#scorciatoie-da-tastiera)
- [Domande frequenti](#domande-frequenti)

## La finestra

![Finestra principale con una foto aperta al 100%](screenshots/02-confronto.jpg)

- **In alto**: i menu e la barra dei comandi principali. Ogni pulsante mostra la propria scorciatoia
  (es. *Apri file…* `Ctrl+O`). I comandi non disponibili in quel momento sono grigi.
- **Al centro**: la foto. A sinistra della linea c'è l'originale (**PRIMA**), a destra il risultato
  (**DOPO**). L'etichetta in alto indica quanta parte del rumore stimato è stata tolta.
- **Sotto la foto**: una striscia ricorda i comandi della vista. Si nasconde da
  *Visualizza → Mostra i tasti sotto la foto*.
- **A destra**: il pannello delle impostazioni, dall'alto verso il basso nell'ordine in cui servono.
  Passando il mouse su un controllo, la sua spiegazione compare nel riquadro in fondo al pannello.
- **In basso**: informazioni sul file, dispositivo di calcolo (● GPU o ● CPU), tempo dell'ultima
  anteprima, livello di zoom e, durante le operazioni lunghe, avanzamento con il pulsante *Interrompi*.

## Aprire una foto

![Pagina iniziale](screenshots/01-benvenuto.png)

- **Apri file…** (`Ctrl+O`), oppure **trascina** una foto nella finestra.
- Dalla pagina iniziale o da *File → Apri recenti* si riaprono le ultime foto.
- Trascinando **più foto o una cartella** si apre direttamente [Elabora più file](#elaborare-più-foto).
- Formati: RAW di quasi tutte le fotocamere (NEF, CR2, CR3, ARW, RAF, ORF, RW2, PEF, DNG…), JPG, PNG, TIFF.

Il pannello **Foto** riassume il file aperto: dimensioni, fotocamera, ISO e un giudizio sul rumore
misurato (basso, medio, alto, molto alto).

Se una fotocamera è troppo recente per LibRaw (o il file è un NEF «alta efficienza»), con
[Adobe DNG Converter](https://helpx.adobe.com/camera-raw/using/adobe-dng-converter.html) installato
(gratuito) l'app converte il file in DNG e lo apre senza altri passaggi.

## Guardare il risultato

La foto si apre **al 100%** (un pixel della foto = un pixel dello schermo, anche con la scala di Windows
al 125–200%), al centro: è il modo giusto per giudicare il rumore.

| Azione | Come |
|---|---|
| Spostare la foto | Trascina con il mouse, oppure frecce (con `Maiusc` passi più lunghi) |
| Zoom | Rotellina, `Ctrl +` / `Ctrl −`, oppure il menu dello zoom in basso a destra |
| Tutta la foto / 100% / 200% | `Ctrl+0` / `Ctrl+1` / `Ctrl+2` |
| Vedere al 100% un punto preciso | Doppio clic sul punto |
| Spostare la linea prima/dopo | Trascina la maniglia rotonda (doppio clic: torna al centro) |
| Vedere solo l'originale | Tieni premuto `Spazio` |
| Cambiare tipo di confronto | `\` oppure il pulsante *Confronto* (▾ per scegliere) |

Tipi di confronto: **tendina** (prima | dopo), **solo dopo**, **solo prima** e **rumore tolto**.

![Vista «rumore tolto»](screenshots/03-rumore-tolto.jpg)

La vista **rumore tolto** mostra, amplificata quattro volte, la differenza tra originale e risultato.
Se vedi solo una grana uniforme il dettaglio è salvo; se compaiono i contorni degli oggetti la
riduzione è troppo forte: abbassa «Grana» o alza «Recupero dettaglio».

Il risultato si vede a **qualsiasi ingrandimento**. Da vicino (100%, 200%) viene calcolata solo la zona
visibile, in pochi istanti. Con la foto rimpicciolita (*Adatta*, 50%, 25%…) viene elaborata **la foto
intera**, come nel file esportato: un avviso al centro mostra percentuale e tempo rimanente. Così puoi
giudicare l'effetto sull'immagine nel suo insieme, utile soprattutto con i sensori da molti megapixel.
Finito il calcolo, ingrandimenti e spostamenti non richiedono altre attese finché non cambi
un'impostazione. Se durante il calcolo della foto intera ingrandisci un dettaglio, l'app passa alla
sola zona visibile, salvo che il calcolo sia già oltre la metà.

Mentre l'anteprima si aggiorna compare una sottile barra blu in alto. Se hai cambiato un'impostazione
e il calcolo non è ancora finito, il lato «dopo» è velato con l'etichetta *DA AGGIORNARE*.

![Tutta la foto in vista](screenshots/04-adatta.jpg)

## Regolare la riduzione del rumore

<img src="screenshots/08-pannello-completo.png" align="right" width="300" alt="Pannello delle impostazioni">

**Riduzione del rumore**

- **Grana**: rumore di luminosità. **1 = il rumore misurato** (la tacca a metà del cursore);
  meno lascia più grana naturale, più leviga di più.
- **Macchie di colore**: i puntini rossi, verdi e blu tipici delle ombre ad ISO alti. Di solito si
  può tenere un po' più alto della grana.
- **Recupero dettaglio**: riporta una parte di grana fine e nitidezza se il risultato sembra «di plastica».
- **Pixel caldi**: toglie i punti isolati troppo luminosi (lunghe esposizioni, sensore caldo).
  *Decisione* stabilisce quanto deve essere evidente un punto per essere tolto; stelle e luci
  puntiformi vengono riconosciute e conservate.
- **Metodo**: vedi [quale metodo scegliere](../README.md#quale-metodo-scegliere).
- **Quando ridurre (RAW)**: *Prima dello sviluppo* (consigliato) lavora sui dati del sensore;
  *Dopo lo sviluppo* sull'immagine già a colori, ed è utile solo per confronto.
- **Regolazioni avanzate**: parametri propri del metodo. I valori consigliati sono indicati
  tra parentesi; il link *Ripristina* li reimposta.

Doppio clic su un cursore: torna al valore consigliato. *Modifica → Annulla* (`Ctrl+Z`) e
*Ripeti* (`Ctrl+Y`) valgono per tutte le regolazioni.

<br clear="right">

## Reti neurali (IA)

![Pannello di DRUNet con stato del modello e della scheda video](screenshots/05-intelligenza-artificiale.jpg)

DRUNet, SCUNet, Restormer e RawNIND sono reti neurali che girano interamente sul tuo computer.

- La prima volta che le scegli, il pannello (o un avviso cliccabile nell'anteprima) propone di
  **scaricare il modello** dalla pubblicazione ufficiale. Il file viene verificato con un'impronta
  digitale e da quel momento tutto funziona **offline**.
- Lo stato è sempre visibile: *Modello pronto*, *Da scaricare* o avanzamento del download,
  e se viene usata la **scheda video** o il processore.
- Con una scheda video l'elaborazione richiede pochi secondi; con il solo processore anche
  alcuni minuti per foto. L'esportazione si può interrompere con `Esc`.
- **DRUNet** usa il rumore misurato: i cursori funzionano come per gli altri metodi.
  **SCUNet**, **Restormer** e **RawNIND** stimano il rumore da sole: lì «Grana» e «Macchie di
  colore» decidono quanto del loro risultato usare (1 = tutto).
- Quale scegliere: **DRUNet** è il più pulito e la scelta predefinita per i RAW. **RawNIND**, addestrata
  su RAW veri di reflex e mirrorless, conserva più dettaglio e un aspetto più naturale, lasciando un
  filo di grana nelle ombre; è veloce anche senza scheda video. **Restormer** dà un risultato molto
  pulito ma tende ad ammorbidire i dettagli finissimi ed è lenta: senza scheda video può richiedere
  molti minuti per foto.
- Con i RAW Bayer lascia *Quando ridurre* su «Prima dello sviluppo» con qualsiasi metodo: dopo lo
  sviluppo il rumore è «a macchie» (correlato tra pixel vicini) e DRUNet, in particolare, ne toglie
  poco. «Dopo lo sviluppo» serve per i sensori non Bayer (per esempio Fujifilm X-Trans), dove è
  l'unica possibilità. Ogni preset predefinito riporta questa impostazione su «Prima dello sviluppo». **SCUNet** resta indicata per JPG e smartphone.

## Sviluppo dei RAW

Il pannello **Sviluppo RAW** decide come i dati del sensore diventano un'immagine a colori:

- **Bilanciamento del bianco**: *come scattato* (consigliato), automatico, luce diurna oppure personalizzato con i
  moltiplicatori R / G / B (partono da quelli dello scatto).
- **Ricostruzione colori**: algoritmo di demosaicizzazione (AHD consigliato).
- **Luminosità automatica** ed **Esposizione** in EV: valgono per anteprima e file salvati in
  TIFF, PNG o JPEG. Nel DNG l'esposizione viene registrata come impostazione, senza toccare i dati.
- **DNG Converter**: uso automatico di Adobe DNG Converter per i RAW che LibRaw non legge.

Dopo un cambio di bilanciamento o di ricostruzione la foto viene risviluppata: se esporti
subito, il salvataggio parte appena il nuovo sviluppo è pronto.

## Salvare

![Avviso al termine dell'esportazione](screenshots/06-esportazione.jpg)

Nel pannello **Salvataggio** scegli:

- **Formato**: TIFF o PNG (8 o 16 bit), JPEG (qualità 1–100), **DNG** (solo da RAW: un RAW
  ripulito da sviluppare in Lightroom, darktable, Capture One…).
- **Cartella**: un nome semplice (es. `denoised`) crea una sottocartella accanto alla foto;
  un percorso completo salva sempre lì.
- **Nome del file**: con i segnaposto `{nome}`, `{metodo}`, `{iso}`, `{data}` (pulsante `{…}`).
  Sotto compare il percorso esatto del file che verrà creato.
- **Sovrascrivi senza chiedere** (per sicurezza non viene ricordato) e **Copia i metadati**.

Poi **Esporta** (`Ctrl+E`), oppure **Esporta come…** (`Ctrl+Maiusc+E`) per scegliere nome e cartella
sul momento. Al termine, un avviso riassume formato, dimensione, tempo e metodo, con i pulsanti
*Apri cartella*, *Mostra il file* e *Apri la foto*.

Vengono conservati metadati (data, fotocamera, obiettivo, GPS, parole chiave…) e profilo colore.
Le impostazioni usate vengono registrate nella descrizione del file. Il file viene scritto con un nome
temporaneo e rinominato solo alla fine: un'esportazione interrotta non lascia file a metà, e
l'originale non viene mai sovrascritto.

## Elaborare più foto

![Elabora più file](screenshots/07-elabora-piu-file.png)

**File → Elabora più file…** (`Ctrl+B`), oppure trascina più foto o una cartella nella finestra:

1. aggiungi foto o cartelle (anche con le sottocartelle; le cartelle dei risultati precedenti vengono saltate);
2. scegli le impostazioni: quelle attuali della finestra principale oppure un preset;
3. scegli cosa fare se il file di uscita esiste già: altro nome (`_1`, `_2`…), sovrascrivere o saltare;
4. **Avvia**. Durante l'elaborazione vedi l'avanzamento totale e della foto in corso, con il tempo
   stimato; **Interrompi** si ferma senza lasciare file a metà.

Al termine un riepilogo indica le foto elaborate, saltate e con errori, con i pulsanti
*Apri la cartella di uscita* e *Copia l'elenco degli errori*.

## Preset

Il menu **Punto di partenza** (e il menu *Preset*) offre impostazioni pronte:

| Preset | Per |
|---|---|
| Bilanciato | Uso generale (predefinito) |
| Delicato | Rumore leggero, massima naturalezza |
| Forte (ISO alti) | Foto notturne e ISO molto alti |
| Solo colore | Togliere solo le macchie di colore, lasciando la grana |
| Neurale RAW (DRUNet) | Massima qualità sui RAW |
| Neurale JPG (SCUNet) | JPG e foto da smartphone |
| Neurale RAW naturale (RawNIND) | RAW con più dettaglio e aspetto naturale |
| Neurale molto pulito (Restormer) | Risultato molto pulito (meglio con scheda video) |

Quando modifichi un preset il nome diventa «(modificato)». *Salva come preset…* salva le
impostazioni attuali scegliendo quali sezioni includere (riduzione del rumore, sviluppo, luminosità,
salvataggio). Da *Preset* puoi eliminare i tuoi preset o aprirne la cartella.

## Scorciatoie da tastiera

![Guida rapida (F1)](screenshots/09-guida.png)

| Scorciatoia | Azione |
|---|---|
| `Ctrl+O` | Apri |
| `Ctrl+E` / `Ctrl+Maiusc+E` | Esporta / Esporta come |
| `Ctrl+B` | Elabora più file |
| `Ctrl+Z` / `Ctrl+Y` | Annulla / Ripeti |
| `Ctrl+0` / `Ctrl+1` / `Ctrl+2` | Adatta / 100% / 200% |
| `Ctrl +` / `Ctrl −`, rotellina | Zoom |
| Frecce (+ `Maiusc`) | Sposta la vista |
| `Spazio` (tenuto) | Mostra l'originale |
| `\` | Tendina → solo dopo → solo prima → rumore tolto |
| Doppio clic su un cursore | Valore consigliato |
| `Esc` | Interrompe l'operazione in corso |
| `F1` | Guida e scorciatoie |

## Domande frequenti

**Il risultato è troppo liscio, «di plastica».**
Abbassa «Grana» (es. 0,7) o alza «Recupero dettaglio». Controlla con la vista *rumore tolto*.

**Restano macchie di colore nelle ombre.**
Alza «Macchie di colore» (1,3–2): il colore tollera una riduzione più forte della luminosità.

**Le reti neurali sono lente.**
Senza una scheda video compatibile girano sul processore. In basso a destra, ● GPU indica che la scheda
video è in uso. Wavelet e NLM danno ottimi risultati in pochi secondi.

**Un RAW non si apre.**
Installa Adobe DNG Converter (gratuito): l'app lo userà da sola. Per i NEF Nikon conviene scattare
con compressione «senza perdita» invece di «alta efficienza».

**Dove finiscono i file?**
Nella sottocartella `denoised` accanto alla foto originale, salvo diversa scelta in *Salvataggio*.
*File → Apri la cartella di salvataggio* la apre in Esplora risorse.

**Si è verificato un errore imprevisto.**
I dettagli vengono salvati in `%LOCALAPPDATA%\Denoiser\errori.log`.
