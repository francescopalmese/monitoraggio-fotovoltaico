"""
Archivio delle letture su SQLite.

Una riga per lettura nella tabella `letture`: colonna `ts` (data e ora UTC in
formato ISO) più una colonna numerica per ogni registro della mappa (tranne
quelli di testo, come il seriale). Se in futuro la mappa cresce, le colonne
mancanti vengono aggiunte automaticamente.
"""
import datetime
import sqlite3

from registri import REGISTRI

COLONNE = [nome for nome, d in REGISTRI.items() if d["tipo"] != "ascii"]


def adesso_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def apri(percorso):
    """Apre (o crea) il database e allinea le colonne alla mappa dei registri."""
    con = sqlite3.connect(percorso)
    con.execute("CREATE TABLE IF NOT EXISTS letture (ts TEXT PRIMARY KEY)")
    esistenti = {riga[1] for riga in con.execute("PRAGMA table_info(letture)")}
    for colonna in COLONNE:
        if colonna not in esistenti:
            con.execute(f'ALTER TABLE letture ADD COLUMN "{colonna}" REAL')
    con.commit()
    return con


def salva(con, valori, ts=None):
    """Salva una lettura {nome: valore}; restituisce il timestamp usato."""
    ts = ts or adesso_utc()
    colonne = [c for c in COLONNE if c in valori]
    nomi = ", ".join(f'"{c}"' for c in colonne)
    segnaposto = ", ".join("?" for _ in colonne)
    con.execute(f'INSERT INTO letture (ts, {nomi}) VALUES (?, {segnaposto})',
                [ts] + [valori[c] for c in colonne])
    con.commit()
    return ts


def ultime(con, n=10):
    """Restituisce le ultime n letture come lista di dizionari, dalla più recente."""
    con.row_factory = sqlite3.Row
    righe = con.execute("SELECT * FROM letture ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
    con.row_factory = None
    return [dict(r) for r in righe]


def conta(con):
    return con.execute("SELECT COUNT(*) FROM letture").fetchone()[0]
