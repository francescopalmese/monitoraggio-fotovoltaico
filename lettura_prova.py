"""
Prima lettura di prova dall'inverter, in SOLA LETTURA.

Cosa fa: si collega alla chiavetta Wi-Fi (porta 8899, protocollo Solarman V5)
con la libreria pysolarmanv5, legge i blocchi di registri definiti in
registri.py con la funzione Modbus 0x03 e stampa i valori decodificati.
Non scrive nulla sull'inverter.

Prima di lanciarlo: copiare .env.example in .env e compilare LOGGER_IP
(indirizzo della chiavetta sulla rete di casa) e LOGGER_SERIAL (seriale
della chiavetta, 10 cifre sull'etichetta).

Uso:  python lettura_prova.py
"""
import os
import sys
import time

from dotenv import load_dotenv
from pysolarmanv5 import PySolarmanV5

from registri import BLOCCHI, decodifica


def main():
    load_dotenv()
    ip = os.getenv("LOGGER_IP", "").strip()
    seriale = os.getenv("LOGGER_SERIAL", "").strip()
    slave_id = int(os.getenv("MODBUS_SLAVE_ID", "1"))
    if not ip or not seriale.isdigit():
        print("Compila LOGGER_IP e LOGGER_SERIAL nel file .env (vedi .env.example).")
        sys.exit(1)

    # Il seriale va passato come numero intero (documentazione pysolarmanv5).
    modbus = PySolarmanV5(ip, int(seriale), port=8899, mb_slave_id=slave_id,
                          socket_timeout=20, verbose=False)
    print(f"Collegato alla chiavetta {ip}:8899, slave Modbus {slave_id}\n")
    try:
        for inizio, quanti in BLOCCHI:
            t0 = time.time()
            grezzi = modbus.read_holding_registers(register_addr=inizio, quantity=quanti)
            durata = time.time() - t0
            print(f"--- blocco 0x{inizio:04X} ({quanti} registri, {durata:.2f} s) ---")
            for nome, valore, unita in decodifica(inizio, grezzi):
                print(f"  {nome:34s} {valore} {unita}")
            time.sleep(0.5)   # una pausa tra le richieste, per non stressare la chiavetta
    finally:
        modbus.disconnect()


if __name__ == "__main__":
    main()
