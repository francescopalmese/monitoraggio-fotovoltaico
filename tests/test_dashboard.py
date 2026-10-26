"""
Test della dashboard con un database finto: costruzione dei dati per la pagina,
connessione in sola lettura e server HTTP locale (porta scelta dal sistema).
"""
import datetime
import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

import archivio
import calcoli
import dashboard

UTC = calcoli.UTC
MENSILI = {m: {"E_d": 30.0, "E_m": 900.0} for m in range(1, 13)}


def db_finto(percorso):
    """Due giorni (15 e 16/10/2026) di letture finte tra le 10:00 e le 13:50 UTC, una ogni 10
    minuti: è pieno giorno in qualunque fuso europeo, così la data locale non cambia.
    Restituisce il timestamp dell'ultima lettura."""
    con = archivio.apri(percorso)
    base = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    ultimo = None
    for giorno in range(2):
        for minuto in range(0, 240, 10):
            ultimo = base + datetime.timedelta(days=giorno, minutes=minuto)
            prodotta = round(0.1 * (minuto // 10) * (giorno + 1), 2)       # cresce durante il giorno
            archivio.salva(con, {
                "stato_inverter": 2, "pv_potenza_totale": 3000 + 100 * (minuto // 10),
                "potenza_carico": 800, "potenza_rete": -500, "batteria_potenza": 1500,
                "batteria_soc": 50 + minuto // 10, "batteria_soh": 96, "batteria_cicli": 831,
                "energia_prodotta_oggi": prodotta, "energia_consumata_oggi": round(prodotta * 0.5, 2),
                "energia_immessa_oggi": round(prodotta * 0.2, 2), "energia_prelevata_oggi": 0.1,
                "energia_carica_batteria_oggi": round(prodotta * 0.3, 2), "energia_scarica_batteria_oggi": 0.0,
            }, ts=ultimo.isoformat(timespec="seconds"))
    con.close()
    return ultimo


def test_costruisci_dati_con_database_finto(tmp_path):
    percorso = tmp_path / "finto.db"
    ultima = db_finto(percorso)
    con = dashboard.apri_sola_lettura(percorso)
    adesso = ultima + datetime.timedelta(minutes=5)
    d = dashboard.costruisci_dati(con, kwp=10, ore=2, giorni=7, adesso=adesso, tz=UTC,
                                  mensili=MENSILI, info_pvgis={"database": "finto"})
    assert d["ultima_lettura"]["minuti_fa"] == 5
    assert d["ultima_lettura"]["stato_testo"] == "Connesso alla rete"
    assert [g["data"] for g in d["giorni"]] == ["2026-10-15", "2026-10-16"]
    assert d["oggi"]["data"] == "2026-10-16"
    assert d["oggi"]["prodotta"] == pytest.approx(4.6)           # ultima lettura del giorno: 23 * 0.1 * 2
    assert d["oggi"]["attesa"] == 30.0
    assert d["giorni"][0]["prodotta"] == pytest.approx(2.3)
    mese = d["mesi"][0]
    assert mese["mese"] == "2026-10" and mese["giorni_con_dati"] == 2
    assert mese["prodotta"] == pytest.approx(6.9)
    assert mese["attesa"] == pytest.approx(30.0 * 2)               # E_d per i giorni con dati
    assert len(d["potenza"]) == 12                                 # ultime 2 ore: 12:00 .. 13:50
    assert d["potenza"][-1]["ora"] == "13:50"
    assert d["batteria"]["verso"] == "in carica" and d["batteria"]["soc"] == 73
    assert d["attesa"]["configurata"] is True and len(d["attesa"]["mensili"]) == 12
    assert d["avvisi"] == []
    json.dumps(d)                                                  # serializzabile per l'API
    con.close()


def test_avviso_nessuna_lettura_dai_dati_del_database(tmp_path):
    percorso = tmp_path / "finto.db"
    ultima = db_finto(percorso)
    con = dashboard.apri_sola_lettura(percorso)
    d = dashboard.costruisci_dati(con, kwp=10, adesso=ultima + datetime.timedelta(minutes=20), tz=UTC)
    assert [a["codice"] for a in d["avvisi"]] == ["nessuna_lettura"]
    assert d["attesa"]["configurata"] is False and d["oggi"]["attesa"] is None
    con.close()


def test_connessione_in_sola_lettura_rifiuta_le_scritture(tmp_path):
    percorso = tmp_path / "finto.db"
    db_finto(percorso)
    con = dashboard.apri_sola_lettura(percorso)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO letture (ts) VALUES ('2030-01-01T00:00:00+00:00')")
    con.close()


def test_pvgis_non_configurato_o_senza_rete(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "CACHE_PVGIS", tmp_path / "cache.json")
    mensili, info = dashboard.dati_pvgis(None)
    assert mensili is None and "non configurato" in info["errore"]
    parametri = {"lat": 45.0, "lon": 7.0, "peakpower": 10.0, "loss": 14.0, "angle": 30.0, "aspect": 0.0}
    mensili, info = dashboard.dati_pvgis(parametri, usa_rete=False)
    assert mensili is None and "rete disattivata" in info["errore"]


def test_server_http_serve_pagina_e_api(tmp_path, monkeypatch):
    percorso = tmp_path / "finto.db"
    db_finto(percorso)
    monkeypatch.setattr(dashboard, "CACHE_PVGIS", tmp_path / "cache.json")
    server = dashboard.Server(("127.0.0.1", 0), str(percorso), kwp=10, parametri_pvgis=None, usa_rete=False)
    porta = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=5) as r:
            assert r.headers["Content-Type"].startswith("text/html")
            pagina = r.read().decode("utf-8")
        assert pagina.lower().startswith("<!doctype html>") and "Fotovoltaico di casa" in pagina
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/dati?ore=2&giorni=7", timeout=5) as r:
            assert r.headers["Content-Type"].startswith("application/json")
            d = json.load(r)
        assert d["parametri"] == {"ore": 2, "giorni": 7}
        assert d["ultima_lettura"]["ts"] == "2026-10-16T13:50:00+00:00"
        assert d["attesa"]["configurata"] is False
        assert "nessuna_lettura" in [a["codice"] for a in d["avvisi"]]   # i dati finti sono vecchi
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/logo.png", timeout=5) as r:   # il polpo della testata
            assert r.headers["Content-Type"] == "image/png"
            assert r.read()[:8] == b"\x89PNG\r\n\x1a\n"
        assert '<img src="/logo.png"' in pagina
        with pytest.raises(urllib.error.HTTPError) as errore:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/altro", timeout=5)
        assert errore.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
