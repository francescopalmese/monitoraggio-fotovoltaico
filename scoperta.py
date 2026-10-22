"""
Scoperta automatica della chiavetta (logger Solarman) sulla rete di casa.

I logger Solarman rispondono a un pacchetto UDP di broadcast sulla porta 48899
che contiene il testo "WIFIKIT-214028-READ"; la risposta è una riga di testo
"indirizzo IP,MAC,seriale".
FONTE: integrazione Home Assistant ha-solarman (davidrapan, licenza MIT), file
custom_components/solarman/discovery.py, che usa proprio questo messaggio e
questa porta. Verificato in pratica il 17/10/2026: la chiavetta ha risposto con
il suo seriale, a un indirizzo diverso da quello del giorno prima.

Perché serve: il router assegna gli indirizzi con il DHCP e può cambiarli; il
16/10/2026 sera è successo e la raccolta è rimasta ferma 15 ore con l'errore
"No socket available". La soluzione definitiva è riservare un indirizzo fisso
alla chiavetta nel router; questo modulo è la rete di sicurezza.

Solo lettura: si manda un pacchetto e si ascolta la risposta. Nessun indirizzo
viene stampato o registrato nel log da chi usa queste funzioni.
"""
import socket
import time

MESSAGGIO = b"WIFIKIT-214028-READ"
PORTA = 48899


def analizza(dati):
    """Dalla risposta "ip,mac,seriale" restituisce (ip, seriale), o None se non ha quella forma."""
    parti = dati.decode("ascii", errors="replace").strip().split(",")
    if len(parti) < 3:
        return None
    ip, seriale = parti[0].strip(), parti[2].strip()
    if ip.count(".") != 3 or not seriale.isdigit():
        return None
    return ip, seriale


def ip_locale_verso(ip_indizio):
    """L'indirizzo di questo PC sulla scheda di rete che porta verso `ip_indizio`.
    Non manda nulla: serve a scegliere la scheda giusta quando ce n'è più d'una
    (per esempio quelle virtuali di WSL o VirtualBox)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip_indizio, PORTA))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def interroga(destinazioni=("255.255.255.255",), locale=None, attesa=2.0, giri=2, porta=PORTA):
    """Manda il messaggio di scoperta e raccoglie le risposte: {ip: seriale}."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((locale or "", 0))
    s.settimeout(0.5)
    trovati = {}
    try:
        for _ in range(giri):
            for dest in destinazioni:
                try:
                    s.sendto(MESSAGGIO, (dest, porta))
                except OSError:
                    continue
            fine = time.monotonic() + attesa
            while time.monotonic() < fine:
                try:
                    dati, _mittente = s.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    # Windows segnala qui (ConnectionResetError) la "porta irraggiungibile"
                    # di un destinatario che non ascolta: non è una risposta, si va avanti
                    time.sleep(0.1)
                    continue
                esito = analizza(dati)
                if esito:
                    trovati[esito[0]] = esito[1]
            if trovati:
                break
    finally:
        s.close()
    return trovati


def trova(seriale, ip_indizio=None, attesa=2.0, porta=PORTA, destinazioni=None):
    """Indirizzo IP della chiavetta con quel seriale, oppure None.
    `ip_indizio` (l'ultimo indirizzo noto) serve a scegliere la scheda di rete e
    a mandare il pacchetto anche al broadcast della sua sottorete (si assume /24,
    la rete di casa tipica), oltre a quello generale."""
    locale = ip_locale_verso(ip_indizio) if ip_indizio else None
    if destinazioni is None:
        destinazioni = ["255.255.255.255"]
        if locale:
            destinazioni.insert(0, ".".join(locale.split(".")[:3]) + ".255")
    seriale = str(seriale).strip()
    for ip, sn in interroga(destinazioni, locale, attesa, porta=porta).items():
        if sn == seriale:
            return ip
    return None
