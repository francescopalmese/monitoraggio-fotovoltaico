"""
Meteo attuale nella posizione dell'impianto, da Open-Meteo.

Fonte: API pubblica Open-Meteo (https://open-meteo.com/en/docs), endpoint
/v1/forecast, senza chiave; i codici del tempo sono quelli WMO che l'API stessa
documenta. Si chiede la condizione attuale (temperatura, codice, nuvolosità,
vento) e il riepilogo di oggi (massima, minima, alba, tramonto).

La posizione è la stessa di PVGIS (PVGIS_LAT, PVGIS_LON nel .env) e viene
inviata a Open-Meteo: chi non vuole può lasciare PVGIS non configurato o avviare
la dashboard con --no-pvgis, che spegne anche il meteo.

La risposta resta in memoria per ETA_MAX secondi (la pagina si aggiorna ogni
minuto, non serve richiedere il meteo ogni volta). Se la rete fallisce, si
restituisce l'ultimo meteo buono se esiste, altrimenti un dizionario con "errore".
"""
import datetime
import json
import urllib.parse
import urllib.request

ETA_MAX = 600   # secondi

# codice WMO -> (descrizione, simbolo). Solo i codici che Open-Meteo documenta.
CODICI = {
    0: ("sereno", "☀"), 1: ("quasi sereno", "🌤"), 2: ("parzialmente nuvoloso", "⛅"), 3: ("coperto", "☁"),
    45: ("nebbia", "🌫"), 48: ("nebbia con brina", "🌫"),
    51: ("pioviggine debole", "🌦"), 53: ("pioviggine", "🌦"), 55: ("pioviggine fitta", "🌧"),
    56: ("pioviggine gelata", "🌧"), 57: ("pioviggine gelata fitta", "🌧"),
    61: ("pioggia debole", "🌧"), 63: ("pioggia", "🌧"), 65: ("pioggia forte", "🌧"),
    66: ("pioggia gelata", "🌧"), 67: ("pioggia gelata forte", "🌧"),
    71: ("neve debole", "🌨"), 73: ("neve", "🌨"), 75: ("neve forte", "🌨"), 77: ("granuli di neve", "🌨"),
    80: ("rovesci deboli", "🌦"), 81: ("rovesci", "🌧"), 82: ("rovesci violenti", "⛈"),
    85: ("rovesci di neve", "🌨"), 86: ("rovesci di neve forti", "🌨"),
    95: ("temporale", "⛈"), 96: ("temporale con grandine", "⛈"), 99: ("temporale con grandine forte", "⛈"),
}


def costruisci_url(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,cloud_cover,wind_speed_10m,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code",
        "timezone": "auto", "forecast_days": 1,
    })
    return "https://api.open-meteo.com/v1/forecast?" + q


def scarica(lat, lon, timeout=10):
    with urllib.request.urlopen(costruisci_url(lat, lon), timeout=timeout) as risposta:
        return json.loads(risposta.read().decode("utf-8"))


def estrai(risposta):
    """Dalla risposta di Open-Meteo al dizionario che la pagina mostra."""
    c = risposta.get("current") or {}
    d = risposta.get("daily") or {}
    primo = lambda chiave: (d.get(chiave) or [None])[0]   # noqa: E731
    codice = c.get("weather_code")
    descrizione, simbolo = CODICI.get(codice, ("tempo sconosciuto", "•"))
    if codice in (0, 1) and c.get("is_day") == 0:
        simbolo = "🌙"
    return {
        "temperatura_c": c.get("temperature_2m"),
        "codice": codice, "descrizione": descrizione, "simbolo": simbolo,
        "nuvole_pct": c.get("cloud_cover"), "vento_kmh": c.get("wind_speed_10m"),
        "giorno": c.get("is_day") == 1,
        "t_max_c": primo("temperature_2m_max"), "t_min_c": primo("temperature_2m_min"),
        "alba": (primo("sunrise") or "")[11:16], "tramonto": (primo("sunset") or "")[11:16],
        "codice_giorno": primo("weather_code"),
        "ora": (c.get("time") or "")[11:16],
    }


class Meteo:
    """Cache in memoria del meteo attuale."""

    def __init__(self, eta_max=ETA_MAX):
        self.eta_max = eta_max
        self._dati = None
        self._quando = None
        self._posizione = None

    def attuale(self, lat, lon, scaricatore=scarica, adesso=None):
        adesso = adesso or datetime.datetime.now(datetime.timezone.utc)
        posizione = (round(float(lat), 3), round(float(lon), 3))
        fresco = (self._dati is not None and self._posizione == posizione and self._quando is not None
                  and (adesso - self._quando).total_seconds() < self.eta_max)
        if fresco:
            return self._dati
        try:
            self._dati = estrai(scaricatore(lat, lon))
            self._dati["scaricato"] = adesso.isoformat(timespec="seconds")
            self._quando, self._posizione = adesso, posizione
            return self._dati
        except Exception as errore:     # noqa: BLE001 - il meteo non deve mai rompere la pagina
            if self._dati is not None and self._posizione == posizione:
                vecchio = dict(self._dati)
                vecchio["avviso"] = f"meteo non aggiornato: {type(errore).__name__}"
                return vecchio
            return {"errore": f"{type(errore).__name__}: {errore}"}
