"""
Lettura dei registri dell'inverter attraverso un "client" Modbus.

Il client può essere quello vero (pysolarmanv5, che parla con la chiavetta) o
uno finto nei test: basta che abbia un metodo
    read_holding_registers(register_addr=..., quantity=...) -> lista di interi.
Separare la lettura dal client permette di testare tutto senza inverter.
"""
import time

from registri import BLOCCHI, decodifica


class LettoreInverter:
    def __init__(self, client, pausa=0.3, tentativi=3, pausa_errore=1.0):
        self.client = client
        self.pausa = pausa                  # secondi tra una richiesta e l'altra
        self.tentativi = tentativi          # tentativi per blocco prima di arrendersi
        self.pausa_errore = pausa_errore    # attesa dopo una risposta sbagliata
        self.errori_recuperati = 0          # quante volte un nuovo tentativo ha salvato la lettura

    def _leggi_blocco(self, inizio, quanti):
        """Una richiesta Modbus con nuovi tentativi: la chiavetta ogni tanto
        risponde con un frame corrotto (errore CRC) o incompleto."""
        ultimo_errore = None
        for tentativo in range(1, self.tentativi + 1):
            try:
                grezzi = self.client.read_holding_registers(register_addr=inizio, quantity=quanti)
                if len(grezzi) != quanti:
                    raise ValueError(f"attesi {quanti} registri, ricevuti {len(grezzi)}")
                if tentativo > 1:
                    self.errori_recuperati += 1
                return grezzi
            except Exception as errore:          # noqa: BLE001 - qualunque errore di lettura
                ultimo_errore = errore
                if tentativo < self.tentativi and self.pausa_errore:
                    time.sleep(self.pausa_errore)
        raise RuntimeError(f"blocco 0x{inizio:04X}: {self.tentativi} tentativi falliti, ultimo errore: {ultimo_errore}")

    def leggi_tutto(self):
        """Legge tutti i blocchi di registri e restituisce {nome: valore}."""
        valori = {}
        for i, (inizio, quanti) in enumerate(BLOCCHI):
            grezzi = self._leggi_blocco(inizio, quanti)
            for nome, valore, _unita in decodifica(inizio, grezzi):
                valori[nome] = valore
            if self.pausa and i < len(BLOCCHI) - 1:
                time.sleep(self.pausa)
        return valori


def crea_client_reale(ip, seriale, slave_id=1, timeout=20):
    """Client vero verso la chiavetta (porta 8899, protocollo Solarman V5)."""
    from pysolarmanv5 import PySolarmanV5   # importato qui: nei test non serve
    return PySolarmanV5(ip, int(seriale), port=8899, mb_slave_id=slave_id,
                        socket_timeout=timeout, verbose=False)
