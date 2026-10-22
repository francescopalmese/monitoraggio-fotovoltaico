"""
Test del client PVGIS con una risposta finta: nessuna richiesta di rete.
"""
import datetime
import json

import pytest

import pvgis

PARAMETRI = {"lat": 45.07, "lon": 7.69, "peakpower": 10.0, "loss": 14.0, "angle": 30.0, "aspect": 0.0}
ADESSO = datetime.datetime(2026, 10, 16, 20, 0, tzinfo=datetime.timezone.utc)


def risposta_finta(fattore=1.0):
    """Stessa struttura della risposta vera di PVcalc (vista il 16/10/2026)."""
    mensili = [{"month": m, "E_d": round(20.0 * m * fattore, 2), "E_m": round(600.0 * m * fattore, 2),
                "H(i)_d": 3.0, "H(i)_m": 90.0, "SD_m": 100.0} for m in range(1, 13)]
    return {
        "inputs": {
            "location": {"latitude": 45.07, "longitude": 7.69, "elevation": 248.0},
            "meteo_data": {"radiation_db": "PVGIS-SARAH3", "meteo_db": "ERA5",
                           "year_min": 2005, "year_max": 2023},
            "mounting_system": {"fixed": {"slope": {"value": 30, "optimal": False},
                                          "azimuth": {"value": 0, "optimal": False}}},
            "pv_module": {"technology": "c-Si", "peak_power": 10.0, "system_loss": 14.0},
        },
        "outputs": {"monthly": {"fixed": mensili},
                    "totals": {"fixed": {"E_d": 36.69, "E_m": 1115.91, "E_y": 13390.89}}},
        "meta": {},
    }


def test_url_con_tutti_i_parametri():
    url = pvgis.costruisci_url(PARAMETRI)
    assert url.startswith("https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?")
    for pezzo in ("lat=45.07", "lon=7.69", "peakpower=10.0", "loss=14.0", "angle=30.0", "aspect=0.0",
                  "outputformat=json"):
        assert pezzo in url
    assert "optimalinclination" not in url


def test_url_inclinazione_ottimale_se_manca_l_angolo():
    url = pvgis.costruisci_url(dict(PARAMETRI, angle=None))
    assert "optimalinclination=1" in url and "angle=" not in url


def test_parametri_da_env():
    assert pvgis.parametri_da_env({}) is None
    assert pvgis.parametri_da_env({"PVGIS_LAT": "45", "PVGIS_LON": "7"}) is None      # manca kWp
    p = pvgis.parametri_da_env({"PVGIS_LAT": "45,07", "PVGIS_LON": "7.69", "IMPIANTO_KWP": "9,8",
                                "PVGIS_INCLINAZIONE": "", "PVGIS_ORIENTAMENTO": "-10"})
    assert p == {"lat": 45.07, "lon": 7.69, "peakpower": 9.8, "loss": 14.0, "angle": None, "aspect": -10.0}


def test_estrai_mensili_e_info():
    mensili = pvgis.estrai_mensili(risposta_finta())
    assert sorted(mensili) == list(range(1, 13))
    assert mensili[10] == {"E_d": 200.0, "E_m": 6000.0, "H_d": 3.0, "H_m": 90.0}
    info = pvgis.info_fonte(risposta_finta())
    assert info["database"] == "PVGIS-SARAH3" and info["anni"] == "2005-2023"
    assert info["kwp"] == 10.0 and info["annuale_kwh"] == 13390.89
    assert "lat" not in json.dumps(info) and "45.07" not in json.dumps(info)   # posizione mai in pagina


def test_estrai_mensili_rifiuta_risposta_incompleta():
    r = risposta_finta()
    r["outputs"]["monthly"]["fixed"] = r["outputs"]["monthly"]["fixed"][:5]
    with pytest.raises(ValueError):
        pvgis.estrai_mensili(r)


class Scaricatore:
    """Finto scaricatore: conta le chiamate, può fallire."""
    def __init__(self, fallisce=False, fattore=1.0):
        self.chiamate = 0
        self.fallisce = fallisce
        self.fattore = fattore

    def __call__(self, p):
        self.chiamate += 1
        if self.fallisce:
            raise OSError("rete assente")
        return risposta_finta(self.fattore)


def test_cache_evita_nuove_richieste_per_un_mese(tmp_path):
    cache = tmp_path / "pvgis_cache.json"
    s = Scaricatore()
    mensili, info = pvgis.carica(PARAMETRI, cache, scaricatore=s, adesso=ADESSO)
    assert s.chiamate == 1 and mensili[1]["E_d"] == 20.0 and info["scaricato"] == "2026-10-16"
    assert cache.exists()
    pvgis.carica(PARAMETRI, cache, scaricatore=s, adesso=ADESSO + datetime.timedelta(days=29))
    assert s.chiamate == 1                                            # ancora fresca
    pvgis.carica(PARAMETRI, cache, scaricatore=s, adesso=ADESSO + datetime.timedelta(days=31))
    assert s.chiamate == 2                                            # scaduta: scaricata di nuovo


def test_cache_ignorata_se_cambiano_i_parametri(tmp_path):
    cache = tmp_path / "pvgis_cache.json"
    s = Scaricatore()
    pvgis.carica(PARAMETRI, cache, scaricatore=s, adesso=ADESSO)
    pvgis.carica(dict(PARAMETRI, peakpower=12.0), cache, scaricatore=s, adesso=ADESSO)
    assert s.chiamate == 2


def test_senza_rete_si_usa_la_cache_vecchia_con_avviso(tmp_path):
    cache = tmp_path / "pvgis_cache.json"
    pvgis.carica(PARAMETRI, cache, scaricatore=Scaricatore(), adesso=ADESSO)
    dopo = ADESSO + datetime.timedelta(days=60)
    mensili, info = pvgis.carica(PARAMETRI, cache, scaricatore=Scaricatore(fallisce=True), adesso=dopo)
    assert mensili[1]["E_d"] == 20.0
    assert "2026-10-16" in info["avviso"]


def test_senza_rete_e_senza_cache_nessun_dato(tmp_path):
    mensili, info = pvgis.carica(PARAMETRI, tmp_path / "pvgis_cache.json",
                                 scaricatore=Scaricatore(fallisce=True), adesso=ADESSO)
    assert mensili is None and "errore" in info
