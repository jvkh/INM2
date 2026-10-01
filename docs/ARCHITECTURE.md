# Internet Noise Monitor


## Container
Der InternetNoiseMonitor2 setzt sich aus drei Docker-Conteinern zusammen:

### 1. Collector

- Der Collector liest eine TRAFIK Konfiturationsdatei und schreibt die Requests in eine SQLite-Datenbank. 
- Entwickelt wird der Collector in Phyton
- Die Aufgaben beschränken sich auf das Auslesen der Daten, die Verwaltung der Datenbank und die Anpassung der eingelesenen Log-Dateien.
- Bei Bedarf werden vorab schon Zusammenfassungen der Daten in gesonderte Tabellen geschrieben.

### 2. API

- Der API-Container ist die Schnittstelle des UI-Containers und dem Collector-Container
- Hier werden nur APIs exponiert, sodass die UI keine Datenbankaktionen tätigen muss 
- Die API wird in Phyton entwickelt
- REST/JSON
- nur Datenzugriff und ggf. einfache Aggregationen

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

## API

## Frontend