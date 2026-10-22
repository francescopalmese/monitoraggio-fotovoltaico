"""
Test automatici con dati finti: nessun inverter richiesto.
Lanciare dalla cartella del progetto:  python -m pytest tests -q
"""
import sqlite3

import pytest

import archivio
import lettore
from registri import BLOCCHI, REGISTRI, decodifica


# ---------- decodifica dei registri ----------

def test_u16_con_scala():
    # pv_potenza_totale: 0x05C4, u16, scala 100 W
    assert decodifica(0x05C4, [37]) == [("pv_potenza_totale", 3700, "W")]


def test_s16_negativo():
    # batteria_potenza: 0x0606, s16, scala 10 W; 0xFF00 = -256 -> -2560 W
    valori = dict((n, v) for n, v, _ in decodifica(0x0604, [3472, 0xFD04, 0xFF00, 36, 83, 96, 831]))
    assert valori["batteria_potenza"] == -2560
    assert valori["batteria_corrente"] == pytest.approx(-7.64)
    assert valori["batteria_tensione"] == pytest.approx(347.2)
    assert valori["batteria_soc"] == 83


def test_u32_parola_alta_prima():
    # energia_prodotta_totale: 0x0686..0x0687, u32, scala 0.1 kWh
    # 0x0008 0x0001 -> (8 << 16) | 1 = 524289 -> 52428.9 kWh
    grezzi = [0, 0, 0x0008, 0x0001]
    valori = dict((n, v) for n, v, _ in decodifica(0x0684, grezzi))
    assert valori["energia_prodotta_oggi"] == 0
    assert valori["energia_prodotta_totale"] == pytest.approx(52428.9)


def test_ascii():
    parole = [0x5A50, 0x3145, 0x5330, 0x3130, 0x4142, 0x4A35, 0x3334, 0x0000]
    assert decodifica(0x0445, parole) == [("seriale_inverter", "ZP1ES010ABJ534", "")]


def test_registro_fuori_dal_blocco_non_viene_decodificato():
    # blocco troppo corto per contenere il u32 in 0x0684-0x0685
    assert decodifica(0x0684, [1]) == []


def test_blocchi_coprono_tutti_i_registri():
    for nome, d in REGISTRI.items():
        a, n = d["indirizzo"], d["n"]
        assert any(inizio <= a and a + n <= inizio + quanti for inizio, quanti in BLOCCHI), nome


# ---------- lettore con client finto ----------

class ClientFinto:
    """Risponde con registri fissi; conta le richieste."""
    def __init__(self):
        self.richieste = []

    def read_holding_registers(self, register_addr, quantity):
        self.richieste.append((register_addr, quantity))
        base = [0] * quantity
        if register_addr == 0x0404:
            base[0] = 2                       # On-grid
        if register_addr == 0x05C4:
            base[0] = 42                      # 4200 W
        if register_addr == 0x0604:
            base[4] = 83                      # SOC
        return base


def test_lettore_legge_tutti_i_blocchi():
    client = ClientFinto()
    valori = lettore.LettoreInverter(client, pausa=0).leggi_tutto()
    assert [r[0] for r in client.richieste] == [b[0] for b in BLOCCHI]
    assert valori["stato_inverter"] == 2
    assert valori["pv_potenza_totale"] == 4200
    assert valori["batteria_soc"] == 83
    assert set(valori) == set(REGISTRI)


def test_lettore_si_arrende_dopo_i_tentativi():
    class ClientCorto:
        chiamate = 0
        def read_holding_registers(self, register_addr, quantity):
            self.chiamate += 1
            return [0] * (quantity - 1)
    client = ClientCorto()
    with pytest.raises(RuntimeError):
        lettore.LettoreInverter(client, pausa=0, tentativi=3, pausa_errore=0).leggi_tutto()
    assert client.chiamate == 3          # tre tentativi sul primo blocco, poi stop


def test_lettore_riprova_dopo_errore_crc():
    class ClientBallerino(ClientFinto):
        """Fallisce la prima richiesta di ogni blocco, come un frame corrotto."""
        def __init__(self):
            super().__init__()
            self.falliti = set()
        def read_holding_registers(self, register_addr, quantity):
            if register_addr not in self.falliti:
                self.falliti.add(register_addr)
                raise ValueError("CRC validation failed.")
            return super().read_holding_registers(register_addr, quantity)
    client = ClientBallerino()
    lettore_ = lettore.LettoreInverter(client, pausa=0, tentativi=2, pausa_errore=0)
    valori = lettore_.leggi_tutto()
    assert valori["pv_potenza_totale"] == 4200
    assert lettore_.errori_recuperati == len(BLOCCHI)


# ---------- archivio SQLite ----------

def test_archivio_salva_e_rilegge(tmp_path):
    con = archivio.apri(tmp_path / "prova.db")
    ts = archivio.salva(con, {"pv_potenza_totale": 1500, "batteria_soc": 55}, ts="2026-10-16T17:00:00+00:00")
    assert ts == "2026-10-16T17:00:00+00:00"
    assert archivio.conta(con) == 1
    riga = archivio.ultime(con, 1)[0]
    assert riga["pv_potenza_totale"] == 1500
    assert riga["batteria_soc"] == 55
    assert riga["potenza_carico"] is None        # non passato: resta vuoto


def test_archivio_aggiunge_colonne_mancanti(tmp_path):
    percorso = tmp_path / "vecchio.db"
    con = sqlite3.connect(percorso)
    con.execute("CREATE TABLE letture (ts TEXT PRIMARY KEY, pv_potenza_totale REAL)")
    con.commit()
    con.close()
    con = archivio.apri(percorso)
    colonne = {r[1] for r in con.execute("PRAGMA table_info(letture)")}
    assert set(archivio.COLONNE) <= colonne


def test_archivio_rifiuta_timestamp_duplicato(tmp_path):
    con = archivio.apri(tmp_path / "prova.db")
    archivio.salva(con, {"batteria_soc": 1}, ts="2026-10-16T17:00:00+00:00")
    with pytest.raises(sqlite3.IntegrityError):
        archivio.salva(con, {"batteria_soc": 2}, ts="2026-10-16T17:00:00+00:00")
