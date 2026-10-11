# Novità

Tutte le modifiche rilevanti, dalla più recente. Formato ispirato a
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/); numerazione [SemVer](https://semver.org/lang/it/).
Le versioni 0.x sono anteprime: la 1.0 arriverà dopo il collaudo sulle foto reali.

## [Non rilasciato]

## [0.9.0] - 2026-10-11

Prima versione pubblicata: applicazione completa, in attesa del collaudo sui RAW reali.

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

[Non rilasciato]: https://github.com/foyer-labs/Image-Denoiser/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/foyer-labs/Image-Denoiser/releases/tag/v0.9.0
