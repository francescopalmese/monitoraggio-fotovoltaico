# Piano: monitoraggio fotovoltaico ZCS

Legenda: [x] fatto, [ ] da fare, [~] in corso

## Tappa 0: ricognizione (senza codice)
- [x] Identificare inverter, chiavetta e app (16/10/2026)
- [x] Registrare l'impianto su Azzurro Systems (16/10/2026)
- [x] Tabella delle vie di accesso ai dati con fonti (`tappa0_ricognizione.md`)
- [x] Ok dell'utente sulla strada A + B (16/10/2026)
- [~] Ticket a ZCS: mappa Modbus del 3PH HYD ZSS (apre l'utente)
- [~] Ticket a ZCS: token "API Terze Parti Azzurro" (apre l'utente)
- [x] IP della chiavetta (scansione porta 8899, 16/10/2026); macchina per la raccolta: questo PC Windows
- [ ] kWp pannelli e marca batteria (dall'app)

## Tappa 1: raccolta dati
- [x] Ambiente Python `.venv` con `.env` e `.gitignore`, pysolarmanv5 installato con ok dell'utente (16/10/2026)
- [x] Prima lettura di prova riuscita (16/10/2026, `lettura_prova.py`)
- [x] Confronto dei valori con l'app: coincidono (16/10/2026); resta il segno della rete
- [x] Mappa registri `registri.py` con fonte e convenzioni (da confermare con la mappa ufficiale ZCS)
- [x] Script di raccolta su SQLite con data e ora UTC, log con rotazione (`raccolta.py`, 16/10/2026)
- [x] Test automatici con dati finti: 11 test in `tests/` (16/10/2026)
- [x] Esecuzione automatica: attività pianificata "Fotovoltaico raccolta" ogni minuto (16/10/2026, con ok dell'utente)
- [x] Controllo dopo 24 ore (17/10/2026): trovato un buco di 15 ore per cambio di indirizzo della chiavetta (DHCP) e uno notturno per PC spento; database 36 KB per 105 letture
- [x] Scoperta automatica della chiavetta se cambia indirizzo (`scoperta.py`, `raccolta.py --prova-rete`, 17/10/2026)
- [x] Indirizzo fisso alla chiavetta nel router ZTE H2640 (prenotazione DHCP "Chiavetta fotovoltaico", 20/10/2026, con ok dell'utente)
- [x] `LOGGER_IP` nel `.env` aggiornato con l'indirizzo riservato e verificato con `raccolta.py --prova-rete` (20/10/2026 sera)
- [ ] Client per l'API Terze Parti (quando arriva il token): confronto con le letture locali e recupero storico
- [ ] README, screenshot, frase per il CV (max 200 caratteri)

## Tappa 2: dashboard
- [x] Pagina web locale: produzione per giorno e mese, consumo, autoconsumo, scambio con la rete, batteria, potenza delle ultime ore (`dashboard.py`, `dashboard.html`, `calcoli.py`, 16/10/2026, senza librerie nuove)
- [x] Produzione attesa da PVGIS (API v5.3 PVcalc, `pvgis.py`, cache 30 giorni), provata con una posizione pubblica di prova (16/10/2026)
- [x] Parametri nel `.env` inseriti dall'utente (20/10/2026): coordinate, kWp 9,5 stimati (24 pannelli), inclinazione ottimale PVGIS, sud; screenshot rifatto con il confronto vero
- [ ] Leggere la potenza del singolo pannello (etichetta o documenti) per il kWp esatto, e misurare inclinazione e orientamento del tetto per un'attesa più fedele
- [x] Avvisi: inverter che non risponde (10 minuti), guasto inverter, produzione molto sotto l'atteso in giornata di sole; provati con `genera_db_finto.py` (16/10/2026)
- [x] Test con dati finti: 31 nuovi test (calcoli, PVGIS, dashboard e server), 43 in tutto (16/10/2026); 50 con quelli della scoperta (17/10/2026)
- [x] README, screenshot (`screenshot_dashboard.png`, `screenshot_avvisi_dati_finti.png`), frase per il CV in `STATO.md` (16/10/2026)
- [x] Azzeramento a mezzanotte verificato sui dati veri del 17-18/10 (contatore a 0 alle 00:00:06 locali; 20/10/2026)
- [ ] Confrontare con l'app i totali di un giorno intero (produzione, consumo, scambio), per esempio il 19/10
- [x] Meteo e temperatura della posizione nella testata, da Open-Meteo (`meteo.py`, 26/10/2026)
- [ ] Opzionale: avvio automatico della dashboard con l'accesso a Windows (attività pianificata, come la raccolta)
- [x] Pubblicazione su GitHub: repository pubblico con licenza MIT, https://github.com/francescopalmese/monitoraggio-fotovoltaico (22/10/2026)
- [x] Nuova veste grafica: stile cyberpunk neon, tema auto/chiaro/scuro, flusso animato, vista TV, modalità widget (26/10/2026, solo `dashboard.html`)
- [x] Logo del polpo nel cerchio della testata (generato con ComfyUI e inserito il 26/10/2026; originali in `D:\StableDiffusion\Immagini\Logo_polpo\`)
- [x] Commit e push della nuova veste grafica e del meteo (26/10/2026)

## Tappa 3: controllo (solo con conferma esplicita e documentazione ufficiale)
- [ ] Verificare sulla mappa ufficiale quali parametri sono scrivibili (es. modalità di lavoro, carica programmata)
- [ ] Decidere insieme cosa controllare e con quali protezioni
- [ ] README, screenshot, frase per il CV
