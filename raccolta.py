"""
Raccolta dei dati dell'inverter su SQLite, in SOLA LETTURA.

Tre modi d'uso:
  python raccolta.py --una-volta        una lettura e basta (per l'Utilità di
                                        pianificazione di Windows, ogni minuto)
  python raccolta.py --intervallo 60    ciclo continuo, una lettura ogni 60 s
  python raccolta.py --prova-rete       dice se la chiavetta risponde all'indirizzo
                                        configurato e alla scoperta automatica
                                        (senza stampare indirizzi)

Configurazione nel file .env (accanto a questo script):
  LOGGER_IP, LOGGER_SERIAL, MODBUS_SLAVE_ID   come per lettura_prova.py
  RACCOLTA_DB         percorso del database (default: dati.db qui accanto)
  RACCOLTA_INTERVALLO secondi tra le letture nel ciclo continuo (default 60)

Se la chiavetta non risponde all'indirizzo configurato (il router può cambiarglielo:
è successo il 16/10/2026 sera e la raccolta è rimasta ferma 15 ore), lo script la
cerca con la scoperta automatica (scoperta.py), controlla che il seriale sia quello
giusto e salva l'indirizzo trovato nel file locale .chiavetta_ip (escluso da git),
che viene provato per primo nelle letture successive. La soluzione definitiva è
riservare un indirizzo fisso alla chiavetta nel router.

Errori e letture vengono scritti in logs/raccolta.log (ruotato a 1 MB) e a schermo.
"""
import argparse
import logging
import logging.handlers
import os
import pathlib
import socket
import sys
import time

from dotenv import load_dotenv

import archivio
import lettore
import scoperta

CARTELLA = pathlib.Path(__file__).resolve().parent
CACHE_IP = CARTELLA / ".chiavetta_ip"


def configura_log():
    cartella_log = CARTELLA / "logs"
    cartella_log.mkdir(exist_ok=True)
    su_file = logging.handlers.RotatingFileHandler(
        cartella_log / "raccolta.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handlers = [su_file]
    if sys.stdout is not None:          # con pythonw.exe non c'è console: solo file
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)


def una_lettura(con, ip, seriale, slave_id):
    """Apre la connessione, legge tutto, salva, chiude. Solleva eccezioni al chiamante."""
    client = lettore.crea_client_reale(ip, seriale, slave_id)
    lettore_ = lettore.LettoreInverter(client)
    try:
        valori = lettore_.leggi_tutto()
    finally:
        try:
            client.disconnect()
        except Exception:      # la chiusura non deve mai nascondere l'errore vero
            pass
    ts = archivio.salva(con, valori)
    if lettore_.errori_recuperati:
        logging.warning("%s risposte sbagliate dalla chiavetta, recuperate con un nuovo tentativo",
                        lettore_.errori_recuperati)
    logging.info("lettura %s: stato %s, PV %s W, carico %s W, rete %s W, batteria %s W, SOC %s%%, oggi %s kWh",
                 ts, valori.get("stato_inverter"), valori.get("pv_potenza_totale"),
                 valori.get("potenza_carico"), valori.get("potenza_rete"),
                 valori.get("batteria_potenza"), valori.get("batteria_soc"),
                 valori.get("energia_prodotta_oggi"))
    return valori


# ---------- indirizzo della chiavetta: configurato, in cache, o scoperto ----------

def leggi_cache_ip(percorso=None):
    try:
        return (percorso or CACHE_IP).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def scrivi_cache_ip(ip, percorso=None):
    try:
        (percorso or CACHE_IP).write_text(ip + "\n", encoding="utf-8")
    except OSError as errore:
        logging.warning("non riesco a salvare l'indirizzo trovato: %s", errore)


def indirizzi_da_provare(ip_cfg, cache=None):
    """Prima l'indirizzo trovato l'ultima volta (se diverso), poi quello del .env."""
    cache = cache if cache is not None else leggi_cache_ip()
    return [cache, ip_cfg] if cache and cache != ip_cfg else [ip_cfg]


def lettura_con_scoperta(con, ip_cfg, seriale, slave_id, leggi=None, trova=None):
    """Prova gli indirizzi noti; se nessuno risponde cerca la chiavetta in rete con
    il suo seriale, legge dal nuovo indirizzo e lo salva per le prossime volte.
    `leggi` e `trova` si sostituiscono nei test con funzioni finte."""
    leggi = leggi or una_lettura
    trova = trova or scoperta.trova
    candidati = indirizzi_da_provare(ip_cfg)
    ultimo_errore = None
    for ip in candidati:
        try:
            return leggi(con, ip, seriale, slave_id)
        except Exception as errore:          # noqa: BLE001 - si passa al prossimo indirizzo
            ultimo_errore = errore
    nuovo = trova(seriale, ip_indizio=ip_cfg)
    if nuovo and nuovo not in candidati:
        logging.warning("chiavetta non raggiungibile agli indirizzi noti (%s); trovata con la "
                        "scoperta automatica a un indirizzo nuovo, salvato in %s",
                        ultimo_errore, CACHE_IP.name)
        valori = leggi(con, nuovo, seriale, slave_id)
        scrivi_cache_ip(nuovo)
        return valori
    if nuovo:
        motivo = ("la scoperta automatica la trova allo stesso indirizzo: è in rete ma non "
                  "risponde sulla porta 8899 (occupata o chiavetta da riavviare?)")
    else:
        motivo = ("non trovata nemmeno con la scoperta automatica: controllare il LED NET "
                  "della chiavetta e la rete di casa")
    raise RuntimeError(f"chiavetta non raggiungibile ({ultimo_errore}); {motivo}")


def porta_aperta(ip, porta=8899, attesa=3.0):
    s = socket.socket()
    s.settimeout(attesa)
    try:
        s.connect((ip, porta))
        return True
    except OSError:
        return False
    finally:
        s.close()


def prova_rete(ip, seriale):
    """Diagnosi senza stampare indirizzi."""
    cache = leggi_cache_ip()
    print("indirizzo nel .env:", "risponde sulla porta 8899" if porta_aperta(ip) else "NON risponde")
    if cache and cache != ip:
        print("indirizzo in cache (.chiavetta_ip):",
              "risponde sulla porta 8899" if porta_aperta(cache) else "NON risponde")
    nuovo = scoperta.trova(seriale, ip_indizio=ip)
    if not nuovo:
        print("scoperta automatica: nessuna chiavetta con questo seriale ha risposto")
    elif nuovo == ip:
        print("scoperta automatica: trovata, stesso indirizzo del .env")
    else:
        print("scoperta automatica: trovata a un indirizzo DIVERSO dal .env "
              "(la raccolta lo usa da sola; per sistemare davvero, riservare l'IP nel router)")
    return 0


def main(argv=None):
    load_dotenv(CARTELLA / ".env")
    parser = argparse.ArgumentParser(description="Raccolta dati inverter su SQLite (sola lettura).")
    parser.add_argument("--una-volta", action="store_true", help="una sola lettura, poi esce")
    parser.add_argument("--prova-rete", action="store_true",
                        help="controlla se la chiavetta risponde (indirizzo configurato e scoperta automatica)")
    parser.add_argument("--intervallo", type=int,
                        default=int(os.getenv("RACCOLTA_INTERVALLO", "60")),
                        help="secondi tra le letture nel ciclo continuo")
    parser.add_argument("--db", default=os.getenv("RACCOLTA_DB", str(CARTELLA / "dati.db")),
                        help="percorso del database SQLite")
    args = parser.parse_args(argv)

    configura_log()
    ip = os.getenv("LOGGER_IP", "").strip()
    seriale = os.getenv("LOGGER_SERIAL", "").strip()
    slave_id = int(os.getenv("MODBUS_SLAVE_ID", "1"))
    if not ip or not seriale.isdigit():
        logging.error("LOGGER_IP o LOGGER_SERIAL mancanti nel file .env")
        return 2
    if args.prova_rete:
        return prova_rete(ip, seriale)

    con = archivio.apri(args.db)
    if args.una_volta:
        try:
            lettura_con_scoperta(con, ip, seriale, slave_id)
            return 0
        except Exception as errore:
            logging.error("lettura fallita: %s", errore)
            return 1

    logging.info("ciclo continuo ogni %s s, database %s (Ctrl+C per fermare)", args.intervallo, args.db)
    while True:
        inizio = time.time()
        try:
            lettura_con_scoperta(con, ip, seriale, slave_id)
        except Exception as errore:
            logging.error("lettura fallita: %s", errore)
        attesa = args.intervallo - (time.time() - inizio)
        if attesa > 0:
            time.sleep(attesa)


if __name__ == "__main__":
    sys.exit(main())
