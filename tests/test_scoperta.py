"""
Test della scoperta automatica della chiavetta e della raccolta che la usa.
La parte di rete usa solo l'indirizzo locale 127.0.0.1 con un finto logger
Solarman che risponde al messaggio di scoperta.
"""
import socket
import threading

import pytest

import raccolta
import scoperta


# ---------- analisi della risposta ----------

def test_analizza_risposta():
    assert scoperta.analizza(b"192.168.1.23,AA:BB:CC:DD:EE:FF,1234567890") == ("192.168.1.23", "1234567890")
    assert scoperta.analizza(b"192.168.1.23,AA:BB:CC:DD:EE:FF,1234567890\r\n") == ("192.168.1.23", "1234567890")
    assert scoperta.analizza(b"ciao") is None                       # non è una risposta di scoperta
    assert scoperta.analizza(b"non-un-ip,mac,1234") is None
    assert scoperta.analizza(b"1.2.3.4,mac,ABC") is None               # seriale non numerico


# ---------- finto logger che risponde su 127.0.0.1 ----------

class LoggerFinto:
    def __init__(self, seriale="1234567890"):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.porta = self.sock.getsockname()[1]
        self.seriale = seriale
        self.ricevuti = []
        self.sock.settimeout(0.2)
        self.vivo = True
        self.thread = threading.Thread(target=self._servi, daemon=True)
        self.thread.start()

    def _servi(self):
        while self.vivo:
            try:
                dati, mittente = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            self.ricevuti.append(dati)
            if dati == scoperta.MESSAGGIO:
                self.sock.sendto(f"127.0.0.1,AA:BB:CC:DD:EE:FF,{self.seriale}".encode(), mittente)

    def chiudi(self):
        self.vivo = False
        self.thread.join(timeout=1)
        self.sock.close()


@pytest.fixture
def logger_finto():
    l = LoggerFinto()
    yield l
    l.chiudi()


def test_interroga_e_trova_con_logger_finto(logger_finto):
    trovati = scoperta.interroga(destinazioni=("127.0.0.1",), locale="127.0.0.1", attesa=0.5, giri=1,
                                 porta=logger_finto.porta)
    assert trovati == {"127.0.0.1": "1234567890"}
    assert logger_finto.ricevuti == [scoperta.MESSAGGIO]
    assert scoperta.trova("1234567890", destinazioni=("127.0.0.1",), attesa=0.5, porta=logger_finto.porta) == "127.0.0.1"
    assert scoperta.trova("0000000000", destinazioni=("127.0.0.1",), attesa=0.5, porta=logger_finto.porta) is None


def test_nessuna_risposta():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    porta_libera = s.getsockname()[1]
    s.close()
    assert scoperta.interroga(destinazioni=("127.0.0.1",), locale="127.0.0.1", attesa=0.3, giri=1,
                              porta=porta_libera) == {}


# ---------- raccolta: indirizzi noti, poi scoperta ----------

class Finti:
    """Lettura finta che risponde solo a certi indirizzi; scoperta finta con un risultato fisso."""
    def __init__(self, funzionanti, trovato=None):
        self.funzionanti = set(funzionanti)
        self.trovato = trovato
        self.letti = []
        self.scoperte = 0

    def leggi(self, con, ip, seriale, slave_id):
        self.letti.append(ip)
        if ip not in self.funzionanti:
            raise OSError("No socket available")
        return {"pv_potenza_totale": 1}

    def trova(self, seriale, ip_indizio=None):
        self.scoperte += 1
        return self.trovato


@pytest.fixture
def cache(tmp_path, monkeypatch):
    percorso = tmp_path / ".chiavetta_ip"
    monkeypatch.setattr(raccolta, "CACHE_IP", percorso)
    return percorso


def test_indirizzo_configurato_funziona_senza_scoperta(cache):
    f = Finti(funzionanti={"10.0.0.5"})
    assert raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f.leggi, trova=f.trova)
    assert f.letti == ["10.0.0.5"] and f.scoperte == 0
    assert not cache.exists()


def test_indirizzo_cambiato_viene_scoperto_e_ricordato(cache):
    f = Finti(funzionanti={"10.0.0.9"}, trovato="10.0.0.9")
    assert raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f.leggi, trova=f.trova)
    assert f.letti == ["10.0.0.5", "10.0.0.9"] and f.scoperte == 1
    assert cache.read_text().strip() == "10.0.0.9"
    # la volta dopo si prova prima l'indirizzo ricordato, senza scoperta
    f2 = Finti(funzionanti={"10.0.0.9"})
    raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f2.leggi, trova=f2.trova)
    assert f2.letti == ["10.0.0.9"] and f2.scoperte == 0


def test_cache_vecchia_poi_indirizzo_configurato(cache):
    cache.write_text("10.0.0.9\n")
    f = Finti(funzionanti={"10.0.0.5"})
    raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f.leggi, trova=f.trova)
    assert f.letti == ["10.0.0.9", "10.0.0.5"] and f.scoperte == 0


def test_errore_chiaro_se_non_si_trova(cache):
    f = Finti(funzionanti=set(), trovato=None)
    with pytest.raises(RuntimeError, match="LED NET"):
        raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f.leggi, trova=f.trova)
    f = Finti(funzionanti=set(), trovato="10.0.0.5")          # in rete ma la porta non risponde
    with pytest.raises(RuntimeError, match="stesso indirizzo"):
        raccolta.lettura_con_scoperta(None, "10.0.0.5", "123", 1, leggi=f.leggi, trova=f.trova)
    assert not cache.exists()
