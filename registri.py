"""
Mappa dei registri Modbus usati dal progetto.
Inverter: ZCS Azzurro 3PH HYD10000 ZSS (ibrido trifase).

FONTE della mappa: profilo "sofar_g3hyd.yaml" dell'integrazione Home Assistant
ha-solarman (https://github.com/davidrapan/ha-solarman, licenza MIT), che cita a
sua volta il documento "SOFAR Modbus Protocol English G3 V1.22 (only 3PH)" e
dichiara: "Also works w/ rebranded ZCS Azzurro 3-Phase inverters such as the
3PH HYD6000 ZSS". La mappa va CONFERMATA con quella ufficiale ZCS richiesta via
ticket (vedi PIANO.md). Letto il 16/10/2026.

FONTE del protocollo di trasporto: ZCS, "Communication with ZCS devices" rev. 00
(03/07/2025): con la chiavetta ZSM-WIFI-USB si parla all'inverter in Modbus TCP
sulla porta 8899 (protocollo Solarman V5, libreria pysolarmanv5), funzione 0x03
per leggere e 0x10 per scrivere. In questo progetto si usa SOLO la lettura.

Convenzioni usate qui:
- indirizzo slave Modbus 1 (la guida ZCS alla chiavetta chiede "Indirizzo
  Modbus = 01" sul display dell'inverter);
- tipo "u16": un registro senza segno; "s16": un registro con segno
  (complemento a due); "u32": due registri consecutivi, parola alta
  all'indirizzo più basso; "ascii": N registri, due caratteri per registro;
- valore reale = valore grezzo * scala;
- SEGNI: per potenza di rete e di batteria il profilo HA inverte il segno per
  le sue convenzioni. Qui si tiene il valore grezzo del protocollo e il
  significato del segno (immissione/prelievo, carica/scarica) si annota nella
  nota del registro solo dopo averlo verificato con l'app.
"""

# nome -> definizione. "n" è il numero di registri (1 per u16/s16, 2 per u32).
REGISTRI = {
    # --- Stato e temperature (gruppo "Device" del profilo) ---
    "stato_inverter": dict(indirizzo=0x0404, n=1, tipo="u16", scala=1, unita="",
        note="0 Waiting, 1 Detection, 2 On-grid, 3 EPS, 4 Recoverable fault, "
             "5 Permanent fault, 6 Upgrade, 7 Self-charging, 8 SVG, 9 PID"),
    "temperatura_ambiente": dict(indirizzo=0x0418, n=1, tipo="s16", scala=1, unita="°C"),
    "temperatura_radiatore": dict(indirizzo=0x041A, n=1, tipo="s16", scala=1, unita="°C"),
    "temperatura_modulo": dict(indirizzo=0x0420, n=1, tipo="s16", scala=1, unita="°C"),
    "minuti_produzione_oggi": dict(indirizzo=0x0426, n=1, tipo="u16", scala=1, unita="min"),

    # --- Informazioni (gruppo "Info") ---
    "seriale_inverter": dict(indirizzo=0x0445, n=8, tipo="ascii", scala=1, unita="",
        note="serve solo a confermare che si sta parlando con l'inverter giusto"),

    # --- Rete e carico (gruppo "Grid") ---
    "frequenza_rete": dict(indirizzo=0x0484, n=1, tipo="u16", scala=0.01, unita="Hz"),
    "potenza_rete": dict(indirizzo=0x0488, n=1, tipo="s16", scala=10, unita="W",
        note="scambio al punto di connessione (contatore); segno verificato il 20/10/2026 con il "
             "bilancio delle potenze (PV a zero, batteria ferma, casa 2,6 kW -> rete -2,7 kW): "
             "positivo = immissione in rete, negativo = prelievo dalla rete"),
    "potenza_carico": dict(indirizzo=0x04AF, n=1, tipo="s16", scala=10, unita="W",
        note="consumo di casa"),

    # --- Fotovoltaico (gruppo "PV") ---
    "pv1_tensione": dict(indirizzo=0x0584, n=1, tipo="u16", scala=0.1, unita="V"),
    "pv1_corrente": dict(indirizzo=0x0585, n=1, tipo="u16", scala=0.01, unita="A"),
    "pv1_potenza": dict(indirizzo=0x0586, n=1, tipo="u16", scala=10, unita="W"),
    "pv2_potenza": dict(indirizzo=0x0589, n=1, tipo="u16", scala=10, unita="W"),
    "pv_potenza_totale": dict(indirizzo=0x05C4, n=1, tipo="u16", scala=100, unita="W"),

    # --- Batteria (gruppo "Battery") ---
    "batteria_tensione": dict(indirizzo=0x0604, n=1, tipo="u16", scala=0.1, unita="V"),
    "batteria_corrente": dict(indirizzo=0x0605, n=1, tipo="s16", scala=0.01, unita="A",
        note="negativo = scarica (stesso segno della potenza)"),
    "batteria_potenza": dict(indirizzo=0x0606, n=1, tipo="s16", scala=10, unita="W",
        note="segno verificato il 16/10/2026 con PV a zero e carico alimentato dalla batteria: negativo = scarica, positivo = carica"),
    "batteria_temperatura": dict(indirizzo=0x0607, n=1, tipo="s16", scala=1, unita="°C"),
    "batteria_soc": dict(indirizzo=0x0608, n=1, tipo="u16", scala=1, unita="%"),
    "batteria_soh": dict(indirizzo=0x0609, n=1, tipo="u16", scala=1, unita="%"),
    "batteria_cicli": dict(indirizzo=0x060A, n=1, tipo="u16", scala=1, unita="cicli"),

    # --- Energie (gruppo "Energy"), "oggi" in 0.01 kWh, "totale" in 0.1 kWh ---
    "energia_prodotta_oggi": dict(indirizzo=0x0684, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_prodotta_totale": dict(indirizzo=0x0686, n=2, tipo="u32", scala=0.1, unita="kWh"),
    "energia_consumata_oggi": dict(indirizzo=0x0688, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_prelevata_oggi": dict(indirizzo=0x068C, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_prelevata_totale": dict(indirizzo=0x068E, n=2, tipo="u32", scala=0.1, unita="kWh"),
    "energia_immessa_oggi": dict(indirizzo=0x0690, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_immessa_totale": dict(indirizzo=0x0692, n=2, tipo="u32", scala=0.1, unita="kWh"),
    "energia_carica_batteria_oggi": dict(indirizzo=0x0694, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_carica_batteria_totale": dict(indirizzo=0x0696, n=2, tipo="u32", scala=0.1, unita="kWh"),
    "energia_scarica_batteria_oggi": dict(indirizzo=0x0698, n=2, tipo="u32", scala=0.01, unita="kWh"),
    "energia_scarica_batteria_totale": dict(indirizzo=0x069A, n=2, tipo="u32", scala=0.1, unita="kWh"),
}

# Blocchi contigui da leggere con una sola richiesta ciascuno (inizio, quanti).
# Tenerli piccoli: meno traffico per la chiavetta, che sta anche inviando al cloud.
BLOCCHI = [
    (0x0404, 1),    # stato
    (0x0418, 9),    # temperature 0x0418..0x0420
    (0x0426, 1),    # minuti di produzione
    (0x0445, 8),    # seriale
    (0x0484, 44),   # rete: 0x0484..0x04AF
    (0x0584, 6),    # PV1/PV2
    (0x05C4, 1),    # PV totale
    (0x0604, 7),    # batteria
    (0x0684, 24),   # energie 0x0684..0x069B
]


def _s16(v):
    """Converte un registro a 16 bit in intero con segno (complemento a due)."""
    return v - 0x10000 if v >= 0x8000 else v


def decodifica(inizio, grezzi):
    """
    Dato un blocco letto a partire da `inizio` (lista di interi a 16 bit),
    restituisce [(nome, valore, unita)] per tutti i registri della mappa
    che cadono interamente dentro il blocco.
    """
    fine = inizio + len(grezzi)
    risultati = []
    for nome, d in REGISTRI.items():
        a, n = d["indirizzo"], d["n"]
        if a < inizio or a + n > fine:
            continue
        parole = grezzi[a - inizio: a - inizio + n]
        if d["tipo"] == "u16":
            valore = parole[0]
        elif d["tipo"] == "s16":
            valore = _s16(parole[0])
        elif d["tipo"] == "u32":
            valore = (parole[0] << 16) | parole[1]       # parola alta prima
        elif d["tipo"] == "ascii":
            valore = "".join(chr(w >> 8) + chr(w & 0xFF) for w in parole).strip("\x00 ")
        else:
            raise ValueError(f"tipo sconosciuto: {d['tipo']}")
        if d["tipo"] != "ascii":
            valore = valore * d["scala"]
            if isinstance(valore, float):
                valore = round(valore, 3)
        risultati.append((nome, valore, d["unita"]))
    return risultati
