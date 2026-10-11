# Internet Noise Monitor

## Container

Der InternetNoiseMonitor2 setzt sich aus drei Docker-Conteinern zusammen:

### 1. Collector

- Der Collector liest eine TRAFIK Konfiturationsdatei und schreibt die Requests in eine SQLite-Datenbank. 
- Entwickelt wird der Collector in Phyton oder PHP 
- Die Aufgaben beschränken sich auf das Auslesen der Daten, die Verwaltung der Datenbank und die Anpassung der eingelesenen Log-Dateien.
- Bei Bedarf werden vorab schon Zusammenfassungen der Daten in gesonderte Tabellen geschrieben.
- Burst-Erkennung
- Der Collector soll in regelmäßigen konfigurierbaren Abständen die (Traefik-) Logdatei bearbeiten
- Der Collector bearbeitet während oder nach dem Import die importieren Daten


### 2. API

- Der API-Container ist die Schnittstelle des UI-Containers und dem Collector-Container
- Hier werden nur APIs exponiert, sodass die UI keine Datenbankaktionen tätigen muss 
- Die API wird in Phyton oder PHP entwickelt
- REST/JSON
- nur Datenzugriff und ggf. einfache Aggregationen
- Kann Wartung durchführen


### 3. Frontend

- Entwickelt in TypeScript
- React
- vollständig clientseitige Oberfläche
- Tabellen/Filter/Charts möglichst im Browser

## Collector Spezifikation

### Funktion

Per Zeitseuerung werden die Logdateien gelesen und verarbeitet. Die Logdateien werden in der Umgebunsvariablen LOG_FILES definiert, wobei die einzelnen Dateinamen incl. Pfade mit Semikolon getrennt werden.   
Die Umgebungsvariable INPUT_INTERVAL_SECONDS gibt die Zeit in Sekunden an, bis ein neuer Durchlauf gestartet wird.  
Die Datei wird Zeile für Zeile importiert, bis der Sicherheitsabstand zum Dateiende erreicht wird. Der Sicherheitsabstand wird mit der Umgebungsvariable INPUT_SAVE_MARGIN_CHARACTERS in Zeichen angegeben.  
  Nach dem Import werden die gelesenen Zeichen aus der Datei entfernt, um einen erneuten Import der Daten zu verhindern.  
Danach können die Daten weiter verarbeitet und aufbereitet werden

Eine zweite Zeitsteuerung entfernt Akteure (IP Adressen) sowie alle daran hängenden Requests aus der Datenbank, die eine bestimmte Zeit nicht mehr aktiv waren.  
Die Umgebungsvariable MAINTENANCE_INTERVAL_DAYS gibt die Zeit in Tagen an, an denen die Wartung läuft. Die Umgebungsvariable MAINTENANCE_INACTIVE_DAYS gibt die Zeit in Tagen an, die ein Aktuer nicht mehr aktiv gewesen sein muss, um gelöscht zu werden.

Die traefik-log Datei besteht aus Zeilen mit folgendem Format:
{"ClientAddr":"198.235.24.11:64452","ClientHost":"198.235.24.11","ClientPort":"64452","ClientUsername":"-","DownstreamContentSize":19,"DownstreamStatus":404,"Duration":75795,"GzipRatio":0,"OriginContentSize":0,"OriginDuration":0,"OriginStatus":0,"Overhead":75795,"RequestAddr":"77.3.80.130:443","RequestContentSize":0,"RequestCount":556965,"RequestHost":"77.3.80.130","RequestMethod":"GET","RequestPath":"/","RequestPort":"443","RequestProtocol":"HTTP/1.1","RequestScheme":"https","RetryAttempts":0,"StartLocal":"2026-10-01T17:27:23.57807806Z","StartUTC":"2026-10-01T17:27:23.57807806Z","TLSCipher":"TLS_CHACHA20_POLY1305_SHA256","TLSVersion":"1.3","entryPointName":"websecure","level":"info","msg":"","request_User-Agent":"Hello from Palo Alto Networks, find out more about our scans in https://docs-cortex.paloaltonetworks.com/r/1/Cortex-Xpanse/Scanning-activity","time":"2026-10-01T17:27:23Z"}


Statuswerte:
    - letzter Import:  Datum/Uhrseit
    - Aktivität: Idle/Import/Maintenance
    - Import_Datei: gerade bearbeitete Datei, nur bei Aktiviät = Import
    - Import_Zahl: Importierte Zeilen, aktuelle Zeilenzahl beim Import sonst die zuletzt importierte Zeilenzahl
    - Alle Umgebungsvariablen


Vorberechnungen und Caching von Daten:

## API

/api/v1/requests                GET   liefert alle Requests in einem Zeitraum
                                      (ggf. für einen Akteur, host, etc.)
/api/v1/requests/{id}           GET   liefert einen Request mit Akteur, Host und Kategorien

/api/v1/actors                  GET   liefert alle Akteure in einem Zeitraum (ggf. nur neue)
/api/v1/actors/{id}             GET   liefert einen Akteur mit Geo-Daten sowie Request- und     
                                      Burstanzahl

/api/v1/bursts                  GET   liefert Zusammenfassung und paginierte Bursts im Zeitraum;
                                      Textfilter: actor, host, country, provider, asn, city; Kennzahlen: Akteure/Bursts, Bursts pro Akteur (Durchschnitt/Median/Maximum), Requests pro Burst (Durchschnitt/Median/Maximum), Burst-Dauer (Durchschnitt/Median/Maximum), Requestarten
/api/v1/bursts/{id}             GET   liefert die Daten eines Bursts
/api/v1/burst_requests/{id}     GET   liefert die Burstdaten und alle zugehörigen Requests

/api/v1/request_counts          GET   liefert lesende, schreibende und andere Requests in gleich  
                                      breite Zeitbalken; Filter: from, to, bars, host, actor/IP oder actor_id, category
/api/v1/categories              GET   liefert Zugriffe pro Kategorie im Zeitraum, getrennt nach 
                                      lesend/schreibend/sonstige sowie HTTP/HTTPS/sonstigem Scheme; optionaler Teiltrefferfilter category
/api/v1/hosts                   GET   liefert Zugriffe pro Host im Zeitraum, getrennt nach 
                                      lesend/schreibend/sonstige sowie HTTP/HTTPS/sonstigem Scheme; optionaler Teiltrefferfilter host
/api/v1/maintenance             PUT   stößt manuell die Wartungsarbeiten an
/api/v1/import                  PUT   stößt manuell einen Import an
/api/v1/status                  GET   gibt Statusparameter des Collectors zurück
/api/v1/params                  GET   group_name erforderlich; mit name einzelner Eintrag, 
                                      ohne name alle Einträge der Gruppe
/api/v1/params                  PUT   group_name und name erforderlich; value setzt/aktualisiert,
                                      bei fehlendem value wird der Eintrag gelöscht
/api/v1/params                  PUT   schreibt einen oder mehrere Parameter


## Frontend

Das Frontent steuert komplett das Aussehen der Anwendung.

## Datenbank


ACTOR
    actor_id    int
    ip          str
    first_time  datetime
    last_time   datetime
    provider    str
    asn         str
    city        str
    country     str


REQUEST
    request_id  int (PK)
    actor_id    int (FK)
    host_id     int (FK)
    ... siehe oben: JSON 
    

REQUEST_CATEGORY
    request_id    int (PK, FK)
    category_id   int (PK, FK)


HOST
    host_id     int (PK)
    name        str
    known       bool


BURST
    actor_id    int (PK FK)
    host_id     int (PK FK)
    start_time  datetime (IDX)
    end_time    datetime (IDX)
    avg_count   double
    read_count  int
    write_count int
    other_count int


BURST_CATEGORY
    actor_id    int (PK FK)
    request_id  int (PK FK)
    cateory_id  int (PK FK)


CATEGRORY
    category_id     int (PK)
    category_name   str


SETTINGS
    group_name  str (PK IDX)
    name        str (PK)
    value       str
