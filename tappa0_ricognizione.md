# Tappa 0: ricognizione delle vie di accesso ai dati

Data: 16/10/2026 · Impianto: ZCS Azzurro 3PH HYD10000 ZSS (ibrido trifase 10 kW, batteria al litio ad alta tensione), chiavetta Wi-Fi del produttore (logger Solarman) già in rete, contatore di consumo presente (l'app mostra consumo e scambio con la rete), PC sulla stessa rete di casa.

Nessun codice scritto in questa tappa. Tutto quello che segue è verificato sulle fonti in fondo; dove una cosa non è verificata è scritto "da verificare".

## Tabella delle strade

| Via | Cosa serve | Cosa si ottiene | Latenza | Lettura / scrittura | Rischi e limiti | Fonte |
|---|---|---|---|---|---|---|
| **A. Locale: Modbus TCP attraverso la chiavetta** (protocollo Solarman V5, porta 8899) con la libreria Python `pysolarmanv5` | Indirizzo IP della chiavetta sulla rete di casa; seriale della chiavetta (è nel file `seriale_inverter.txt`); PC sulla stessa rete; libreria `pysolarmanv5` (licenza MIT, da installare con pip previo ok); mappa dei registri: subito quella comunitaria del profilo Sofar G3, in parallelo quella ufficiale via ticket a ZCS | Tutte le grandezze istantanee: potenza fotovoltaica totale e per stringa, potenza di rete, potenza del carico, potenza/SOC/SOH/tensione/temperatura batteria, energie del giorno (prodotta, consumata, importata, esportata, caricata, scaricata) e totali, stato inverter, codici di guasto, temperature interne | Secondi; il profilo Home Assistant legge ogni 5 s potenze e batteria, ogni 30 s le energie | **Entrambe**: funzione 0x03 per leggere, 0x10 per scrivere (dichiarato da ZCS). In questo progetto si usa solo la lettura fino alla Tappa 3 | Sulla rete locale non c'è autenticazione oltre al seriale: la rete di casa deve restare privata. Una scrittura sbagliata cambia le impostazioni dell'inverter: nel codice non si usano le funzioni di scrittura. Un polling troppo fitto potrebbe disturbare l'invio al cloud della chiavetta (da verificare in pratica; partire da 30-60 s). Serve un PC acceso per la raccolta continua. La mappa comunitaria è scritta per i Sofar G3 e dichiara di funzionare con gli Azzurro trifase rimarchiati: va confermata con quella ufficiale | [1] §3, [4], [5], [6] |
| **B. Cloud: "API Terze Parti Azzurro"** (Azzurro System, portale nuovo) | Token rilasciato da ZCS (nel documento la richiesta dal portale è "in sviluppo"; la guida del luglio 2025 dice di aprire un ticket); email dell'account come `x-api-key`, token come `x-api-secret`; seriale dell'inverter come `thingKey` | Comando `realtimeData` (ultima telemetria) e `historicData` (campioni ogni 5 minuti, finestre di massimo 24 ore), allarmi storici e in tempo reale con codici normalizzati. Telemetrie: potenze generata, consumata, importata, esportata, in carica e in scarica; energie del giorno e totali; SOC e tensione batteria; frequenza di rete; tensioni e correnti DC nello storico | 5 minuti | Lettura. "Invio comandi Modbus" è in preparazione e richiede un impianto avanzato e antenna Wi-Fi con firmware minimo 1.07C | Dipende dal cloud ZCS e dal fatto che inverter e PC siano online; limiti di frequenza non documentati; tempi di risposta del ticket; mapping di alcune telemetrie incompleto ("not mapped yet" negli esempi) | [2], [1] §6.2 |
| **C. Cloud: API Azzurro Portal** (portale vecchio) | Codice cliente (`client`) assegnato da ZCS via ticket; header `Authorization` con un valore fisso riportato nel documento; endpoint `third.zcsazzurroportal.com` porta 19003 | Stessi comandi di B (`historicData`, `realtimeData`, allarmi) più i sensori ambientali; finestre di massimo 24 ore; stesse telemetrie più `powerAutoconsuming` | 5 minuti | Solo lettura | È il portale vecchio: probabile dismissione. L'integrazione Home Assistant che lo usa (ha-zcsazzurro) non è più mantenuta dall'autore | [3], [1] §6.1, [7] |
| **D. Esportazione manuale dal portale web** | Account Azzurro Systems (già fatto) | Grafici e, se la funzione esiste, esportazione CSV | Manuale, giornaliera | Lettura | Non automatizzabile; funzione di esportazione da verificare sul portale | da verificare |
| **E. Integrazioni pronte** (Home Assistant: ha-solarman in locale, ha-zcsazzurro via cloud) | Un'istanza Home Assistant sempre accesa | Dashboard e storico già fatti | Secondi (ha-solarman) o minuti (ha-zcsazzurro) | ha-solarman espone anche parametri scrivibili | Non è il tuo progetto: serve come riferimento per la mappa dei registri, gli intervalli di lettura e come confronto dei valori | [5], [6], [7] |
| **F. Modbus RTU su RS485 con cavo** | Adattatore USB-RS485, cablaggio alla porta di comunicazione dell'inverter, mappa ufficiale | Come A | Secondi | Entrambe | Richiede di aprire o cablare l'inverter (garanzia, sicurezza elettrica) e non serve: la chiavetta fa già da ponte. Non approfondita | non verificata |

## Raccomandazione

**Strada A (lettura locale via chiavetta) come via principale, strada B (API Terze Parti) come via di controllo e di storico.**

Perché A:
- è la via indicata da ZCS stessa per comunicare con l'inverter in locale, con esempi in Python e la libreria `pysolarmanv5` citata nel loro documento;
- non aspetta nessun ticket per partire: la mappa comunitaria basta per leggere potenze, energie e batteria già nella Tappa 1, e si confronta con i numeri dell'app;
- dà dati ogni pochi secondi e funziona anche se il cloud ZCS è lento o giù;
- è la base anche per la Tappa 3 (controllo), perché la scrittura passa dagli stessi registri.

Perché anche B:
- serve a validare le letture locali (stesso dato dal cloud) e a recuperare lo storico passato un giorno alla volta;
- è il ripiego quando il PC che raccoglie i dati è spento;
- richiede solo un ticket: conviene aprirlo subito, mentre si lavora su A.

Strada C si scarta (portale vecchio), D si tiene come verifica manuale, E come riferimento, F non serve.

Vincoli da rispettare nella Tappa 1: solo funzioni di lettura (0x03/0x04), intervallo iniziale di 30-60 secondi, nessuna credenziale nel codice (IP, seriali e token in `.env` fuori da git), test con dati finti.

## Cose da fare adesso (tue)

1. Dare l'ok alla strada, o chiedere cambiamenti.
2. Aprire due ticket su www.zcsazzurro.com (sezione supporto), citando il modello 3PH HYD10000 ZSS e il seriale dell'inverter:
   - richiesta della **mappa dei registri Modbus** dell'inverter;
   - richiesta del **token per le "API Terze Parti Azzurro"** associato all'email del tuo account Azzurro Systems.
3. Trovare l'**indirizzo IP della chiavetta** nell'elenco dei dispositivi del router di casa (ZCS mostra proprio questo metodo nel suo documento) e annotarlo nel file `.env` quando lo creeremo, non in chat.
4. Leggere nell'app i **kWp dei pannelli** e la **marca della batteria**.
5. Decidere **quale macchina resta accesa** per la raccolta continua (questo PC Windows, o un Raspberry/NAS).

## Fonti

1. ZCS, "Communication with ZCS devices", rev. 00 del 03/07/2025: https://www.zcsazzurro.com/uploads/documetazione/Communication-with-ZCS-devices_rev1.pdf (§3 chiavetta Wi-Fi: Modbus TCP su porta 8899, pysolarmanv5, 0x03 lettura e 0x10 scrittura, mappa via ticket; §6 API).
2. ZCS, "Manuale Utente: API Terze Parti Azzurro", versione 2025-05-30 (PDF linkato dal documento 1, portale https://zcsazzurrosystemsweb.com): endpoint, header `x-api-key`/`x-api-secret`, comandi realtimeData/historicData/deviceAlarm/deviceHistoricAlarm, campioni ogni 5 minuti, finestre di 24 ore, comandi Modbus in preparazione.
3. ZCS, "Dettaglio nuove API" (Azzurro Portal, PDF linkato dal documento 1): endpoint third.zcsazzurroportal.com:19003, codice cliente da ZCS, finestre di 24 ore.
4. Documentazione pysolarmanv5: https://pysolarmanv5.readthedocs.io/ (porta 8899, costruttore con IP e seriale del datalogger, funzioni read_holding_registers / read_input_registers, licenza MIT).
5. Integrazione Home Assistant ha-solarman (davidrapan), basata su pysolarmanv5: https://github.com/davidrapan/ha-solarman
6. Profilo `sofar_g3hyd.yaml` di ha-solarman, con la nota "Also works w/ rebranded ZCS Azzurro 3-Phase inverters such as the 3PH HYD6000 ZSS" e gli indirizzi dei registri (potenza PV 0x05C4, rete 0x0488, carico 0x04AF, batteria 0x0606-0x0609, energie giornaliere 0x0684-0x0699, stato 0x0404): https://raw.githubusercontent.com/davidrapan/ha-solarman/main/custom_components/solarman/inverter_definitions/sofar_g3hyd.yaml
7. Integrazione Home Assistant ha-zcsazzurro (aturri), usa l'API Azzurro Portal con `client_code` e `auth_key`, non più mantenuta: https://github.com/aturri/ha-zcsazzurro
8. ZCS, "Guida al monitoraggio dei sistemi Azzurro ZCS (ZSM-WIFI-KIT)", rev. 4.0: https://www.zcsazzurro.com/uploads/documetazione/Manuale-utente-sistemi-di-monitoraggio-wifi-ZSM-WIFI-KIT.pdf (compatibilità HYD 3PH 5000-20000 ZSS con ZSM-WIFI-USB).
9. PVGIS, API non interattiva v5.3 (per la Tappa 2): https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/api-non-interactive-service_en (strumenti PVcalc e seriescalc, parametri lat, lon, peakpower, loss, angle, aspect; limite 30 richieste al secondo per IP).
