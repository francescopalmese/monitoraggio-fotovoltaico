"""
Calcoli per la dashboard: aggregazioni per giorno e per mese, serie di potenza
delle ultime ore, stato della batteria, produzione attesa e avvisi.

Sono solo funzioni "pure" su liste di letture (dizionari con le stesse colonne
della tabella `letture`, come li restituisce archivio.ultime): niente database,
niente rete, niente orologio nascosto. Così si provano con dati finti nei test.

Convenzioni:
- `ts` di ogni lettura è in UTC ISO (come lo scrive archivio.py). I giorni si
  raggruppano per DATA LOCALE (fuso del PC, oppure `tz` passato esplicitamente),
  perché i contatori "oggi" dell'inverter si azzerano alla mezzanotte locale
  (verificato il 16/10/2026: minuti_produzione_oggi = 1202 alle 20:05 locali,
  cioè il conteggio è partito alle 00:03).
- Il valore del giorno di un contatore "oggi" (energia prodotta, consumata,
  immessa, prelevata, carica e scarica batteria) è l'ULTIMA lettura del giorno,
  non il massimo: le prime letture dopo mezzanotte possono portare ancora il
  valore del giorno prima, finché l'inverter non azzera.
- autoconsumo = prodotta - immessa: energia prodotta non ceduta alla rete,
  compresa quella messa in batteria. autosufficienza = consumata - prelevata:
  consumo coperto senza la rete. Le percentuali dividono rispettivamente per
  la produzione e per il consumo.
"""
import datetime

UTC = datetime.timezone.utc

# nome usato nella dashboard -> colonna della tabella letture
CONTATORI_GIORNO = {
    "prodotta": "energia_prodotta_oggi",
    "consumata": "energia_consumata_oggi",
    "immessa": "energia_immessa_oggi",
    "prelevata": "energia_prelevata_oggi",
    "carica_batteria": "energia_carica_batteria_oggi",
    "scarica_batteria": "energia_scarica_batteria_oggi",
}
SOMME_MESE = list(CONTATORI_GIORNO) + ["autoconsumo", "autosufficienza"]
LETTURE_AL_GIORNO = 24 * 60          # la raccolta gira una volta al minuto

# da registri.py (stato_inverter); testi in italiano per la pagina
STATI_INVERTER = {
    0: "In attesa", 1: "Controllo", 2: "Connesso alla rete", 3: "EPS (isola)",
    4: "Guasto recuperabile", 5: "Guasto permanente", 6: "Aggiornamento",
    7: "Auto-carica", 8: "SVG", 9: "PID",
}


def in_locale(ts, tz=None):
    """Converte un timestamp ISO (UTC) in datetime nel fuso `tz` (None = fuso del PC)."""
    dt = datetime.datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def _ordinate(righe):
    return sorted(righe, key=lambda r: r["ts"])


def _nuovo_giorno(data):
    g = {"data": data, "n_letture": 0, "prima": None, "ultima": None,
         "picco_pv_w": 0.0, "max_media_oraria_w": 0.0,
         "soc_min": None, "soc_max": None, "_ore": {}}
    for nome in CONTATORI_GIORNO:
        g[nome] = None
    return g


def _derivati(g):
    """Aggiunge autoconsumo, autosufficienza e percentuali (None se mancano i contatori)."""
    p, i = g.get("prodotta"), g.get("immessa")
    c, pr = g.get("consumata"), g.get("prelevata")
    g["autoconsumo"] = round(max(0.0, p - i), 2) if p is not None and i is not None else None
    g["autosufficienza"] = round(max(0.0, c - pr), 2) if c is not None and pr is not None else None
    g["autoconsumo_pct"] = (round(100.0 * g["autoconsumo"] / p, 1)
                            if g["autoconsumo"] is not None and p > 0 else None)
    g["autosufficienza_pct"] = (round(100.0 * g["autosufficienza"] / c, 1)
                                if g["autosufficienza"] is not None and c > 0 else None)
    return g


def aggrega_giorni(righe, tz=None):
    """Una voce per giorno locale, in ordine di data. Vedi le convenzioni in cima al file."""
    per_giorno = {}
    for r in _ordinate(righe):
        dt = in_locale(r["ts"], tz)
        data = dt.date().isoformat()
        g = per_giorno.get(data)
        if g is None:
            g = per_giorno[data] = _nuovo_giorno(data)
        g["n_letture"] += 1
        ora = dt.strftime("%H:%M")
        if g["prima"] is None:
            g["prima"] = ora
        g["ultima"] = ora
        for nome, colonna in CONTATORI_GIORNO.items():
            v = r.get(colonna)
            if v is not None:
                g[nome] = round(float(v), 2)
        pv = r.get("pv_potenza_totale")
        if pv is not None:
            pv = float(pv)
            g["picco_pv_w"] = max(g["picco_pv_w"], pv)
            somma, n = g["_ore"].get(dt.hour, (0.0, 0))
            g["_ore"][dt.hour] = (somma + pv, n + 1)
        soc = r.get("batteria_soc")
        if soc is not None:
            g["soc_min"] = soc if g["soc_min"] is None else min(g["soc_min"], soc)
            g["soc_max"] = soc if g["soc_max"] is None else max(g["soc_max"], soc)

    giorni = []
    for data in sorted(per_giorno):
        g = per_giorno[data]
        ore = g.pop("_ore")
        if ore:
            g["max_media_oraria_w"] = round(max(s / n for s, n in ore.values()), 1)
        g["copertura"] = round(min(1.0, g["n_letture"] / LETTURE_AL_GIORNO), 3)
        giorni.append(_derivati(g))
    return giorni


def aggrega_mesi(giorni):
    """Somma dei giorni per mese ("YYYY-MM"), con il numero di giorni che hanno dati."""
    per_mese = {}
    for g in giorni:
        mese = g["data"][:7]
        m = per_mese.get(mese)
        if m is None:
            m = per_mese[mese] = {"mese": mese, "giorni_con_dati": 0}
            for nome in SOMME_MESE:
                m[nome] = 0.0
        m["giorni_con_dati"] += 1
        for nome in SOMME_MESE:
            if g.get(nome) is not None:
                m[nome] = round(m[nome] + g[nome], 2)
    mesi = []
    for mese in sorted(per_mese):
        m = per_mese[mese]
        m["autoconsumo_pct"] = (round(100.0 * m["autoconsumo"] / m["prodotta"], 1)
                                if m["prodotta"] > 0 else None)
        m["autosufficienza_pct"] = (round(100.0 * m["autosufficienza"] / m["consumata"], 1)
                                    if m["consumata"] > 0 else None)
        mesi.append(m)
    return mesi


def serie_potenza(righe, tz=None):
    """Punti per il grafico delle ultime ore: ora locale e potenze istantanee (W)."""
    punti = []
    for r in _ordinate(righe):
        dt = in_locale(r["ts"], tz)
        punti.append({
            "ts": r["ts"], "ora": dt.strftime("%H:%M"),
            "pv_w": r.get("pv_potenza_totale"),
            "carico_w": r.get("potenza_carico"),
            "rete_w": r.get("potenza_rete"),
            "batteria_w": r.get("batteria_potenza"),
            "soc": r.get("batteria_soc"),
        })
    return punti


def stato_batteria(ultima, soglia_w=50):
    """Stato della batteria dall'ultima lettura. Sotto `soglia_w` (rumore) la batteria è 'ferma'."""
    if ultima is None:
        return None
    p = ultima.get("batteria_potenza")
    if p is None:
        verso = "sconosciuto"
    elif p > soglia_w:
        verso = "in carica"
    elif p < -soglia_w:
        verso = "in scarica"
    else:
        verso = "ferma"
    return {
        "soc": ultima.get("batteria_soc"), "soh": ultima.get("batteria_soh"),
        "cicli": ultima.get("batteria_cicli"), "tensione_v": ultima.get("batteria_tensione"),
        "temperatura_c": ultima.get("batteria_temperatura"), "potenza_w": p, "verso": verso,
    }


def attesa_giorno(mensili, data):
    """Produzione attesa (kWh) per il giorno `data` ("YYYY-MM-DD"): la media giornaliera
    PVGIS del suo mese (E_d). `mensili` è {mese 1..12: {"E_d": ..., "E_m": ...}}."""
    if not mensili:
        return None
    voce = mensili.get(int(data[5:7]))
    return voce["E_d"] if voce else None


def attesa_mese(mensili, mese, giorni_trascorsi=None):
    """Produzione attesa (kWh) per il mese "YYYY-MM": E_m per un mese intero, oppure
    E_d per i giorni trascorsi se il mese è ancora in corso."""
    if not mensili:
        return None
    voce = mensili.get(int(mese[5:7]))
    if not voce:
        return None
    if giorni_trascorsi is None:
        return voce["E_m"]
    return round(voce["E_d"] * giorni_trascorsi, 2)


def avvisi(ultima_ts, adesso, giorni=(), mensili=None, kwp=None, stato_inverter=None, tz=None,
           minuti_max=10, frazione_min=0.5, frazione_sole=0.5, ora_valutazione_oggi=18,
           copertura_min=0.8):
    """
    Avvisi semplici. `adesso` è un datetime con fuso. Restituisce una lista di
    {"livello": "critico"|"attenzione", "codice": ..., "testo": ...}.

    - nessuna_lettura: l'ultima lettura è più vecchia di `minuti_max` minuti.
    - inverter_guasto: stato 4 (guasto recuperabile) o 5 (guasto permanente).
    - produzione_bassa: in un giorno "di sole" la produzione è sotto `frazione_min`
      dell'attesa PVGIS. Non c'è un sensore di irraggiamento: il giorno conta come
      di sole se la media oraria massima della potenza FV supera `frazione_sole`
      dei kWp (una media oraria, non il picco istantaneo, per non scambiare una
      schiarita per una giornata limpida). Si valuta per ieri e, dalle
      `ora_valutazione_oggi` in poi, per oggi; si salta un giorno con troppe
      letture mancanti (`copertura_min`), perché il totale sarebbe parziale.
    """
    lista = []
    if ultima_ts is None:
        lista.append({"livello": "critico", "codice": "nessun_dato",
                      "testo": "Nessuna lettura nel database: la raccolta non è mai partita?"})
    else:
        ritardo = (adesso - in_locale(ultima_ts, UTC)).total_seconds() / 60
        if ritardo > minuti_max:
            ora = in_locale(ultima_ts, tz).strftime("%d/%m %H:%M")
            lista.append({"livello": "critico", "codice": "nessuna_lettura",
                          "testo": f"Nessuna lettura da {int(ritardo)} minuti (ultima il {ora}): "
                                   "controllare l'attività pianificata, la chiavetta o la rete"})
    if stato_inverter in (4, 5):
        lista.append({"livello": "critico", "codice": "inverter_guasto",
                      "testo": f"Inverter in stato \"{STATI_INVERTER[stato_inverter]}\" "
                               f"(codice {stato_inverter})"})

    adesso_loc = adesso.astimezone(tz)
    oggi = adesso_loc.date()
    ieri = oggi - datetime.timedelta(days=1)
    for g in giorni:
        data = datetime.date.fromisoformat(g["data"])
        if data == oggi:
            if adesso_loc.hour < ora_valutazione_oggi:
                continue
            minuti_trascorsi = adesso_loc.hour * 60 + adesso_loc.minute
            copertura = g["n_letture"] / max(1, minuti_trascorsi)
        elif data == ieri:
            copertura = g["copertura"]
        else:
            continue
        attesa = attesa_giorno(mensili, g["data"])
        if attesa is None or not kwp or g.get("prodotta") is None or copertura < copertura_min:
            continue
        sole = g["max_media_oraria_w"] >= frazione_sole * kwp * 1000
        if sole and g["prodotta"] < frazione_min * attesa:
            lista.append({"livello": "attenzione", "codice": "produzione_bassa",
                          "testo": f"Produzione del {data:%d/%m}: {g['prodotta']:.1f} kWh, molto sotto "
                                   f"l'attesa PVGIS di {attesa:.1f} kWh nonostante il sole forte "
                                   f"(media oraria massima {g['max_media_oraria_w']:.0f} W)"})
    return lista
