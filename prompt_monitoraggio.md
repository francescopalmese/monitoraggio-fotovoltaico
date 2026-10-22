# Prompt: monitoraggio e controllo del mio impianto fotovoltaico

Copia tutto il testo sotto la riga e incollalo come primo messaggio di una nuova sessione Claude Code, dopo aver riempito le parti tra [parentesi quadre]. Le righe che iniziano con "Nota per me" sono promemoria tuoi: cancellale prima di incollare.

---

Voglio costruire un progetto personale di **monitoraggio (e, se possibile, controllo) del mio impianto fotovoltaico**. Serve a due cose: avere dati utili davvero, e diventare una voce credibile nel mio CV per candidature nel settore delle energie rinnovabili. Sono uno studente di Ingegneria Informatica al Politecnico di Torino, so programmare in Python, TypeScript e JavaScript, e ho già lavorato a un progetto con API REST, test automatici e un'app offline.

## Il mio impianto

- Inverter: ZCS Azzurro 3PH HYD10000 ZSS (Zucchetti Centro Sistemi; ibrido trifase, 10 kW nominali, prodotto a ottobre 2021; corrisponde al Sofar Solar HYD 10KTL-3PH, da confermare).
- Potenza dei pannelli: [kWp: non lo so ancora, lo leggo sulla documentazione dell'impianto o lo chiedo all'installatore] · Batteria: sì, al litio ad alta tensione (l'inverter accetta 180-800 V); marca e capacità: [da leggere sull'etichetta della batteria] · Contatore o sensore di consumo: sì, l'app mostra consumo di casa e scambio con la rete (16/10/2026)
- App ufficiale che uso oggi: "Azzurro Systems" di ZCS (portale web www.zcsazzurrosystemsweb.com), con l'impianto registrato a mio nome e la chiavetta associata il 16/10/2026; i dati si aggiornano circa ogni 5 minuti. Esiste anche il vecchio portale www.zcsazzurroportal.com.
- Accesso di rete: chiavetta del produttore inserita nella porta USB dell'inverter, con LED NET, COM e READY (logger Solarman, versione Wi-Fi ZSM-WIFI-USB, nessun cavo di rete); è già collegata alla rete di casa (LED NET acceso, verificato il 16/10/2026), quindi la configurazione iniziale non serve; il PC su cui lavoro è sulla stessa rete di casa; accesso alla pagina del router: [da verificare]
- Account sviluppatore o chiave API del produttore: non ce l'ho. ZCS rilascia il token (Azzurro System), il Client Code (Azzurro Portal) e la mappa Modbus aprendo un ticket su www.zcsazzurro.com.

Nota per me: i seriali dell'inverter e della chiavetta e la password della chiavetta (PWD) sono sulle etichette fisiche; non incollarli in chat, servono solo al momento della configurazione.

### Cose già verificate il 16/10/2026 su fonti ufficiali (da ricontrollare prima di usarle)

- "Communication with ZCS devices" rev. 00 del 03/07/2025 (documentazione su www.zcsazzurro.com): con la chiavetta ZSM-WIFI-USB o ZSM-ETH-USB si parla all'inverter in locale via Modbus TCP sulla porta 8899, libreria Python pysolarmanv5, funzione 0x03 per leggere e 0x10 per scrivere; la mappa dei registri si chiede via ticket. API cloud: Azzurro Portal (solo lettura, Client Code via ticket, massimo 1 giorno per richiesta) e Azzurro System (lettura e scrittura, token via ticket, storico di circa 6 giorni per richiesta). Integrazione Home Assistant citata da ZCS: aturri/ha-zcsazzurro, che usa l'API Azzurro Portal.
- "Guida al monitoraggio dei sistemi Azzurro ZCS (ZSM-WIFI-KIT)" rev. 4.0: la chiavetta si configura collegandosi alla sua rete Wi-Fi AP_<seriale chiavetta> (password PWD dell'etichetta), aprendo 10.10.100.254 con utente e password admin e seguendo il Wizard per scegliere il Wi-Fi di casa; la verifica è "Remote server A: Pingable" nella pagina Status.
- Integrazione Home Assistant "Solarman" (locale, porta 8899): ha profili pronti per gli HYD monofase ZSS e per i KTL-V3; per il 3PH HYD ZSS non ho trovato un profilo pronto, probabilmente serve la mappa registri.

## Regole che devi rispettare

1. **Solo lettura all'inizio.** Nessuna modifica alla configurazione dell'inverter o della batteria finché non lo decido io esplicitamente.
2. **Vie ufficiali o documentate.** Prima le API ufficiali del produttore, poi le interfacce locali standard (Modbus TCP o RTU, SunSpec, HTTP locale documentato). Niente che violi i termini d'uso dell'app o che possa invalidare la garanzia. Se l'unica strada è intercettare il traffico dell'app, fermati e spiegami pro, contro e rischi: decido io.
3. **Non inventare API.** Ogni endpoint, registro Modbus o campo va verificato su documentazione ufficiale o su librerie open source note (per esempio integrazioni di Home Assistant, pymodbus, pvlib). Cita la fonte.
4. **Nessuna credenziale in chat né nel codice.** Chiavi, password e token stanno in un file `.env` escluso da git; se vuoi che li inserisca io, dimmi dove e lo faccio da solo. Non salvare credenziali o indirizzi IP nella tua memoria.
5. **Chiedi prima di installare** programmi o librerie, e spiegami in modo semplice ogni scelta tecnica: voglio capire quello che facciamo, non solo farlo funzionare.
6. Tieni un file `STATO.md` con lo stato del progetto aggiornato a fine sessione e un `PIANO.md` con le milestone, come nel mio progetto di tirocinio.

## Cosa voglio ottenere, a tappe

**Tappa 0, ricognizione (prima di scrivere codice).** Identifica il modello dell'inverter e fammi una tabella delle strade possibili per leggere i dati: API cloud ufficiale del produttore, interfaccia locale (Modbus, SunSpec, HTTP), esportazione CSV dal portale, integrazioni esistenti (Home Assistant, librerie Python). Per ognuna: cosa serve, cosa si ottiene (dati istantanei, giornalieri, storici), latenza, rischi, se è lettura o anche scrittura. Poi consigliami una strada e aspetta il mio ok.

**Tappa 1, raccolta dati.** Uno script Python che legge a intervalli regolari potenza istantanea, energia prodotta nel giorno, e se disponibili consumo, immissione in rete, prelievo e stato della batteria. Salvataggio su SQLite con data e ora, esecuzione automatica (Utilità di pianificazione su Windows o systemd su Linux), log degli errori, test automatici con dati finti.

**Tappa 2, dashboard.** Una pagina web locale con grafici di produzione per giorno e mese, autoconsumo, confronto con la produzione attesa calcolata dai dati pubblici PVGIS per la mia posizione e la mia potenza. Avvisi semplici: inverter che non risponde, produzione molto sotto l'atteso in una giornata di sole.

**Tappa 3, controllo (solo se il produttore lo consente in modo ufficiale).** Per esempio impostare la priorità di carica della batteria o leggere e cambiare modalità di lavoro. Solo con API documentate e dopo che te lo confermo.

**Alla fine di ogni tappa:** README aggiornato, un paio di screenshot, e una frase per il CV di massimo 200 caratteri che descriva cosa fa il progetto in parole semplici.

## Come lavorare con me

Prima di partire fammi le domande che ti servono, poche e mirate. Lavora a piccoli passi verificabili, mostrami i risultati veri (output, grafici, dati letti) e non dirmi che una cosa funziona se non l'hai provata. Se qualcosa non si può fare, dimmelo chiaramente invece di aggirarlo.
