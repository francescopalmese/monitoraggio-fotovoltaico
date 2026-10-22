"""
Test dei calcoli della dashboard con dati finti (nessun database, nessuna rete).
Lanciare dalla cartella del progetto:  python -m pytest tests -q
"""
import datetime

import pytest

import calcoli

TZ = datetime.timezone(datetime.timedelta(hours=2))      # ora legale italiana, fissa nei test


def ts(data_ora_locale):
    """'2026-10-16 20:05' in ora locale (TZ) -> timestamp UTC ISO come in dati.db."""
    dt = datetime.datetime.fromisoformat(data_ora_locale).replace(tzinfo=TZ)
    return dt.astimezone(calcoli.UTC).isoformat(timespec="seconds")


def lettura(data_ora_locale, **campi):
    r = {"ts": ts(data_ora_locale)}
    r.update(campi)
    return r


# ---------- giorni ----------

def test_giorno_usa_ultima_lettura_non_il_massimo():
    righe = [
        lettura("2026-10-16 10:00", energia_prodotta_oggi=5.0),
        lettura("2026-10-16 23:59", energia_prodotta_oggi=20.0),
        lettura("2026-10-17 00:00", energia_prodotta_oggi=20.0),   # non ancora azzerata
        lettura("2026-10-17 00:02", energia_prodotta_oggi=0.0),
        lettura("2026-10-17 12:00", energia_prodotta_oggi=8.0),
    ]
    giorni = calcoli.aggrega_giorni(righe, tz=TZ)
    assert [g["data"] for g in giorni] == ["2026-10-16", "2026-10-17"]
    assert giorni[0]["prodotta"] == 20.0
    assert giorni[1]["prodotta"] == 8.0          # con il massimo sarebbe 20: sbagliato
    assert giorni[1]["prima"] == "00:00" and giorni[1]["ultima"] == "12:00"
    assert giorni[1]["n_letture"] == 3


def test_giorni_raggruppati_per_data_locale_non_utc():
    # 22:30 UTC del 15/10 = 00:30 del 16/10 in Italia (ora legale)
    r = {"ts": "2026-10-15T22:30:00+00:00", "energia_prodotta_oggi": 0.1}
    giorni = calcoli.aggrega_giorni([r], tz=TZ)
    assert giorni[0]["data"] == "2026-10-16"


def test_autoconsumo_e_autosufficienza():
    # numeri reali letti il 16/10/2026 alle 20:05
    r = lettura("2026-10-16 20:05", energia_prodotta_oggi=23.16, energia_immessa_oggi=0.86,
                energia_consumata_oggi=16.63, energia_prelevata_oggi=3.49)
    g = calcoli.aggrega_giorni([r], tz=TZ)[0]
    assert g["autoconsumo"] == pytest.approx(22.30)             # prodotta - immessa
    assert g["autoconsumo_pct"] == pytest.approx(96.3)
    assert g["autosufficienza"] == pytest.approx(13.14)         # consumata - prelevata
    assert g["autosufficienza_pct"] == pytest.approx(79.0)


def test_autoconsumo_non_va_sotto_zero_e_manca_senza_contatori():
    g = calcoli.aggrega_giorni([lettura("2026-10-16 12:00", energia_prodotta_oggi=1.0,
                                        energia_immessa_oggi=1.5)], tz=TZ)[0]
    assert g["autoconsumo"] == 0.0
    assert g["autosufficienza"] is None and g["autosufficienza_pct"] is None


def test_picco_e_media_oraria_massima():
    righe = [
        lettura("2026-10-16 12:10", pv_potenza_totale=1000),
        lettura("2026-10-16 12:40", pv_potenza_totale=9000),    # schiarita: media dell'ora 5000
        lettura("2026-10-16 13:10", pv_potenza_totale=6000),
        lettura("2026-10-16 13:40", pv_potenza_totale=6000),    # ora piena di sole: media 6000
    ]
    g = calcoli.aggrega_giorni(righe, tz=TZ)[0]
    assert g["picco_pv_w"] == 9000
    assert g["max_media_oraria_w"] == 6000


def test_copertura_e_soc():
    righe = [lettura(f"2026-10-16 10:{m:02d}", batteria_soc=50 + m) for m in range(0, 60)]
    g = calcoli.aggrega_giorni(righe, tz=TZ)[0]
    assert g["n_letture"] == 60
    assert g["copertura"] == pytest.approx(60 / 1440, abs=1e-3)
    assert (g["soc_min"], g["soc_max"]) == (50, 109)


# ---------- mesi ----------

def test_mesi_sommano_i_giorni():
    righe = [
        lettura("2026-09-30 20:00", energia_prodotta_oggi=30.0, energia_immessa_oggi=10.0,
                energia_consumata_oggi=15.0, energia_prelevata_oggi=5.0),
        lettura("2026-10-01 20:00", energia_prodotta_oggi=20.0, energia_immessa_oggi=5.0,
                energia_consumata_oggi=10.0, energia_prelevata_oggi=2.0),
        lettura("2026-10-02 20:00", energia_prodotta_oggi=10.0, energia_immessa_oggi=0.0,
                energia_consumata_oggi=12.0, energia_prelevata_oggi=4.0),
    ]
    mesi = calcoli.aggrega_mesi(calcoli.aggrega_giorni(righe, tz=TZ))
    assert [m["mese"] for m in mesi] == ["2026-09", "2026-10"]
    ottobre = mesi[1]
    assert ottobre["giorni_con_dati"] == 2
    assert ottobre["prodotta"] == 30.0 and ottobre["immessa"] == 5.0
    assert ottobre["autoconsumo"] == 25.0 and ottobre["autoconsumo_pct"] == pytest.approx(83.3)
    assert ottobre["autosufficienza"] == 16.0 and ottobre["autosufficienza_pct"] == pytest.approx(72.7)


# ---------- potenza e batteria ----------

def test_serie_potenza_in_ora_locale_e_ordinata():
    righe = [lettura("2026-10-16 20:05", pv_potenza_totale=0, potenza_carico=750,
                     potenza_rete=0, batteria_potenza=-790, batteria_soc=82),
             lettura("2026-10-16 20:04", pv_potenza_totale=0, potenza_carico=740)]
    punti = calcoli.serie_potenza(righe, tz=TZ)
    assert [p["ora"] for p in punti] == ["20:04", "20:05"]
    assert punti[1]["batteria_w"] == -790 and punti[1]["soc"] == 82
    assert punti[0]["rete_w"] is None


def test_stato_batteria():
    assert calcoli.stato_batteria({"batteria_potenza": -790, "batteria_soc": 82})["verso"] == "in scarica"
    assert calcoli.stato_batteria({"batteria_potenza": 2000})["verso"] == "in carica"
    assert calcoli.stato_batteria({"batteria_potenza": 10})["verso"] == "ferma"
    assert calcoli.stato_batteria({})["verso"] == "sconosciuto"
    assert calcoli.stato_batteria(None) is None


# ---------- attesa PVGIS ----------

MENSILI = {m: {"E_d": 10.0 * m, "E_m": 300.0 * m} for m in range(1, 13)}


def test_attesa_giorno_e_mese():
    assert calcoli.attesa_giorno(MENSILI, "2026-10-16") == 100.0
    assert calcoli.attesa_mese(MENSILI, "2026-09") == 2700.0            # mese intero: E_m
    assert calcoli.attesa_mese(MENSILI, "2026-10", giorni_trascorsi=16) == 1600.0   # in corso: E_d * giorni
    assert calcoli.attesa_giorno(None, "2026-10-16") is None
    assert calcoli.attesa_mese({}, "2026-10") is None


# ---------- avvisi ----------

ADESSO = datetime.datetime(2026, 10, 16, 20, 0, tzinfo=TZ)


def giorno(data, prodotta, media_oraria_w, copertura=1.0):
    n = int(copertura * 1440)
    return {"data": data, "prodotta": prodotta, "max_media_oraria_w": media_oraria_w,
            "n_letture": n, "copertura": copertura}


def codici(lista):
    return [a["codice"] for a in lista]


def test_avviso_nessuna_lettura_oltre_dieci_minuti():
    vecchia = ts("2026-10-16 19:49")       # 11 minuti prima
    recente = ts("2026-10-16 19:55")       # 5 minuti prima
    assert codici(calcoli.avvisi(vecchia, ADESSO, tz=TZ)) == ["nessuna_lettura"]
    assert "19:49" in calcoli.avvisi(vecchia, ADESSO, tz=TZ)[0]["testo"]
    assert calcoli.avvisi(recente, ADESSO, tz=TZ) == []


def test_avviso_database_vuoto():
    assert codici(calcoli.avvisi(None, ADESSO, tz=TZ)) == ["nessun_dato"]


def test_avviso_inverter_in_guasto():
    recente = ts("2026-10-16 19:59")
    assert codici(calcoli.avvisi(recente, ADESSO, stato_inverter=5, tz=TZ)) == ["inverter_guasto"]
    assert calcoli.avvisi(recente, ADESSO, stato_inverter=2, tz=TZ) == []


def test_avviso_produzione_bassa_in_giorno_di_sole():
    # ieri: attesa 100 kWh, prodotti 10, media oraria massima 6 kW su 10 kWp -> sole forte
    ieri = giorno("2026-10-15", prodotta=10.0, media_oraria_w=6000)
    lista = calcoli.avvisi(ts("2026-10-16 19:59"), ADESSO, giorni=[ieri], mensili=MENSILI, kwp=10, tz=TZ)
    assert codici(lista) == ["produzione_bassa"]
    assert "15/10" in lista[0]["testo"] and "100.0 kWh" in lista[0]["testo"]


def test_nessun_avviso_in_giorno_nuvoloso_o_con_produzione_normale():
    nuvoloso = giorno("2026-10-15", prodotta=10.0, media_oraria_w=1500)      # poco sole: normale
    normale = giorno("2026-10-15", prodotta=80.0, media_oraria_w=6000)        # sole e produzione ok
    for g in (nuvoloso, normale):
        assert calcoli.avvisi(ts("2026-10-16 19:59"), ADESSO, giorni=[g], mensili=MENSILI, kwp=10, tz=TZ) == []


def test_avviso_oggi_solo_dalle_18_e_con_abbastanza_letture():
    oggi = giorno("2026-10-16", prodotta=10.0, media_oraria_w=6000)
    oggi["n_letture"] = 20 * 60                                       # letture dalle 00:00 alle 20:00
    presto = ADESSO.replace(hour=15)
    assert calcoli.avvisi(ts("2026-10-16 14:59"), presto, giorni=[oggi], mensili=MENSILI, kwp=10, tz=TZ) == []
    assert codici(calcoli.avvisi(ts("2026-10-16 19:59"), ADESSO, giorni=[oggi], mensili=MENSILI, kwp=10, tz=TZ)) == ["produzione_bassa"]
    oggi["n_letture"] = 100                                           # raccolta partita tardi: totale parziale
    assert calcoli.avvisi(ts("2026-10-16 19:59"), ADESSO, giorni=[oggi], mensili=MENSILI, kwp=10, tz=TZ) == []


def test_nessun_avviso_senza_pvgis_o_kwp_o_per_giorni_vecchi():
    ieri = giorno("2026-10-15", prodotta=10.0, media_oraria_w=6000)
    vecchio = giorno("2026-10-10", prodotta=10.0, media_oraria_w=6000)
    recente = ts("2026-10-16 19:59")
    assert calcoli.avvisi(recente, ADESSO, giorni=[ieri], mensili=None, kwp=10, tz=TZ) == []
    assert calcoli.avvisi(recente, ADESSO, giorni=[ieri], mensili=MENSILI, kwp=None, tz=TZ) == []
    assert calcoli.avvisi(recente, ADESSO, giorni=[vecchio], mensili=MENSILI, kwp=10, tz=TZ) == []
