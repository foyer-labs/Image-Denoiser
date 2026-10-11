# Novità

Tutte le modifiche rilevanti, dalla più recente. Formato ispirato a
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/); numerazione [SemVer](https://semver.org/lang/it/).

## [Non rilasciato]

## [0.11.0] - 2026-10-11

### Aggiunto

- **RawNIND (IA)**: rete di Brummer e De Vleeschouwer (UCLouvain, 2025) addestrata su coppie vere
  di RAW rumorosi e puliti di reflex e mirrorless. Lavora direttamente sui dati del sensore,
  conserva molto dettaglio e un aspetto naturale ed è veloce anche senza scheda video. Il risultato
  torna sui fotositi, quindi sviluppo, bilanciamento del bianco e DNG dei dati del sensore restano
  quelli dell'app. Dopo lo sviluppo, per i sensori non Bayer e per i JPG, usa la sua versione su
  RGB lineare. Modello ONNX scaricato al primo uso dalle release di darktable (55 MB, pesi CC BY 4.0).
- **Restormer (IA)**: rete *transformer* di Zamir e altri (CVPR 2022) addestrata su rumore reale.
  Dà un risultato molto pulito ma è lenta e conviene con una scheda video; con i RAW rende meglio
  «Dopo lo sviluppo». Pesi ufficiali (100 MB, MIT) convertiti in ONNX sul computer, senza PyTorch.
- Preset «Neurale RAW naturale (RawNIND)» e «Neurale molto pulito (Restormer)».
- Confronto delle reti con il rumore misurato su una Nikon D5100 nella pagina «Come funziona».

### Corretto

- Le regolazioni avanzate del metodo precedente non restano più visibili per un istante quando si
  cambia metodo.

## [0.10.1] - 2026-10-11

### Corretto

- All'avvio di `Denoiser.exe` non compare più una piccola finestra grigia vuota prima della schermata
  di avvio: ora c'è solo la schermata con la barra di avanzamento.

## [0.10.0] - 2026-10-11

### Aggiunto

- **Risultato a qualsiasi ingrandimento**: con la foto rimpicciolita (*Adatta*, 50%, 25%…) l'app
  elabora la foto intera in background, con percentuale e tempo rimanente. Si vede così l'effetto
  sull'immagine nel suo insieme e non solo su un dettaglio, cosa utile soprattutto con i sensori da
  molti megapixel. Una volta pronto, il risultato vale per ogni ingrandimento e spostamento senza
  altri calcoli. Da vicino resta il calcolo rapido della sola zona visibile.

### Migliorato

- Anteprima più leggera in memoria: resa tonale a strisce e immagini della vista a 8 bit.

## [0.9.3] - 2026-10-11

### Aggiunto

- **Schermata di avvio**: appena si avvia `Denoiser.exe` compare subito una schermata con il nome
  dell'app, poi una barra di avanzamento con percentuale e fase in corso (calcolo numerico,
  algoritmi, reti neurali, scheda video, interfaccia) fino all'apertura della finestra. Non resta
  più il dubbio se il doppio clic abbia funzionato.

## [0.9.2] - 2026-10-11

### Corretto

- L'app poteva chiudersi all'improvviso, senza messaggi, passando più volte tra DRUNet e SCUNet
  con la scheda video (DirectML): ora sulla scheda video resta caricata una sola rete alla volta, e
  DRUNet usa tasselli di misura fissa, così la memoria della scheda non si esaurisce.
- Se l'app dovesse comunque chiudersi per un errore della scheda video o di una libreria, il punto
  in cui è successo viene annotato in `%LOCALAPPDATA%\Denoiser\errori.log`.

## [0.9.1] - 2026-10-11

### Corretto

- Il pannello delle impostazioni poteva risultare tagliato a destra (caselle numeriche e menu
  nascosti), per esempio su Windows con la scala dello schermo al 125–150% o spostando la finestra
  su un altro monitor: ora la colonna si adegua sempre al contenuto, e se serve compare una barra di
  scorrimento orizzontale.
- Nomi di file lunghi nel pannello «Foto» e percorsi lunghi nei file recenti non allargano più la finestra.
- Nome della fotocamera senza la marca ripetuta (es. «NIKON D5100» invece di
  «NIKON CORPORATION NIKON D5100»).
- Nessun messaggio d'errore chiudendo l'app con un'anteprima in corso.

## [0.9.0] - 2026-10-11

Prima versione pubblicata: applicazione completa, in attesa del collaudo sui RAW reali.
Codice distribuito con licenza MIT.

### Elaborazione

- Riduzione del rumore dei **RAW sui dati del sensore** (livello 3, sensori Bayer) e dopo lo sviluppo
  (livello 2, tutti i sensori); JPG, PNG e TIFF a 8/16 bit.
- **Misura del rumore sulla foto stessa** (modello Poisson-gaussiano), senza profili per fotocamera;
  «gemello di rumore» per misurarlo dopo la demosaicizzazione.
- Metodi **Wavelet**, **Non-Local Means**, **Bilaterale** e reti neurali **DRUNet** e **SCUNet**
  eseguite in locale con ONNX Runtime (DirectML sulla scheda video, ripiego sul processore).
  I modelli si scaricano al primo uso dalle pubblicazioni ufficiali e vengono verificati.
- Forze separate per grana e macchie di colore, recupero del dettaglio, rimozione dei pixel caldi
  che conserva stelle e luci puntiformi.
- Bilanciamento del bianco (come scattato, automatico, luce diurna, personalizzato), sette algoritmi
  di demosaicizzazione, luminosità automatica ed esposizione.
- Lettura dei RAW non supportati da LibRaw tramite Adobe DNG Converter.

### Salvataggio

- TIFF e PNG a 8/16 bit, JPEG, **DNG** (dati del sensore ripuliti oppure DNG lineare).
- Copia completa dei metadati con ExifTool (incluso), profilo colore conservato, impostazioni
  registrate nel file, scrittura atomica, originale mai sovrascritto.
- Elaborazione di più foto e cartelle, preset predefiniti e personali, riga di comando completa.

### Interfaccia

- Interfaccia in italiano a tema scuro, con pagina iniziale e file recenti.
- Confronto prima/dopo a tendina al 100%, viste «solo dopo», «solo prima» e «rumore tolto».
  Tieni premuto Spazio per vedere l'originale.
- Scorciatoie sempre visibili sui pulsanti, guida rapida (F1), annulla/ripeti, spiegazione di ogni
  controllo nel pannello.
- Anteprima corretta sui monitor ad alta densità (125–200%) e nella vista ridotta.
- Operazioni lunghe interrompibili con avanzamento e tempo stimato.

### Qualità e robustezza (revisione del codice)

- Niente aloni colorati sui bordi neutri con bilanciamenti del bianco reali.
- Stima del rumore del sensore molto più accurata nelle ombre.
- Anteprima di una zona coincidente con la foto esportata.
- Correzioni di memoria, concorrenza, cache e gestione degli errori; registro degli errori in
  `%LOCALAPPDATA%\Denoiser\errori.log`.

[Non rilasciato]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.9.3...v0.10.0
[0.9.3]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/foyer-labs/Image-Denoiser/releases/tag/v0.9.0
