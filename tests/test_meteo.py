"""Test del modulo meteo con risposte finte: niente rete."""
import datetime

import meteo

RISPOSTA = {
    "current": {"time": "2026-10-26T14:00", "temperature_2m": 16.4, "weather_code": 3, "cloud_cover": 92,
                "wind_speed_10m": 7.5, "is_day": 1},
    "daily": {"time": ["2026-10-26"], "temperature_2m_max": [18.1], "temperature_2m_min": [9.3],
              "sunrise": ["2026-10-26T07:41"], "sunset": ["2026-10-26T18:16"], "weather_code": [61]},
}


def test_url_contiene_posizione_e_campi():
    url = meteo.costruisci_url(45.07, 7.69)
    assert "latitude=45.07" in url and "longitude=7.69" in url
    assert "temperature_2m" in url and "weather_code" in url and "forecast_days=1" in url


def test_estrai_traduce_codice_e_giornata():
    m = meteo.estrai(RISPOSTA)
    assert m["temperatura_c"] == 16.4
    assert m["descrizione"] == "coperto" and m["simbolo"] == "☁"
    assert m["t_max_c"] == 18.1 and m["t_min_c"] == 9.3
    assert m["alba"] == "07:41" and m["tramonto"] == "18:16"
    assert m["giorno"] is True and m["ora"] == "14:00"


def test_estrai_di_notte_con_cielo_sereno_mostra_la_luna():
    r = {"current": {"weather_code": 0, "is_day": 0}, "daily": {}}
    m = meteo.estrai(r)
    assert m["descrizione"] == "sereno" and m["simbolo"] == "🌙"
    assert m["alba"] == "" and m["t_max_c"] is None


def test_codice_sconosciuto_non_rompe():
    m = meteo.estrai({"current": {"weather_code": 123}, "daily": {}})
    assert m["descrizione"] == "tempo sconosciuto"


def test_cache_in_memoria_e_scadenza():
    chiamate = []
    def finto(lat, lon):
        chiamate.append((lat, lon))
        return RISPOSTA
    t0 = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)
    m = meteo.Meteo(eta_max=600)
    a = m.attuale(45.07, 7.69, scaricatore=finto, adesso=t0)
    b = m.attuale(45.07, 7.69, scaricatore=finto, adesso=t0 + datetime.timedelta(seconds=300))
    assert a is b and len(chiamate) == 1                     # entro 10 minuti: nessuna nuova richiesta
    m.attuale(45.07, 7.69, scaricatore=finto, adesso=t0 + datetime.timedelta(seconds=700))
    assert len(chiamate) == 2                                # scaduta: si richiede
    m.attuale(44.0, 8.0, scaricatore=finto, adesso=t0 + datetime.timedelta(seconds=701))
    assert len(chiamate) == 3                                # posizione diversa: si richiede


def test_errore_di_rete_restituisce_errore_o_ultimo_meteo_buono():
    def rotto(lat, lon):
        raise OSError("rete assente")
    m = meteo.Meteo(eta_max=600)
    t0 = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=datetime.timezone.utc)
    primo = m.attuale(45.07, 7.69, scaricatore=rotto, adesso=t0)
    assert "errore" in primo
    m.attuale(45.07, 7.69, scaricatore=lambda a, b: RISPOSTA, adesso=t0)
    dopo = m.attuale(45.07, 7.69, scaricatore=rotto, adesso=t0 + datetime.timedelta(seconds=900))
    assert dopo["temperatura_c"] == 16.4 and "avviso" in dopo
