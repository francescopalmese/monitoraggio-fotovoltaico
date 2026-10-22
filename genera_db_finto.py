"""
Crea un database FINTO con la stessa struttura di dati.db, per provare la
dashboard e i suoi avvisi senza inverter. Non tocca dati.db.

Uso:  python genera_db_finto.py percorso/finto.db [--giorni 30] [--fine 2026-10-16T18:00:00+00:00]
poi:  python dashboard.py --db percorso/finto.db --porta 8766 [--env file_di_prova.env]

Cosa contiene (una lettura al minuto, come la raccolta vera):
- giorni normali: produzione a campana dalle 7 alle 19, con giornate limpide
  (picco 7 kW) e nuvolose (picco 2,5 kW) alternate; casa tra 0,5 e 1,5 kW;
  batteria da 10 kWh che si carica di giorno e si scarica di sera;
- IERI: mattina limpida e poi produzione a zero dalle 11, come per un guasto:
  totale molto sotto l'attesa in una giornata di sole (avviso "produzione_bassa"
  se PVGIS è configurato per circa 10 kWp);
- l'ultima lettura è a --fine (default: 25 minuti fa, così scatta l'avviso
  "nessuna_lettura") e riporta stato inverter 4, guasto recuperabile (avviso
  "inverter_guasto").
"""
import argparse
import datetime
import math
import pathlib
import sys

import archivio

CAPACITA_KWH = 10.0
POTENZA_BATTERIA_MAX = 3000.0


def profilo_pv(ora, picco):
    """Potenza FV (W) a campana tra le 7 e le 19."""
    if ora < 7 or ora > 19:
        return 0.0
    return picco * math.sin(math.pi * (ora - 7) / 12)


def genera(percorso, giorni, fine_utc):
    tz = fine_utc.astimezone().tzinfo             # fuso del PC, come la dashboard
    fine = fine_utc.astimezone(tz)
    primo = fine.date() - datetime.timedelta(days=giorni - 1)
    ieri = fine.date() - datetime.timedelta(days=1)
    righe = []
    soc = 60.0
    tot_prod, tot_imm, tot_prel, tot_car, tot_sca = 52000.0, 22800.0, 14100.0, 15600.0, 13700.0
    for i in range(giorni):
        data = primo + datetime.timedelta(days=i)
        picco = 7000.0 if i % 2 == 0 else 2500.0
        if data == ieri:
            picco = 7000.0
        e = dict(prod=0.0, cons=0.0, imm=0.0, prel=0.0, car=0.0, sca=0.0)
        for minuto in range(24 * 60):
            dt = datetime.datetime.combine(data, datetime.time(0, 0), tzinfo=tz) + datetime.timedelta(minutes=minuto)
            if dt > fine:
                break
            ora = minuto / 60
            pv = profilo_pv(ora, picco)
            if data == ieri and ora >= 11:
                pv = 0.0                                  # "guasto" di ieri
            carico = 500.0 + (800.0 if 18 <= ora <= 23 else 0.0) + (300.0 if minuto % 7 == 0 else 0.0)
            surplus = pv - carico
            if surplus > 0 and soc < 100:
                batteria = min(surplus, POTENZA_BATTERIA_MAX)
            elif surplus < 0 and soc > 10:
                batteria = -min(-surplus, POTENZA_BATTERIA_MAX)
            else:
                batteria = 0.0
            rete = pv - carico - batteria                 # positivo = immissione (convenzione finta)
            soc = max(0.0, min(100.0, soc + batteria / 60 / 1000 / CAPACITA_KWH * 100))
            e["prod"] += pv / 60000; e["cons"] += carico / 60000
            e["imm"] += max(0.0, rete) / 60000; e["prel"] += max(0.0, -rete) / 60000
            e["car"] += max(0.0, batteria) / 60000; e["sca"] += max(0.0, -batteria) / 60000
            righe.append((
                dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
                2, 45, round(28 + pv / 500), round(28 + pv / 500), minuto, 50.0,
                round(rete, 0), round(carico, 0), 600.0, round(pv / 600 / 2, 2), round(pv / 2, 0), round(pv / 2, 0), round(pv, 0),
                round(348.0 + soc / 10, 1), round(batteria / 348, 2), round(batteria, 0), 35, round(soc, 0), 96, 831 + i // 3,
                round(e["prod"], 2), round(tot_prod + e["prod"], 1), round(e["cons"], 2), round(e["prel"], 2),
                round(tot_prel + e["prel"], 1), round(e["imm"], 2), round(tot_imm + e["imm"], 1),
                round(e["car"], 2), round(tot_car + e["car"], 1), round(e["sca"], 2), round(tot_sca + e["sca"], 1),
            ))
        tot_prod += e["prod"]; tot_imm += e["imm"]; tot_prel += e["prel"]; tot_car += e["car"]; tot_sca += e["sca"]

    ultima = list(righe[-1])
    ultima[1] = 4                                 # l'ultima lettura: stato 4, guasto recuperabile
    righe[-1] = tuple(ultima)

    percorso = pathlib.Path(percorso)
    if percorso.exists():
        percorso.unlink()
    con = archivio.apri(percorso)
    colonne = ["ts"] + archivio.COLONNE
    assert len(colonne) == len(righe[0]), (len(colonne), len(righe[0]))
    con.executemany(f'INSERT INTO letture ({", ".join(chr(34) + c + chr(34) for c in colonne)}) '
                    f'VALUES ({", ".join("?" for _ in colonne)})', righe)
    con.commit()
    con.close()
    return len(righe)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera un database finto per provare la dashboard.")
    parser.add_argument("percorso", help="file .db da creare (viene sovrascritto)")
    parser.add_argument("--giorni", type=int, default=30)
    parser.add_argument("--fine", default=None,
                        help="timestamp ISO dell'ultima lettura (default: 25 minuti fa)")
    args = parser.parse_args(argv)
    if args.fine:
        fine = datetime.datetime.fromisoformat(args.fine)
        if fine.tzinfo is None:
            fine = fine.astimezone()
    else:
        fine = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=25)
    n = genera(args.percorso, args.giorni, fine)
    print(f"scritte {n} letture finte in {args.percorso} (ultima: {fine.isoformat(timespec='seconds')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
