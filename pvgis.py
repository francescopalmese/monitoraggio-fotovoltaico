"""
Produzione attesa dall'API pubblica PVGIS v5.3 (Joint Research Centre della
Commissione Europea).

FONTE: https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/api-non-interactive-service_en
Endpoint usato: https://re.jrc.ec.europa.eu/api/v5_3/PVcalc (strumento PVcalc:
rendimento medio mensile di un impianto fisso connesso alla rete).
Parametri: lat, lon in gradi decimali; peakpower in kWp; loss in % (perdite di
sistema, PVGIS propone 14); angle = inclinazione dei moduli dall'orizzontale in
gradi (0 = piatti), oppure optimalinclination=1 per farla scegliere a PVGIS;
aspect = orientamento (0 = sud, 90 = ovest, -90 = est); outputformat=json.
Risposta (verificata il 16/10/2026 con una posizione di prova): outputs.monthly.fixed
è una lista di 12 voci {month, E_d, E_m, H(i)_d, H(i)_m, SD_m}: E_d = produzione
media giornaliera (kWh), E_m = produzione media mensile (kWh), H(i)_d e H(i)_m =
irraggiamento medio sul piano dei moduli (kWh/m²); inputs.meteo_data indica il
database di radiazione (es. PVGIS-SARAH3) e gli anni usati (es. 2005-2023).
Limite dichiarato: 30 richieste al secondo per IP. Qui la risposta si tiene in
una cache su file e si richiede di nuovo solo dopo MAX_ETA_GIORNI giorni o se
cambiano i parametri. La cache contiene la posizione: è esclusa da git.

Nessuna credenziale: l'API è pubblica e senza registrazione.
"""
import datetime
import json
import pathlib
import urllib.parse
import urllib.request

ENDPOINT = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
MAX_ETA_GIORNI = 30
PERDITE_DEFAULT = 14.0


def parametri_da_env(env):
    """
    Parametri dell'impianto dalle variabili d'ambiente (file .env):
    PVGIS_LAT, PVGIS_LON, IMPIANTO_KWP obbligatori; PVGIS_INCLINAZIONE (vuoto =
    lascia scegliere a PVGIS), PVGIS_ORIENTAMENTO (default 0 = sud),
    PVGIS_PERDITE (default 14). None se manca un obbligatorio.
    """
    def numero(nome, default=None):
        v = (env.get(nome) or "").strip().replace(",", ".")
        return float(v) if v else default

    lat, lon, kwp = numero("PVGIS_LAT"), numero("PVGIS_LON"), numero("IMPIANTO_KWP")
    if lat is None or lon is None or kwp is None:
        return None
    return {"lat": lat, "lon": lon, "peakpower": kwp,
            "loss": numero("PVGIS_PERDITE", PERDITE_DEFAULT),
            "angle": numero("PVGIS_INCLINAZIONE"),
            "aspect": numero("PVGIS_ORIENTAMENTO", 0.0)}


def costruisci_url(p):
    q = {"lat": p["lat"], "lon": p["lon"], "peakpower": p["peakpower"],
         "loss": p.get("loss", PERDITE_DEFAULT), "aspect": p.get("aspect", 0.0)}
    if p.get("angle") is None:
        q["optimalinclination"] = 1
    else:
        q["angle"] = p["angle"]
    q["outputformat"] = "json"
    return ENDPOINT + "?" + urllib.parse.urlencode(q)


def scarica(p, timeout=30):
    """Una richiesta HTTP a PVGIS; restituisce il JSON della risposta."""
    with urllib.request.urlopen(costruisci_url(p), timeout=timeout) as risposta:
        return json.load(risposta)


def estrai_mensili(risposta):
    """{mese 1..12: {"E_d", "E_m", "H_d", "H_m"}} dalla risposta PVcalc."""
    mensili = {}
    for voce in risposta["outputs"]["monthly"]["fixed"]:
        mensili[int(voce["month"])] = {
            "E_d": float(voce["E_d"]), "E_m": float(voce["E_m"]),
            "H_d": float(voce.get("H(i)_d", 0.0)), "H_m": float(voce.get("H(i)_m", 0.0)),
        }
    if sorted(mensili) != list(range(1, 13)):
        raise ValueError(f"PVGIS: attesi 12 mesi, ricevuti {sorted(mensili)}")
    return mensili


def info_fonte(risposta):
    """Dati di contesto da mostrare in pagina. Volutamente SENZA la posizione."""
    inputs = risposta.get("inputs", {})
    meteo = inputs.get("meteo_data", {})
    fisso = inputs.get("mounting_system", {}).get("fixed", {})
    modulo = inputs.get("pv_module", {})
    totali = risposta.get("outputs", {}).get("totals", {}).get("fixed", {})
    return {
        "database": meteo.get("radiation_db"),
        "anni": f"{meteo.get('year_min')}-{meteo.get('year_max')}",
        "inclinazione": fisso.get("slope", {}).get("value"),
        "inclinazione_ottimizzata": bool(fisso.get("slope", {}).get("optimal")),
        "orientamento": fisso.get("azimuth", {}).get("value"),
        "kwp": modulo.get("peak_power"),
        "perdite": modulo.get("system_loss"),
        "annuale_kwh": totali.get("E_y"),
    }


def _esito(cache, avviso=None):
    info = info_fonte(cache["risposta"])
    info["scaricato"] = cache["scaricato"][:10]
    if avviso:
        info["avviso"] = avviso
    return estrai_mensili(cache["risposta"]), info


def carica(p, percorso_cache, scaricatore=scarica, max_eta_giorni=MAX_ETA_GIORNI, adesso=None):
    """
    Restituisce (mensili, info). Usa la cache su file se ha gli stessi parametri ed
    è più giovane di `max_eta_giorni`; altrimenti scarica e la riscrive. Se lo
    scaricamento fallisce ma esiste una cache (anche vecchia) con gli stessi
    parametri, la usa e lo dice in info["avviso"]. Se non c'è niente: (None, {"errore"}).
    """
    adesso = adesso or datetime.datetime.now(datetime.timezone.utc)
    percorso = pathlib.Path(percorso_cache)
    cache = None
    if percorso.exists():
        try:
            cache = json.loads(percorso.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            cache = None
    if cache and cache.get("parametri") == p:
        scaricato = datetime.datetime.fromisoformat(cache["scaricato"])
        if (adesso - scaricato).days < max_eta_giorni:
            return _esito(cache)
    try:
        risposta = scaricatore(p)
        estrai_mensili(risposta)                  # controlla che la risposta sia completa
        nuova = {"parametri": p, "scaricato": adesso.isoformat(timespec="seconds"),
                 "risposta": risposta}
        percorso.write_text(json.dumps(nuova), encoding="utf-8")
        return _esito(nuova)
    except Exception as errore:                   # noqa: BLE001 - rete, JSON, disco: si va avanti
        if cache and cache.get("parametri") == p:
            return _esito(cache, avviso=f"PVGIS non raggiungibile ({errore}); "
                                        f"uso i dati scaricati il {cache['scaricato'][:10]}")
        return None, {"errore": f"PVGIS non disponibile: {errore}"}
