# HTTP-Honeypot

[English version](HONEYPOT.en.md)

## Eigenständiger Betrieb

Der Python-Honeypot ist ein separates Teilprojekt unter `honeypot/`. INM2 funktioniert auch ohne ihn. Die normale `docker-compose.yml` startet den Honeypot nicht.

Konfiguration und Start:

```sh
cd honeypot
cp .env.example .env
# Hostname, Traefik-Netzwerk, EntryPoints und Zertifikatsresolver anpassen
docker compose up -d --build
```

Das externe Docker-Netzwerk muss bereits existieren und mit Traefik verbunden sein. HTTP wird auf HTTPS umgeleitet; HTTPS wird von Traefik terminiert. Der Honeypot veröffentlicht keinen Host-Port. Zum Beenden:

```sh
docker compose down
```

Das Install-Script bietet im Hauptmenü den Punkt „Honeypot konfigurieren“ und schreibt `honeypot/.env`. Dort lässt sich der Honeypot aktivieren oder deaktivieren (`HONEYPOT_ENABLED`). Ist er deaktiviert, blendet INM2 Honeypot-Menüpunkt, Statistikdaten und Statushinweis aus. Ist er aktiviert und nicht gestartet, erscheint ein Warnhinweis im Dashboard und unter System.

## Erfasste Daten und Import

Der Honeypot schreibt pro Request eine JSON-Zeile nach `logs/honeypot.jsonl`. POST-Bodies werden vollständig bis zu einer Grenze von 10 MiB pro Request gespeichert, einschließlich übermittelter Login-Felder. Bodies bis 64 KiB werden in der JSONL-Zeile abgelegt. Größere Bodies und Uploads liegen als einzelne Dateien in `logs/honeypot-bodies/`; die JSONL-Zeile verweist auf die Datei. Bei Überschreitung der Erfassungsgrenze wird der gespeicherte Body gekürzt und als gekürzt markiert. Das Portal enthält eine fingierte Datei- und Backup-Verwaltung, die Uploads von Archiven, PHP-Dateien, Konfigurationen und Skripten annimmt. Der öffentliche Endpunkt `/files/upload` zeigt ein Formular und akzeptiert Uploads ohne Anmeldung; Aufruf und Übertragung werden protokolliert. Uploads werden ausschließlich als Honeypot-Daten abgelegt und protokolliert; sie werden niemals geöffnet oder ausgeführt. Hochgeladene Dateien erscheinen in der Dateiliste mit einer öffentlichen Website-Pfad und einem normalen „Open“-Link. Aufrufe hochgeladener PHP-Dateien werden als Requests erfasst und liefern eine simulierte Portalantwort; der Dateiinhalt wird nicht ausgeführt.

Der Collector importiert die Ereignisse beim nächsten regulären Import in die Tabelle `honeypot_event`. Er sperrt die gemeinsame Logdatei während der Übernahme und kürzt sie erst nach erfolgreichem Datenbank-Commit. Dadurch bleibt die Datei klein und ein unterbrochener Import kann ohne Duplikate wiederholt werden. Die großen Body-Dateien bleiben für die Detailansicht verfügbar.

Die INM2-Seite „Honeypot“ zeigt Requests und Bodies. Sie wird nur angezeigt, solange der Honeypot eine Statusdatei für einen erfolgreich gebundenen HTTP-Port hinterlegt. Wenn der Dienst nicht gestartet wurde, weist das Dashboard und der Systembereich darauf hin, dass die separate Konfiguration fehlt oder ein Startfehler vorliegt.

## Köderverhalten

Die Hauptseite imitiert den kleinen Fußballverein SV Eichenwacht mit einem Vereinsbüro, automatisch berechneten kommenden Trainingsterminen, einem durchsuchbaren Mitgliederregister mit Beitrags- und Mannschaftsangaben sowie einem schwarzen Brett. Mitgliederbereich, Webmaster-Dateiverwaltung und Terminal sind Teil der Köderoberfläche.

Das Terminal bildet typische Linux-Abläufe nach: Navigation, Dateiansicht und -suche, PHP- und Systeminformationen, Umgebungsvariablen sowie einfache Dateioperationen. Grundlegende Pipes, Befehlsverkettungen und Umleitungen arbeiten ausschließlich mit simulierten Ausgaben und einem sitzungsgebundenen virtuellen Dateisystem. Es startet keine Betriebssystembefehle, führt keinen PHP-Code aus und greift weder auf echte Netzwerkdienste noch auf Host-Dateien zu. Eingaben werden als Honeypot-Requests protokolliert; nicht unterstützte Befehle erhalten normale Shell-Fehlermeldungen.

Der Dienst imitiert außerdem häufig gesuchte Login-Seiten, WordPress, phpMyAdmin, API-Endpunkte und ausgewählte Abfragen sensibler Dateien. Er verbindet sich mit keinem echten Backend und liefert keine Host-Dateien aus. Unbekannte Pfade erhalten eine 404-Antwort. Die Antworten sind statische, regelbasierte Imitationen und belegen keinen erfolgreichen Exploit.
