# Cowrie-SSH-Honeypot für Linux-Server

Dieses Compose-Projekt betreibt Cowrie in einem Container und veröffentlicht
SSH auf TCP-Port 2222 des Servers.

## Voraussetzungen

- Linux-Server mit installiertem Docker Engine und Docker Compose Plugin
- Für den Container verfügbarer TCP-Port 2222
- Eingehende TCP-Verbindungen zum Server, direkt oder über eine Router- bzw.
  Firewall-Weiterleitung
- Schreibbarer Speicherplatz für `../../cowrie-data/var`

Der Host-Port 2222 muss frei sein. Bei einer NAT- oder Firewall-Weiterleitung
kann ein anderer öffentlicher Port auf TCP 2222 des Servers zeigen. Falls auf
demselben Server ein echter SSH-Dienst betrieben wird, sind dessen Port und
Erreichbarkeit getrennt zu konfigurieren. Eine Weiterleitung darf nicht
versehentlich den echten SSH-Dienst öffentlich erreichbar machen.

## Start und Kontrolle

Im Verzeichnis dieser Compose-Datei:

```sh
docker compose up -d
docker compose logs -f cowrie
```

Der Honeypot ist über TCP-Port 2222 erreichbar:

```sh
ssh -p 2222 root@SERVER_ADRESSE
```

Der Zugriff sollte von einem externen Netzwerk geprüft werden. Die lokale
Server-Firewall sowie gegebenenfalls vorgeschaltete Router- und Cloud-Firewall-
Regeln müssen eingehende Verbindungen zum veröffentlichten Port erlauben.

## Verhalten und Datenspeicherung

Cowrie ist ein nachgebildeter SSH-Honeypot und kein Proxy zum Server. Der
Container erhält keine Host-Verzeichnisse oder Docker-Sockets. Die Compose-
Konfiguration entfernt Linux-Capabilities, deaktiviert SSH-Tunneling und
begrenzt die von Docker erfassten stdout/stderr-Logs. Cowrie zeigt einen
Debian-12-artigen Host `web01` samt passendem SSH-Banner. Das Verzeichnis `var/`
bleibt unter `cowrie-data/var` erhalten; dazu gehören Ereignisprotokolle,
Sitzungsmitschnitte, Downloads und generierte SSH-Hostkeys. Erfasste Dateien
sind als nicht vertrauenswürdig zu behandeln; Cowrie führt sie nicht aus.

Erfolgreiche Passwort-Logins sind auf die Köder-Zugangsdaten in `userdb.txt`
beschränkt. Für `root` sind 20 häufig geleakte oder öffentlich bekannte
schwache Passwörter eingetragen; alle anderen Benutzer-/Passwort-Kombinationen
werden abgewiesen. Die Datei kann angepasst werden; Änderungen werden nach
Neuerstellung des Containers wirksam. Es dürfen ausschließlich eigens für den
Honeypot bestimmte Zugangsdaten verwendet werden.
