"""
Dashboard web locale del fotovoltaico, in SOLA LETTURA.

Avvio:    python dashboard.py          poi aprire http://127.0.0.1:8765 nel browser
Opzioni:  --porta 8765   --db percorso/dati.db   --no-pvgis (non contattare PVGIS)

Scelte tecniche (spiegate anche nel README):
- server HTTP della libreria standard di Python (http.server): niente da
  installare; ascolta SOLO su 127.0.0.1, quindi la pagina si vede solo da questo PC;
- il database si apre in sola lettura (URI "mode=ro"): la dashboard non può
  scrivere in dati.db e non parla mai con l'inverter: legge solo il database
  che raccolta.py riempie;
- la pagina dashboard.html (file accanto a questo) disegna i grafici con Chart.js
  caricato da CDN: per vedere i grafici serve internet, ma i dati non escono dal PC;
- la produzione attesa viene da PVGIS (pvgis.py), con cache su file
  pvgis_cache.json rinnovata ogni 30 giorni (è l'unico file che la dashboard scrive).

Configurazione nel file .env (vedi .env.example): IMPIANTO_KWP, PVGIS_LAT,
PVGIS_LON, PVGIS_INCLINAZIONE, PVGIS_ORIENTAMENTO, PVGIS_PERDITE, DASHBOARD_PORTA.

Risposte del server:
  GET /                              la pagina
  GET /api/dati?ore=12&giorni=31     tutto quello che la pagina mostra, in JSON
"""
import argparse
import datetime
import http.server
import json
import logging
import os
import pathlib
import sqlite3
import sys
import urllib.parse

from dotenv import load_dotenv

import calcoli
import pvgis

CARTELLA = pathlib.Path(__file__).resolve().parent
PAGINA = CARTELLA / "dashboard.html"
CACHE_PVGIS = CARTELLA / "pvgis_cache.json"
PORTA_DEFAULT = 8780
MAX_ORE, MAX_GIORNI = 72, 92


# ---------- database (solo lettura) ----------

def apri_sola_lettura(percorso):
    """Connessione SQLite in sola lettura (URI mode=ro): ogni scrittura fallirebbe."""
    uri = pathlib.Path(percorso).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def righe_da(con, da_ts):
    return [dict(r) for r in con.execute("SELECT * FROM letture WHERE ts >= ? ORDER BY ts", (da_ts,))]


def ultima_lettura(con):
    r = con.execute("SELECT * FROM letture ORDER BY ts DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def ultime_letture_per_giorno(con):
    """L'ultima lettura di ogni giorno locale su tutto lo storico: basta per i totali
    mensili (i contatori "oggi" valgono per tutto il giorno) senza caricare ogni riga.
    Il giorno locale qui è quello del sistema (SQLite 'localtime'), come il default
    di calcoli.in_locale."""
    sql = ("SELECT l.* FROM letture l JOIN (SELECT max(ts) AS ts FROM letture "
           "GROUP BY date(ts, 'localtime')) u ON l.ts = u.ts ORDER BY l.ts")
    return [dict(r) for r in con.execute(sql)]


# ---------- dati per la pagina ----------

def costruisci_dati(con, kwp=None, ore=12, giorni=31, adesso=None, tz=None, mensili=None, info_pvgis=None):
    """Tutto quello che la pagina mostra, come dizionario pronto per il JSON."""
    adesso = adesso or datetime.datetime.now(calcoli.UTC)
    adesso_loc = adesso.astimezone(tz)
    oggi = adesso_loc.date()
    inizio = (adesso_loc - datetime.timedelta(days=giorni - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    righe = righe_da(con, inizio.astimezone(calcoli.UTC).isoformat(timespec="seconds"))
    da_ore = (adesso - datetime.timedelta(hours=ore)).astimezone(calcoli.UTC).isoformat(timespec="seconds")
    righe_ore = [r for r in righe if r["ts"] >= da_ore]
    ultima = ultima_lettura(con)

    lista_giorni = calcoli.aggrega_giorni(righe, tz)
    for g in lista_giorni:
        g["attesa"] = calcoli.attesa_giorno(mensili, g["data"])
    lista_mesi = calcoli.aggrega_mesi(calcoli.aggrega_giorni(ultime_letture_per_giorno(con), tz))
    for m in lista_mesi:
        # attesa per i soli giorni che hanno dati: un mese iniziato a metà (o in corso)
        # si confronta con quello che PVGIS si aspetta in quei giorni, non nel mese intero
        m["attesa"] = calcoli.attesa_mese(mensili, m["mese"], m["giorni_con_dati"])
    giorno_oggi = next((g for g in lista_giorni if g["data"] == oggi.isoformat()), None)
    stato = None
    if ultima and ultima.get("stato_inverter") is not None:
        stato = int(ultima["stato_inverter"])
    lista_avvisi = calcoli.avvisi(ultima["ts"] if ultima else None, adesso, lista_giorni,
                                  mensili, kwp, stato, tz)

    info_ultima = None
    if ultima:
        info_ultima = {
            "ts": ultima["ts"],
            "ora_locale": calcoli.in_locale(ultima["ts"], tz).strftime("%d/%m/%Y %H:%M"),
            "minuti_fa": int((adesso - calcoli.in_locale(ultima["ts"], calcoli.UTC)).total_seconds() // 60),
            "stato_inverter": stato,
            "stato_testo": calcoli.STATI_INVERTER.get(stato, "sconosciuto"),
            "pv_w": ultima.get("pv_potenza_totale"),
            "carico_w": ultima.get("potenza_carico"),
            "rete_w": ultima.get("potenza_rete"),
            "batteria_w": ultima.get("batteria_potenza"),
            "frequenza_hz": ultima.get("frequenza_rete"),
            "temperatura_radiatore_c": ultima.get("temperatura_radiatore"),
            "energia_totale_kwh": ultima.get("energia_prodotta_totale"),
        }
    return {
        "generato": adesso_loc.isoformat(timespec="seconds"),
        "ultima_lettura": info_ultima,
        "oggi": giorno_oggi,
        "giorni": lista_giorni,
        "mesi": lista_mesi,
        "potenza": calcoli.serie_potenza(righe_ore, tz),
        "batteria": calcoli.stato_batteria(ultima),
        "attesa": {
            "configurata": mensili is not None,
            "info": info_pvgis or {},
            "mensili": [dict(mese=m, **mensili[m]) for m in sorted(mensili)] if mensili else [],
        },
        "impianto": {"kwp": kwp},
        "avvisi": lista_avvisi,
        "parametri": {"ore": ore, "giorni": giorni},
    }


def _niente_rete(_parametri):
    raise RuntimeError("rete disattivata con --no-pvgis")


def dati_pvgis(parametri, usa_rete=True):
    """(mensili, info) da PVGIS con cache, oppure (None, {"errore": ...})."""
    if not parametri:
        return None, {"errore": "non configurato: servono PVGIS_LAT, PVGIS_LON e IMPIANTO_KWP nel file .env"}
    return pvgis.carica(parametri, CACHE_PVGIS, scaricatore=pvgis.scarica if usa_rete else _niente_rete)


# ---------- server HTTP ----------

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # Su Windows il default (riuso dell'indirizzo) permette a due programmi di
    # ascoltare sulla stessa porta senza errori: meglio fallire subito se è occupata.
    allow_reuse_address = False

    def __init__(self, indirizzo, percorso_db, kwp=None, parametri_pvgis=None, usa_rete=True):
        super().__init__(indirizzo, Gestore)
        self.percorso_db = percorso_db
        self.kwp = kwp
        self.parametri_pvgis = parametri_pvgis
        self.usa_rete = usa_rete


class Gestore(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path in ("/", "/index.html"):
            self._invia(PAGINA.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/dati":
            self._api(urllib.parse.parse_qs(url.query))
        else:
            self.send_error(404, "Pagina non trovata")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def _api(self, q):
        try:
            ore = max(1, min(MAX_ORE, int(q.get("ore", ["12"])[0])))
            giorni = max(1, min(MAX_GIORNI, int(q.get("giorni", ["31"])[0])))
            mensili, info = dati_pvgis(self.server.parametri_pvgis, self.server.usa_rete)
            con = apri_sola_lettura(self.server.percorso_db)
            try:
                dati = costruisci_dati(con, self.server.kwp, ore, giorni, mensili=mensili, info_pvgis=info)
            finally:
                con.close()
        except Exception as errore:               # noqa: BLE001 - la pagina mostra l'errore
            logging.exception("errore nella risposta /api/dati")
            dati = {"errore": f"{type(errore).__name__}: {errore}"}
        self._invia(json.dumps(dati, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _invia(self, corpo, tipo):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, formato, *args):
        logging.info("%s " + formato, self.address_string(), *args)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dashboard web locale del fotovoltaico (sola lettura).")
    parser.add_argument("--porta", type=int, default=None,
                        help="porta del server (default: DASHBOARD_PORTA nel .env, poi la variabile PORT, "
                             f"oppure {PORTA_DEFAULT})")
    parser.add_argument("--db", default=None,
                        help="percorso del database SQLite (default: RACCOLTA_DB nel .env, oppure dati.db qui accanto)")
    parser.add_argument("--env", default=str(CARTELLA / ".env"),
                        help="file .env da leggere (default: .env qui accanto); utile per prove con dati finti")
    parser.add_argument("--no-pvgis", action="store_true",
                        help="non contattare PVGIS: usa solo la cache, se esiste")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(args.env)
    args.porta = args.porta or int(os.getenv("DASHBOARD_PORTA") or os.getenv("PORT") or PORTA_DEFAULT)
    args.db = args.db or os.getenv("RACCOLTA_DB") or str(CARTELLA / "dati.db")

    if not pathlib.Path(args.db).exists():
        logging.error("database non trovato: %s", args.db)
        return 2
    parametri = pvgis.parametri_da_env(os.environ)
    kwp = parametri["peakpower"] if parametri else None
    if kwp is None and (os.getenv("IMPIANTO_KWP") or "").strip():
        kwp = float(os.getenv("IMPIANTO_KWP").replace(",", "."))
    if not parametri:
        logging.warning("PVGIS non configurato: la produzione attesa resta vuota "
                        "(servono PVGIS_LAT, PVGIS_LON e IMPIANTO_KWP nel file .env)")

    server = Server(("127.0.0.1", args.porta), args.db, kwp, parametri, usa_rete=not args.no_pvgis)
    logging.info("dashboard su http://127.0.0.1:%s (Ctrl+C per fermare), database %s", args.porta, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
