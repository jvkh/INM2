#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ENV_FILE="$ROOT_DIR/.env"
SETUP_CREATED_ENV=0
SETUP_COMPLETE=0
BOOTSTRAP_REQUIRED=0
BACKUP_CREATED=0
declare -A ENV_UPDATES=()
declare -A ENV_BASELINE=()
SCREEN_ACTIVE=0
SCREEN_SECTION=''
SCREEN_HELP=''
SCREEN_STATUS=''
LAST_NOTICE=''
BACKUP_NOTICE=''
LANGUAGE='de'
LANGUAGE_FILE="${XDG_CONFIG_HOME:-${HOME:-/tmp}/.config}/inm2/setup-language"

translate() {
  local text="$1"
  [[ "$LANGUAGE" == en ]] || { printf '%s' "$text"; return; }
  case "$text" in
    'INM2 Server-Setup') printf 'INM2 Server Setup' ;;
    'Hauptmenü') printf 'Main menu' ;;
    'Pflichtangaben und Einrichtung') printf 'Required settings and setup' ;;
    'Systemvoraussetzungen geprüft: Docker, Compose v2, Docker-Dienst und Projektdateien.') printf 'Requirements checked: Docker, Compose v2, Docker service, and project files.' ;;
    '  Weitere Menüpunkte erscheinen nach der Ersteinrichtung.') printf '  More menu items become available after initial setup.' ;;
    'Pflichtangaben und Logquelle prüfen/ändern') printf 'Review required settings and log source' ;;
    '  1  Pflichtangaben und Logquelle prüfen/ändern') printf '  1  Required settings and log source' ;;
    '  2  Ports') printf '  2  Ports' ;;
    '  3  Zugangssicherheit') printf '  3  Access security' ;;
    '  4  Burst- und Vorfallerkennung') printf '  4  Burst and incident detection' ;;
    '  5  Import, Wartung und optionale Daten') printf '  5  Import, maintenance, and optional data' ;;
    '  6  Admin-Passwort ändern') printf '  6  Change administrator password' ;;
    '  7  .env-Backupdateien löschen') printf '  7  Delete .env backup files' ;;
    'Pflichtangaben und Logquelle prüfen/ändern') printf 'Review/change required settings and log source' ;;
    '  1  Pflichtangaben und Logquelle prüfen/ändern') printf '  1  Review required settings and log source' ;;
    '  2  Ports') printf '  2  Ports' ;;
    '  3  Zugangssicherheit') printf '  3  Access security' ;;
    '  4  Burst- und Vorfallerkennung') printf '  4  Burst and incident detection' ;;
    '  5  Import, Wartung und optionale Daten') printf '  5  Import, maintenance, and optional data' ;;
    '  6  Admin-Passwort ändern') printf '  6  Change administrator password' ;;
    '  7  .env-Backupdateien löschen') printf '  7  Delete .env backup files' ;;
    '  0  Beenden') printf '  0  Exit' ;;
    'Ports') printf 'Ports' ;;
    'Zugangssicherheit') printf 'Access security' ;;
    'Burst- und Vorfallerkennung') printf 'Burst and incident detection' ;;
    'Import, Wartung und optionale Daten') printf 'Import, maintenance, and optional data' ;;
    'Admin-Passwort ändern') printf 'Change administrator password' ;;
    '.env-Backupdateien löschen') printf 'Delete .env backup files' ;;
    'Sprache / Language') printf 'Language: English' ;;
    'Beenden') printf 'Exit' ;;
    'Systemvoraussetzungen geprüft: Docker, Compose v2, Docker-Dienst und Projektdateien.') printf 'Requirements checked: Docker, Compose v2, Docker service, and project files.' ;;
    'Vorhandene .env gefunden. Änderungen werden gesichert.') printf 'Existing .env found. Changes will be backed up.' ;;
    'Noch keine .env vorhanden; die Pflichtangaben werden zuerst eingerichtet.') printf 'No .env file found; required settings must be configured first.' ;;
    'Weitere Menüpunkte erscheinen nach der Ersteinrichtung.') printf 'More menu items become available after initial setup.' ;;
    'Auswahl: ') printf 'Selection: ' ;;
    'Bitte eine angezeigte Menünummer wählen.') printf 'Select one of the displayed menu numbers.' ;;
    'Bitte zuerst die Pflichtangaben einrichten.') printf 'Configure the required settings first.' ;;
    'Server-Port der Weboberfläche') printf 'Web interface server port' ;;
    'Server-Port der API') printf 'API server port' ;;
    'Interner Collector-Steuerport') printf 'Internal collector control port' ;;
    'Vollständiger Hostpfad zur Access-Logdatei') printf 'Full host path to the access log file' ;;
    'Hostverzeichnis der GeoLite2-Datenbanken') printf 'Host directory for the GeoLite2 databases' ;;
    'Hostordner mit GeoLite2-City.mmdb und GeoLite2-ASN.mmdb; wird im Container schreibgeschützt unter /geoip eingebunden.') printf 'Host directory containing GeoLite2-City.mmdb and GeoLite2-ASN.mmdb; mounted read-only at /geoip in the container.' ;;
    'Host/Pfad-Präfixe beim Import überspringen') printf 'Skip host/path prefixes during import' ;;
    'Eigene Hostnamen als bekannt markieren') printf 'Mark host names as known' ;;
    'Importintervall (Sekunden)') printf 'Import interval (seconds)' ;;
    'Sicherheitspuffer am Logende (Zeichen)') printf 'Safety buffer at end of log (characters)' ;;
    'Wartungsintervall (Tage)') printf 'Maintenance interval (days)' ;;
    'Maximaler Request-Abstand im Burst (Sekunden)') printf 'Maximum request gap in a burst (seconds)' ;;
    'Mindestzahl Requests pro Burst') printf 'Minimum requests per burst' ;;
    'Burst-Zeitfenster (Sekunden)') printf 'Burst detection window (seconds)' ;;
    'Zeitfenster für langsame Scans (Sekunden; 10800 = 3 Stunden)') printf 'Slow scan window (seconds; 10800 = 3 hours)' ;;
    'Mindestens unterschiedliche passende Pfade (sensible oder mit HTTP-Fehler)') printf 'Minimum distinct matching paths (sensitive or HTTP error paths)' ;;
    'Mindestens verschiedene Hosts') printf 'Minimum distinct hosts' ;;
    'Diese Angaben braucht INM2 zwingend: eine Logdatei sowie ein Admin-Passwort und ein Sitzungsschlüssel. Der Sitzungsschlüssel wird sicher erzeugt; das Passwort wird nur als Hash gespeichert.') printf 'INM2 requires an access log, an administrator password, and a session secret. The session secret is generated securely; only a password hash is stored.' ;;
    'Der Logpfad darf kein Semikolon und keinen Doppelpunkt enthalten.') printf 'The log path cannot contain a semicolon or colon.' ;;
    'Logverzeichnis kann nicht angelegt werden: '*) printf '%s' "The log directory cannot be created: ${text#Logverzeichnis kann nicht angelegt werden: }" ;;
    'Logdatei noch nicht vorhanden: '*) printf '%s' "Log file not found yet: ${text#Logdatei noch nicht vorhanden: }" ;;
    'Logquelle ist keine reguläre Datei: '*) printf '%s' "Log source is not a regular file: ${text#Logquelle ist keine reguläre Datei: }" ;;
    'Sitzungsschlüssel konnte nicht erzeugt werden. OpenSSL oder /dev/urandom prüfen; anschließend erneut versuchen.') printf 'Could not generate the session secret. Check OpenSSL or /dev/urandom, then retry.' ;;
    'Logdatei gefunden. Zugriffsrechte und JSON-Format werden vom Collector beim Import geprüft.') printf 'Log file found. The collector checks access permissions and JSON format during import.' ;;
    'Logdatei ist leer. Sobald Traefik schreibt, kann der Collector sie einlesen.') printf 'Log file is empty. The collector can read it after Traefik writes to it.' ;;
    'Die Logdatei fehlt noch; der Collector kann starten, sobald Traefik sie anlegt.') printf 'The log file is not present yet; the collector can start after Traefik creates it.' ;;
    'Akteure nach wie vielen inaktiven Tagen bereinigen?') printf 'Remove actors after how many inactive days?' ;;
    'Der Sitzungsschlüssel fehlt. Bitte zuerst Pflichtangaben einrichten.') printf 'The session secret is missing. Configure the required settings first.' ;;
    'Bitte zuerst im Menüpunkt Pflichtangaben einen Sitzungsschlüssel einrichten.') printf 'Set up a session secret under Required settings first.' ;;
    'Admin-Passwort geändert. Damit es gilt: docker compose up -d api') printf 'Administrator password changed. Apply with: docker compose up -d api' ;;
    'Admin-Passwort-Hash wurde erstellt.') printf 'Administrator password hash created.' ;;
    'Backupdateien löschen') printf 'Delete backup files' ;;
    'Im Projektverzeichnis '*)
      text="${text/Im Projektverzeichnis /Project directory }"
      text="${text/ gibt es keine Dateien mit dem Muster / contains no files matching /}"
      text="${text/. Return: zurück zum Hauptmenü./. Press Return to return to the main menu.}"
      printf '%s' "$text" ;;
    'Mindestüberschneidung (Prozent)') printf 'Minimum overlap (percent)' ;;
    'Mindestens verstrichene Zeit (Sekunden; 300 = 5 Minuten)') printf 'Minimum elapsed time (seconds; 300 = 5 minutes)' ;;
    'Akteure nach wie vielen inaktiven Tagen bereinigen?') printf 'Remove actors after how many inactive days?' ;;
    'Wie oft der Collector neue Logzeilen verarbeitet.') printf 'How often the collector processes new log lines.' ;;
    'Zeichen am Dateiende, die ausgespart werden, damit keine unvollständige Logzeile importiert wird.') printf 'Characters skipped at the end of a file to avoid importing an incomplete log line.' ;;
    'Der Maximalabstand begrenzt die Lücke zwischen Requests; Mindestzahl und Zeitfenster qualifizieren eine Folge als Burst.') printf 'The maximum gap limits the time between requests; the minimum count and time window define a burst.' ;;
    'Ein Burst braucht mindestens diese Anzahl Requests innerhalb des Zeitfensters.') printf 'A burst requires at least this many requests within the time window.' ;;
    'Requests außerhalb dieses Zeitfensters zählen nicht zur Qualifizierung eines Bursts.') printf 'Requests outside this time window do not count toward a burst.' ;;
    'Zusammenführung: Kriterien desselben Akteurs werden verbunden, wenn mehr als dieser Anteil des kürzeren Zeitraums überlappt.') printf 'Merge criteria for the same actor when overlap exceeds this share of the shorter period.' ;;
    'In diesem rollierenden Fenster werden passende Pfad-Requests derselben Quell-IP ausgewertet.') printf 'Matching path requests from the same source IP are evaluated in this rolling window.' ;;
    'Gezählt werden unterschiedliche sensible Pfade oder Pfade mit HTTP-Fehlerantwort.') printf 'Distinct sensitive paths and paths with HTTP error responses are counted.' ;;
    'Die Pfade müssen mindestens über diese Anzahl verschiedener Hosts verteilt sein.') printf 'The paths must span at least this number of distinct hosts.' ;;
    'Erster bis letzter passender Request müssen mindestens so weit auseinanderliegen.') printf 'The first and last matching requests must be at least this far apart.' ;;
    'Import, Wartung und optionale Daten') printf 'Import, maintenance, and optional data' ;;
    'Die Logdatei muss einen vollständigen Dateipfad enthalten.') printf 'The log file must be specified using its full path.' ;;
    'Bitte einen Dateipfad mit Dateinamen angeben.') printf 'Enter a file path including the file name.' ;;
    'Der Logpfad darf kein Semikolon und keinen Doppelpunkt enthalten.') printf 'The log path cannot contain a semicolon or colon.' ;;
    'Keine Backupdateien gefunden') printf 'No backup files found' ;;
    'Backupdateien löschen') printf 'Delete backup files' ;;
    'Angezeigte Backupdateien endgültig löschen?') printf 'Permanently delete the listed backup files?' ;;
    'Return zum Fortfahren … ') printf 'Press Return to continue … ' ;;
    'Weboberfläche und API benötigen unterschiedliche Ports.') printf 'The web interface and API require different ports.' ;;
    'Ports müssen zwischen 1 und 65535 liegen.') printf 'Ports must be between 1 and 65535.' ;;
    Port\ *\ ist\ belegt.\ Bitte\ einen\ anderen\ Port\ wählen.) printf '%s' "${text/ ist belegt. Bitte einen anderen Port wählen./ is in use. Choose another port.}" ;;
    'Aktueller Wert: '*) printf 'Current value: %s' "${text#Aktueller Wert: }" ;;
    'Eingabe: ') printf 'Input: ' ;;
    'Aktueller Wert: %s') printf 'Current value: %s' ;;
    'Antwort: j oder n.') printf 'Enter y or n.' ;;
    'Antwort [j/N]: ') printf 'Answer [y/N]: ' ;;
    'Antwort [J/n]: ') printf 'Answer [Y/n]: ' ;;
    'Bitte mit j oder n antworten.') printf 'Enter y or n.' ;;
    'Enter behält den Wert bei; - leert ihn.') printf 'Enter keeps the current value; - clears it.' ;;
    'Einfache Anführungszeichen werden in diesem Wert nicht unterstützt.') printf 'Single quotes are not supported in this value.' ;;
    'Der Wert enthält ein ungültiges Steuerzeichen.') printf 'The value contains an invalid control character.' ;;
    'Bitte eine positive ganze Zahl eingeben.') printf 'Enter a positive whole number.' ;;
    'Bitte eine nicht-negative ganze Zahl eingeben.') printf 'Enter a non-negative whole number.' ;;
    'Neues Admin-Passwort') printf 'New administrator password' ;;
    'Passwort wiederholen') printf 'Repeat password' ;;
    'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar.') printf 'At least 12 characters. Input is hidden.' ;;
    'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar. Enter bricht die Passwortänderung ab.') printf 'At least 12 characters. Input is hidden. Enter cancels the password change.' ;;
    'Das Passwort darf nicht leer sein.') printf 'The password cannot be empty.' ;;
    'Die Passwörter stimmen nicht überein. Bitte erneut eingeben.') printf 'The passwords do not match. Enter them again.' ;;
    'Das Passwort muss mindestens 12 Zeichen lang sein.') printf 'The password must contain at least 12 characters.' ;;
    'Passwortänderung abgebrochen. Es wurden keine Änderungen vorgenommen.') printf 'Password change cancelled. No changes were made.' ;;
    'Änderungen gespeichert. Die übrigen .env-Einträge blieben erhalten. Übernehmen mit: docker compose up -d --build') printf 'Changes saved. Other .env entries were preserved. Apply with: docker compose up -d --build' ;;
    'Logdatei noch nicht vorhanden: %s. Sie muss vor dem Import von Traefik angelegt werden.') printf 'Log file not found yet: %s. Traefik must create it before import.' ;;
    'Logdatei gefunden. Zugriffsrechte und JSON-Format werden vom Collector beim Import geprüft.') printf 'Log file found. The collector checks access permissions and JSON format during import.' ;;
    'Logdatei ist leer. Sobald Traefik schreibt, kann der Collector sie einlesen.') printf 'Log file is empty. The collector can read it after Traefik writes to it.' ;;
    'Die Weboberfläche ist über den Server-Port erreichbar. Der API-Port ist aus Sicherheitsgründen nur lokal auf dem Server gebunden. Der Collector-Port ist ausschließlich im internen Docker-Netzwerk erreichbar.') printf 'The web interface is available on the server port. For security, the API port is bound locally only. The collector port is available only on the internal Docker network.' ;;
    'Bei HTTPS muss das sichere Sitzungscookie aktiv bleiben. TOTP verlangt beim Login zusätzlich zum Passwort einen zeitabhängigen Code aus einer Authenticator-App.') printf 'For HTTPS, the secure session cookie must remain enabled. TOTP requires a time-based code from an authenticator app in addition to the password.' ;;
    'Wird INM2 über HTTPS aufgerufen?') printf 'Is INM2 accessed over HTTPS?' ;;
    'Zweiten Faktor (TOTP) verlangen?') printf 'Require a second factor (TOTP)?' ;;
    'Authenticator-App einrichten') printf 'Set up authenticator app' ;;
    Schlüssel:\ *)
      text="${text/Schlüssel:/Secret:}"
      text="${text/Einrichtungs-URI:/Setup URI:}"
      text="${text/Bewahre den Schlüssel sicher auf./Store the secret securely.}"
      printf '%s' "$text" ;;
    'Schlüssel: %s') printf 'Secret: %s' ;;
    'Das Passwort wird im API-Container gehasht. Es wird nicht in der Konfiguration gespeichert.') printf 'The password is hashed inside the API container and is not stored in the configuration.' ;;
    'Passwort-Hash erzeugen') printf 'Generate password hash' ;;
    'API-Image vorbereiten') printf 'Prepare API image' ;;
    'Docker baut das API-Image. Die Ausgabe bleibt im Hintergrund, damit der Bildschirm stehen bleibt.') printf 'Docker builds the API image. Output runs in the background while this screen remains visible.' ;;
    'TOTP-Schlüssel erzeugen') printf 'Generate TOTP secret' ;;
    'Der Schlüssel wird sicher im API-Container erstellt.') printf 'The secret is generated securely inside the API container.' ;;
    'Die Weboberfläche ist über den Server-Port erreichbar. Der API-Port ist aus Sicherheitsgründen nur lokal auf dem Server gebunden. Der Collector-Port ist ausschließlich im internen Docker-Netzwerk erreichbar.') printf 'The web interface is available on the server port. The API port is bound to localhost only. The collector port is available only on the internal Docker network.' ;;
    'Bei HTTPS muss das sichere Sitzungscookie aktiv bleiben. TOTP verlangt beim Login zusätzlich zum Passwort einen zeitabhängigen Code aus einer Authenticator-App.') printf 'For HTTPS, the secure session cookie must remain enabled. TOTP requires a time-based authenticator code in addition to the password.' ;;
    'Wie oft der Collector neue Logzeilen verarbeitet.') printf 'How often the collector processes new log lines.' ;;
    'Sobald Traefik schreibt, kann der Collector sie einlesen.') printf 'The collector can read the file after Traefik writes to it.' ;;
    'Änderungen gespeichert. Die übrigen .env-Einträge blieben erhalten. Übernehmen mit: docker compose up -d --build') printf 'Changes saved. Other .env entries were preserved. Apply with: docker compose up -d --build' ;;
    'Löschen abgebrochen. Es wurden keine Backupdateien entfernt.') printf 'Deletion cancelled. No backup files were removed.' ;;
    'Return: zurück zum Hauptmenü.') printf 'Return: back to the main menu.' ;;
    'j') printf 'y' ;;
    'J/n') printf 'Y/n' ;;
    'j/N') printf 'y/N' ;;
    'INM2-Setup beendet.') printf 'INM2 setup finished.' ;;
    'Sprache geändert: Englisch.') printf 'Language changed to English.' ;;
    'Sprache geändert: Deutsch.') printf 'Language changed to German.' ;;
    'Spracheinstellung konnte nicht gespeichert werden; sie gilt nur für diesen Lauf.') printf 'Language preference could not be saved; it applies to this session only.' ;;
    *) printf '%s' "$text" ;;
  esac
}

screen_leave() {
  if (( SCREEN_ACTIVE )); then
    printf '\033[?25h\033[?1049l' > /dev/tty 2>/dev/null || true
    SCREEN_ACTIVE=0
  fi
}

cleanup_setup() {
  screen_leave
  if (( SETUP_CREATED_ENV == 1 && SETUP_COMPLETE == 0 )); then
    rm -f -- "$ENV_FILE"
    printf '\nSetup did not finish. The temporary .env was removed.\n' >&2
  fi
  rm -f -- "$ROOT_DIR"/.env.setup.*
}
trap cleanup_setup EXIT

fail() {
  screen_leave
  printf 'Fehler: %s\n' "$1" >&2
  exit 1
}

handle_input_eof() {
  screen_leave
  printf '\nEingabe beendet; Setup wird geschlossen.\n' >&2
  exit 0
}

require_command() {
  while ! command -v "$1" >/dev/null 2>&1; do
    wait_for_retry "Benötigtes Programm nicht gefunden: $1. Nach der Installation Eingabetaste zur erneuten Prüfung."
  done
}

toggle_language() {
  local _
  if [[ "$LANGUAGE" == de ]]; then LANGUAGE=en; LAST_NOTICE='Sprache geändert: Englisch.'
  else LANGUAGE=de; LAST_NOTICE='Sprache geändert: Deutsch.'
  fi
  if mkdir -p -- "${LANGUAGE_FILE%/*}" 2>/dev/null && printf '%s\n' "$LANGUAGE" > "$LANGUAGE_FILE" 2>/dev/null; then
    chmod 600 "$LANGUAGE_FILE" 2>/dev/null || true
  else
    LAST_NOTICE='Spracheinstellung konnte nicht gespeichert werden; sie gilt nur für diesen Lauf.'
  fi
}

check_compose() {
  while true; do
    if ! command -v docker >/dev/null 2>&1; then
      wait_for_retry 'Docker wurde nicht gefunden. Nach der Installation Eingabetaste zur erneuten Prüfung.'
      continue
    fi
    if ! docker compose version >/dev/null 2>&1; then
      wait_for_retry 'Docker Compose v2 ist nicht verfügbar. Nach der Installation Eingabetaste zur erneuten Prüfung.'
      continue
    fi
    if ! docker info >/dev/null 2>&1; then
      wait_for_retry 'Der Docker-Dienst ist nicht erreichbar oder der aktuelle Benutzer hat keinen Zugriff. Nach Behebung Eingabetaste zur erneuten Prüfung.'
      continue
    fi
    return 0
  done
}

check_writable_project() {
  while [[ ! -r "$ROOT_DIR/.env.example" || ! -w "$ROOT_DIR" ]]; do
    wait_for_retry "Projektdateien fehlen oder das Verzeichnis ist nicht beschreibbar: $ROOT_DIR. Nach Behebung Eingabetaste zur erneuten Prüfung."
  done
}

wait_for_retry() {
  local message="$1" _
  printf '\n%s\n' "$message" >&2
  if ! read -r -p 'Eingabetaste = erneut prüfen, Ctrl-C = Setup beenden: ' _ </dev/tty; then
    screen_leave
    exit 0
  fi
}

prompt_value() {
  local label="$1" default="$2" result
  while true; do
    render_prompt "$label" "$default"
    if ! read -r -p "$(translate 'Eingabe: ')" result </dev/tty; then handle_input_eof; fi
    result="${result:-$default}"
    if [[ "$result" == *"'"* ]]; then SCREEN_STATUS="Einfache Anführungszeichen werden in diesem Wert nicht unterstützt."; continue; fi
    if [[ "$result" == *$'\r'* ]]; then SCREEN_STATUS='Der Wert enthält ein ungültiges Steuerzeichen.'; continue; fi
    REPLY="$result"
    return 0
  done
}

prompt_optional() {
  local label="$1" default="$2" result
  while true; do
    render_prompt "$label" "$default" 'Enter behält den Wert bei; - leert ihn.'
    if ! read -r -p "$(translate 'Eingabe: ')" result </dev/tty; then handle_input_eof; fi
    if [[ -z "$result" ]]; then result="$default"; elif [[ "$result" == - ]]; then result=''; fi
    if [[ "$result" == *"'"* ]]; then SCREEN_STATUS="Einfache Anführungszeichen werden in diesem Wert nicht unterstützt."; continue; fi
    if [[ "$result" == *$'\r'* ]]; then SCREEN_STATUS='Der Wert enthält ein ungültiges Steuerzeichen.'; continue; fi
    REPLY="$result"
    return 0
  done
}

get_env_value() {
  local key="$1" fallback="$2" line value
  line="$(grep -m 1 "^${key}=" "$ENV_FILE" 2>/dev/null || true)"
  if [[ -z "$line" ]]; then REPLY="$fallback"; return; fi
  value="${line#*=}"
  if [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
    value="${value:1:${#value}-2}"
  fi
  REPLY="$value"
}

apply_env_updates() {
  local backup_file='' env_temp key update_keys=''
  if [[ ! -f "$ENV_FILE" ]]; then
    if ! cp -- "$ROOT_DIR/.env.example" "$ENV_FILE"; then
      LAST_NOTICE='Die .env-Datei konnte nicht angelegt werden. Schreibrechte im Projektverzeichnis prüfen.'
      return 1
    fi
    SETUP_CREATED_ENV=1
    if ! chmod 600 "$ENV_FILE"; then
      rm -f -- "$ENV_FILE"
      SETUP_CREATED_ENV=0
      LAST_NOTICE='Die .env-Datei konnte nicht geschützt werden. Schreibrechte im Projektverzeichnis prüfen.'
      return 1
    fi
    BACKUP_CREATED=1
  else
    if (( BACKUP_CREATED == 0 )); then
      if ! backup_file="$(mktemp "$ROOT_DIR/.env.backup.XXXXXX")" || ! cp -p -- "$ENV_FILE" "$backup_file" || ! chmod 600 "$backup_file"; then
        [[ -z "$backup_file" ]] || rm -f -- "$backup_file"
        LAST_NOTICE='Die vorhandene .env konnte nicht gesichert werden. Freien Speicherplatz und Schreibrechte prüfen.'
        return 1
      fi
      BACKUP_CREATED=1
      BACKUP_NOTICE="Sicherung der vorherigen .env: $backup_file"
    fi
  fi
  for key in "${!ENV_UPDATES[@]}"; do
    if [[ "${ENV_UPDATES[$key]}" == *"'"* || "${ENV_UPDATES[$key]}" == *$'\r'* || "${ENV_UPDATES[$key]}" == *$'\n'* ]]; then
      LAST_NOTICE="Der Wert für $key kann nicht sicher in .env geschrieben werden. Wert korrigieren und erneut speichern."
      return 1
    fi
    printf -v "$key" '%s' "${ENV_UPDATES[$key]}"
    export "$key"
    update_keys+=" $key"
  done
  export INM2_SETUP_UPDATE_KEYS="${update_keys# }"
  if ! env_temp="$(mktemp "$ROOT_DIR/.env.setup.XXXXXX")"; then
    LAST_NOTICE='Temporäre .env-Datei konnte nicht erstellt werden. Freien Speicherplatz und Schreibrechte prüfen.'
    return 1
  fi
  if ! awk '
    BEGIN {
      count = split(ENVIRON["INM2_SETUP_UPDATE_KEYS"], keys, " ")
      for (i = 1; i <= count; i++) pending[keys[i]] = 1
    }
    {
      separator = index($0, "=")
      key = separator ? substr($0, 1, separator - 1) : ""
      if (key in pending) {
        printf "%s=%c%s%c\n", key, 39, ENVIRON[key], 39
        delete pending[key]
      } else {
        print
      }
    }
    END {
      for (i = 1; i <= count; i++) {
        key = keys[i]
        if (key in pending) printf "%s=%c%s%c\n", key, 39, ENVIRON[key], 39
      }
    }
  ' "$ENV_FILE" > "$env_temp"; then
    rm -f -- "$env_temp"
    LAST_NOTICE='Die aktualisierte .env-Datei konnte nicht vorbereitet werden.'
    return 1
  fi
  if ! chmod 600 "$env_temp" || ! mv -f -- "$env_temp" "$ENV_FILE"; then
    rm -f -- "$env_temp"
    LAST_NOTICE='Die aktualisierte .env-Datei konnte nicht gespeichert werden. Speicherplatz und Schreibrechte prüfen.'
    return 1
  fi
  ENV_UPDATES=()
}

prompt_yes_no() {
  local label="$1" default="$2" answer prompt_default
  if [[ "$default" == true ]]; then prompt_default='J/n'; else prompt_default='j/N'; fi
  while true; do
    render_prompt "$label" "$prompt_default" 'Antwort: j oder n.'
    if ! read -r -p "$(translate "Antwort [$prompt_default]: ")" answer </dev/tty; then handle_input_eof; fi
    answer="${answer,,}"
    if [[ -z "$answer" ]]; then REPLY="$default"; return; fi
    case "$answer" in
      j|ja|y|yes) REPLY=true; return ;;
      n|nein|no) REPLY=false; return ;;
      *) SCREEN_STATUS='Bitte mit j oder n antworten.' ;;
    esac
  done
}

section() {
  SCREEN_SECTION="$1"
  SCREEN_HELP=''
  SCREEN_STATUS=''
}

explain() {
  SCREEN_HELP="$1"
}

prompt_positive_integer() {
  local label="$1" default="$2" value
  while true; do
    prompt_value "$label" "$default"
    value="$REPLY"
    if [[ "$value" =~ ^[0-9]{1,18}$ ]] && (( 10#$value > 0 )); then REPLY="$value"; SCREEN_STATUS=''; return; fi
    SCREEN_STATUS='Bitte eine positive ganze Zahl eingeben.'
  done
}

prompt_nonnegative_integer() {
  local label="$1" default="$2" value
  while true; do
    prompt_value "$label" "$default"
    value="$REPLY"
    if [[ "$value" =~ ^[0-9]{1,18}$ ]] && (( 10#$value >= 0 )); then REPLY="$value"; SCREEN_STATUS=''; return; fi
    SCREEN_STATUS='Bitte eine nicht-negative ganze Zahl eingeben.'
  done
}

read_password_pair() {
  local allow_cancel="${1:-0}" first second
  PASSWORD_CANCELLED=0
  while true; do
    if (( allow_cancel )); then
      render_prompt 'Neues Admin-Passwort' '' 'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar. Enter bricht die Passwortänderung ab.'
      if ! IFS= read -r -s -p 'Neues Admin-Passwort (Enter = Abbrechen): ' first </dev/tty; then handle_input_eof; fi
    else
      render_prompt 'Neues Admin-Passwort' '' 'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar.'
      if ! IFS= read -r -s -p 'Neues Admin-Passwort (mindestens 12 Zeichen): ' first </dev/tty; then handle_input_eof; fi
    fi
    printf '\n' > /dev/tty
    if [[ -z "$first" ]] && (( allow_cancel )); then
      PASSWORD_CANCELLED=1
      unset PASSWORD_VALUE PASSWORD_CONFIRMATION
      return
    fi
    if [[ -z "$first" ]]; then
      SCREEN_STATUS='Das Passwort darf nicht leer sein.'
      continue
    fi
    if (( allow_cancel )); then
      render_prompt 'Passwort wiederholen' '' 'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar. Enter bricht die Passwortänderung ab.'
      if ! IFS= read -r -s -p 'Passwort wiederholen (Enter = Abbrechen): ' second </dev/tty; then handle_input_eof; fi
    else
      render_prompt 'Passwort wiederholen' '' 'Mindestens 12 Zeichen. Die Eingabe bleibt unsichtbar.'
      if ! IFS= read -r -s -p 'Passwort wiederholen: ' second </dev/tty; then handle_input_eof; fi
    fi
    printf '\n' > /dev/tty
    if [[ -z "$second" ]] && (( allow_cancel )); then
      PASSWORD_CANCELLED=1
      unset PASSWORD_VALUE PASSWORD_CONFIRMATION
      return
    fi
    if [[ "$first" != "$second" ]]; then
      SCREEN_STATUS='Die Passwörter stimmen nicht überein. Bitte erneut eingeben.'
      continue
    fi
    if (( ${#first} < 12 )); then
      SCREEN_STATUS='Das Passwort muss mindestens 12 Zeichen lang sein.'
      continue
    fi
    SCREEN_STATUS=''
    PASSWORD_VALUE="$first"
    PASSWORD_CONFIRMATION="$second"
    return
  done
}

generate_password_hash() {
  local allow_cancel="${1:-0}" generated output
  read_password_pair "$allow_cancel"
  if (( PASSWORD_CANCELLED )); then
    LAST_NOTICE='Passwortänderung abgebrochen. Es wurden keine Änderungen vorgenommen.'
    return 1
  fi
  if ! validate_compose || ! run_api_build; then
    unset PASSWORD_VALUE PASSWORD_CONFIRMATION
    return 1
  fi
  if ! output="$(mktemp "$ROOT_DIR/.env.setup.hash.XXXXXX")"; then
    unset PASSWORD_VALUE PASSWORD_CONFIRMATION
    LAST_NOTICE='Temporäre Datei für den Passwort-Hash konnte nicht erstellt werden. Speicherplatz und Schreibrechte prüfen.'
    return 1
  fi
  screen_status_page 'Passwort-Hash erzeugen' 'Das Passwort wird im API-Container gehasht. Es wird nicht in der Konfiguration gespeichert.'
  if ! generated="$(printf '%s\n%s\n' "$PASSWORD_VALUE" "$PASSWORD_CONFIRMATION" | docker compose run --rm --no-deps -T --entrypoint python api -m api.password_hash --password-stdin 2>"$output")"; then
    unset PASSWORD_VALUE PASSWORD_CONFIRMATION
    screen_show_log_tail 'Der Passwort-Hash konnte nicht erzeugt werden. Letzte Ausgaben:' "$output"
    rm -f -- "$output"
    LAST_NOTICE='Passwort-Hash konnte nicht erzeugt werden. Docker- und API-Image-Fehler prüfen; anschließend erneut versuchen.'
    return 1
  fi
  rm -f -- "$output"
  unset PASSWORD_VALUE PASSWORD_CONFIRMATION
  if [[ ! "$generated" =~ ^scrypt:[0-9]+:[0-9]+:[0-9]+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$ ]]; then
    LAST_NOTICE='Der Passwort-Hash-Befehl lieferte keine gültige Hash-Zeile. Bitte erneut versuchen.'
    return 1
  fi
  PASSWORD_HASH="$generated"
  LAST_NOTICE='Admin-Passwort-Hash wurde erstellt.'
}

color_init() {
  C_RESET='' C_BOLD='' C_BLUE='' C_CYAN='' C_GREEN='' C_YELLOW='' C_RED=''
  if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_BLUE=$'\033[38;5;75m'
    C_CYAN=$'\033[38;5;80m'; C_GREEN=$'\033[38;5;114m'
    C_YELLOW=$'\033[38;5;221m'; C_RED=$'\033[38;5;203m'
  fi
}

screen_enter() {
  if [[ -t 1 && "${TERM:-dumb}" != dumb ]]; then
    printf '\033[?1049h\033[?25h\033[2J\033[H' > /dev/tty
    SCREEN_ACTIVE=1
  fi
}

screen_clear() {
  if [[ "${TERM:-dumb}" != dumb ]]; then printf '\033[2J\033[H' > /dev/tty; fi
}

screen_header() {
  local version='unbekannt' padding title frame_width=90 inner_width=88 terminal_size terminal_cols
  if [[ -r "$ROOT_DIR/VERSION" ]]; then IFS= read -r version < "$ROOT_DIR/VERSION"; fi
  [[ "$version" =~ ^[0-9A-Za-z._+-]+$ ]] || version='unbekannt'
  if [[ "${TERM:-dumb}" != dumb ]]; then
    terminal_size="$(stty size < /dev/tty 2>/dev/null || true)"
    read -r _ terminal_cols <<< "$terminal_size"
    if [[ "${terminal_cols:-}" =~ ^[0-9]+$ ]] && (( terminal_cols <= frame_width )); then
      frame_width=$((terminal_cols - 1))
      (( frame_width >= 40 )) || frame_width=40
    fi
  fi
  inner_width=$((frame_width - 2))
  SCREEN_FRAME_WIDTH=$frame_width
  SCREEN_TEXT_WIDTH=$((inner_width - 4))
  title="  $(translate 'INM2 Server-Setup')  v$version"
  if (( ${#title} > inner_width )); then title="${title:0:inner_width}"; fi
  padding=$((inner_width - ${#title}))
  (( padding >= 0 )) || padding=0
  printf -v padding '%*s' "$padding" ''
  local rule
  printf -v rule '%*s' "$inner_width" ''
  rule="${rule// /─}"
  screen_clear
  printf '%s╭%s╮%s\n' "$C_BLUE" "$rule" "$C_RESET"
  printf '%s│%s%s%s│%s\n' "$C_BLUE" "$C_BOLD" "$title" "$padding" "$C_BLUE$C_RESET"
  printf '%s╰%s╯%s\n' "$C_BLUE" "$rule" "$C_RESET"
}

print_wrapped() {
  local text width="${SCREEN_TEXT_WIDTH:-84}"
  text="$(translate "$1")"
  printf '%s\n' "$text" | fold -s -w "$width"
}

print_wrapped_hanging() {
  local prefix="$1" text="$2" width="${SCREEN_TEXT_WIDTH:-84}" indent
  text="$(translate "$text")"
  printf -v indent '%*s' "${#prefix}" ''
  printf '%s\n' "$text" | fold -s -w "$((width - ${#prefix}))" | {
    local first=1 line
    while IFS= read -r line; do
      if (( first )); then printf '%s%s\n' "$prefix" "$line"; first=0
      else printf '%s%s\n' "$indent" "$line"
      fi
    done
  }
}

screen_rule() {
  local width="${SCREEN_FRAME_WIDTH:-90}" rule
  printf -v rule '%*s' "$((width - 2))" ''
  printf '%s' "${rule// /─}"
}

screen_box_top() {
  local title="$(translate "$1")" inner_width=$(( ${SCREEN_FRAME_WIDTH:-90} - 2 )) rule
  printf -v rule '%*s' "$((inner_width - ${#title} - 2))" ''
  printf '┌ %s %s┐\n' "$title" "${rule// /─}"
}

render_prompt() {
  local label="$1" default="${2:-}" extra_help="${3:-}"
  screen_header
  printf '\n%s%s%s\n%s' "$C_BOLD" "$(translate "${SCREEN_SECTION:-Eingabe}")" "$C_RESET" "$C_CYAN"; screen_rule; printf '%s\n' "$C_RESET"
  printf '\n'; print_wrapped "$label"; printf '\n'
  if [[ -n "$default" ]]; then print_wrapped "Aktueller Wert: $default"; printf '\n'; fi
  if [[ -n "$SCREEN_HELP" ]]; then printf '\n%s›%s ' "$C_BLUE" "$C_RESET"; print_wrapped "$SCREEN_HELP"; fi
  if [[ -n "$extra_help" ]]; then printf '\n%s›%s ' "$C_BLUE" "$C_RESET"; print_wrapped "$extra_help"; fi
  if [[ -n "$SCREEN_STATUS" ]]; then printf '\n%s' "$C_YELLOW"; print_wrapped "$SCREEN_STATUS"; printf '%s\n' "$C_RESET"; fi
  printf '\n'
}

screen_message() {
  local title="$1" body="$2"
  title="$(translate "$title")"
  body="$(translate "$body")"
  screen_header
  printf '\n%s%s%s\n%s' "$C_BOLD" "$title" "$C_RESET" "$C_CYAN"; screen_rule; printf '%s\n\n' "$C_RESET"
  printf '%b' "$body" | fold -s -w "${SCREEN_TEXT_WIDTH:-84}"; printf '\n\n'
  if ! read -r -p 'Return zum Fortfahren … ' _ </dev/tty; then handle_input_eof; fi
}

screen_status_page() {
  local title="$1" body="$2"
  title="$(translate "$title")"
  body="$(translate "$body")"
  screen_header
  printf '\n%s%s%s\n%s' "$C_BOLD" "$title" "$C_RESET" "$C_CYAN"; screen_rule; printf '%s\n\n' "$C_RESET"
  print_wrapped "$body"; printf '\n'
}

screen_show_log_tail() {
  local title="$1" log_file="$2"
  screen_header
  printf '\n%s' "$C_RED"; print_wrapped "$title"; printf '%s\n\n' "$C_RESET"
  tail -n 8 "$log_file" | fold -s -w "${SCREEN_TEXT_WIDTH:-84}"
  printf '\n'
  if ! read -r -p 'Return zum Fortfahren … ' _ </dev/tty; then handle_input_eof; fi
}

validate_compose() {
  local output
  if ! output="$(mktemp "$ROOT_DIR/.env.setup.config.XXXXXX")"; then
    LAST_NOTICE='Temporäre Datei für die Compose-Prüfung konnte nicht erstellt werden.'
    return 1
  fi
  if docker compose config --quiet >"$output" 2>&1; then
    rm -f -- "$output"
  else
    screen_show_log_tail 'Die Compose-Konfiguration ist ungültig. Letzte Ausgaben:' "$output"
    rm -f -- "$output"
    LAST_NOTICE='Die Compose-Konfiguration ist ungültig. Angezeigten Fehler beheben und erneut versuchen.'
    return 1
  fi
}

run_api_build() {
  local output
  if ! output="$(mktemp "$ROOT_DIR/.env.setup.build.XXXXXX")"; then
    LAST_NOTICE='Temporäre Datei für den Docker-Build konnte nicht erstellt werden.'
    return 1
  fi
  screen_status_page 'API-Image vorbereiten' 'Docker baut das API-Image. Die Ausgabe bleibt im Hintergrund, damit der Bildschirm stehen bleibt.'
  if docker compose build api >"$output" 2>&1; then
    rm -f -- "$output"
    LAST_NOTICE='API-Image wurde erfolgreich vorbereitet.'
  else
    screen_show_log_tail 'Das API-Image konnte nicht gebaut werden. Letzte Ausgaben:' "$output"
    rm -f -- "$output"
    LAST_NOTICE='Docker konnte das API-Image nicht bauen. Angezeigte Fehler prüfen und erneut versuchen.'
    return 1
  fi
}

generate_totp_setup() {
  local output log_file
  if ! log_file="$(mktemp "$ROOT_DIR/.env.setup.totp.XXXXXX")"; then
    LAST_NOTICE='Temporäre Datei für die TOTP-Einrichtung konnte nicht erstellt werden.'
    return 1
  fi
  screen_status_page 'TOTP-Schlüssel erzeugen' 'Der Schlüssel wird sicher im API-Container erstellt.'
  if ! output="$(docker compose run --rm --no-deps -T --entrypoint python api -m api.totp_secret 2>"$log_file")"; then
    screen_show_log_tail 'Der TOTP-Schlüssel konnte nicht erzeugt werden. Letzte Ausgaben:' "$log_file"
    rm -f -- "$log_file"
    LAST_NOTICE='Der TOTP-Schlüssel konnte nicht erzeugt werden. Angezeigte Fehler prüfen und erneut versuchen.'
    return 1
  fi
  rm -f -- "$log_file"
  TOTP_SECRET="$(printf '%s\n' "$output" | sed -n 's/^INM2_TOTP_SECRET=//p')"
  TOTP_URI="$(printf '%s\n' "$output" | sed -n 's/^Authenticator setup URI: //p')"
  if [[ ! "$TOTP_SECRET" =~ ^[A-Z2-7]{32}$ || -z "$TOTP_URI" ]]; then
    LAST_NOTICE='Der TOTP-Befehl lieferte keine gültigen Einrichtungsdaten. Bitte erneut versuchen.'
    return 1
  fi
  screen_message 'Authenticator-App einrichten' "Schlüssel: $TOTP_SECRET\n\nEinrichtungs-URI: $TOTP_URI\n\nBewahre den Schlüssel sicher auf."
}

check_tty() {
  [[ -r /dev/tty && -w /dev/tty ]] || fail 'Für das Setup ist ein interaktives Terminal erforderlich.'
}

set_update() {
  local key="$1" value="$2" baseline
  if [[ -n "${ENV_BASELINE[$key]+x}" ]]; then baseline="${ENV_BASELINE[$key]}"
  else get_env_value "$key" ''; baseline="$REPLY"
  fi
  if [[ "$value" == "$baseline" ]]; then unset 'ENV_UPDATES[$key]'
  else ENV_UPDATES["$key"]="$value"
  fi
}

load_default() {
  get_env_value "$1" "$2"
  ENV_BASELINE["$1"]="$REPLY"
}

save_group() {
  if ((${#ENV_UPDATES[@]} == 0)); then return 0; fi
  if ! apply_env_updates; then return 1; fi
  if (( BOOTSTRAP_REQUIRED == 0 )); then SETUP_COMPLETE=1; fi
  ENV_EXISTS=1
  LAST_NOTICE='Änderungen gespeichert. Die übrigen .env-Einträge blieben erhalten. Übernehmen mit: docker compose up -d --build'
  if [[ -n "$BACKUP_NOTICE" ]]; then LAST_NOTICE+=" | $BACKUP_NOTICE"; fi
}

prompt_port() {
  local key="$1" label="$2" default="$3" value
  while true; do
    prompt_positive_integer "$label" "$default"
    value="$REPLY"
    if (( 10#$value <= 65535 )); then break; fi
    SCREEN_STATUS='Ports müssen zwischen 1 und 65535 liegen.'
  done
  set_update "$key" "$value"
  REPLY="$value"
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(.3); sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)' "$port"
  else
    return 1
  fi
}

api_port_in_use() {
  local port="$1" published published_port
  if ! port_in_use "$port"; then return 1; fi

  # A running INM2 API may already own its configured host port. Treat that
  # exact Compose mapping as available for retaining the current setting.
  if command -v docker >/dev/null 2>&1; then
    published="$(docker compose port --index 1 api 8000 2>/dev/null || true)"
    while IFS= read -r endpoint; do
      published_port="${endpoint##*:}"
      if [[ "$published_port" == "$port" ]]; then return 1; fi
    done <<< "$published"
  fi

  return 0
}

suggest_free_ui_port() {
  local candidate="$1"
  while (( candidate < 65535 )); do
    candidate=$((candidate + 1))
    if ! port_in_use "$candidate"; then REPLY="$candidate"; return 0; fi
  done
  REPLY=''
  return 1
}

check_log_source() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    SCREEN_STATUS="Logdatei noch nicht vorhanden: $path. Sie muss vor dem Import von Traefik angelegt werden."
    return 0
  fi
  if [[ ! -f "$path" ]]; then
    SCREEN_STATUS="Logquelle ist keine reguläre Datei: $path"
    return 0
  fi
  if [[ -s "$path" ]]; then
    SCREEN_STATUS='Logdatei gefunden. Zugriffsrechte und JSON-Format werden vom Collector beim Import geprüft.'
  else
    SCREEN_STATUS='Logdatei ist leer. Sobald Traefik schreibt, kann der Collector sie einlesen.'
  fi
}

menu_required() {
  local log_path log_dir log_file old_log_file old_log_files secret hash
  section 'Pflichtangaben und Einrichtung'
  explain 'Diese Angaben braucht INM2 zwingend: eine Logdatei sowie ein Admin-Passwort und ein Sitzungsschlüssel. Der Sitzungsschlüssel wird sicher erzeugt; das Passwort wird nur als Hash gespeichert.'
  load_default INPUT_LOG_DIR './logs'; local old_dir="$REPLY"
  [[ -n "$old_dir" ]] || old_dir='./logs'
  load_default LOG_FILES 'access.log'; old_log_files="$REPLY"; old_log_file="${old_log_files%%;*}"; old_log_file="${old_log_file##*/}"; log_file="$old_log_file"
  [[ -n "$log_file" ]] || log_file='access.log'
  [[ "$old_dir" == / ]] && log_path="/$log_file" || log_path="${old_dir%/}/$log_file"
  while true; do
    prompt_value 'Vollständiger Hostpfad zur Access-Logdatei' "$log_path"
    log_path="$REPLY"
    if [[ "$log_path" == *';'* || "$log_path" == *':'* ]]; then
      SCREEN_STATUS='Der Logpfad darf kein Semikolon und keinen Doppelpunkt enthalten.'
      continue
    fi
    log_file="${log_path##*/}"
    if [[ -z "$log_file" || "$log_file" == . || "$log_file" == .. ]]; then
      SCREEN_STATUS='Bitte einen Dateipfad mit Dateinamen angeben.'
      continue
    fi
    break
  done
  if [[ "$log_path" == */* ]]; then log_dir="${log_path%/*}"; [[ -n "$log_dir" ]] || log_dir='/'; else log_dir='.'; fi
  if ! mkdir -p -- "$log_dir" 2>/dev/null; then
    SCREEN_STATUS="Logverzeichnis kann nicht angelegt werden: $log_dir. Pfad und Schreibrechte prüfen."
    while true; do
      prompt_value 'Vollständiger Hostpfad zur Access-Logdatei' "$log_path"
      log_path="$REPLY"
      if [[ "$log_path" == *';'* || "$log_path" == *':'* ]]; then SCREEN_STATUS='Der Logpfad darf kein Semikolon und keinen Doppelpunkt enthalten.'; continue; fi
      log_file="${log_path##*/}"
      if [[ -z "$log_file" || "$log_file" == . || "$log_file" == .. ]]; then SCREEN_STATUS='Bitte einen Dateipfad mit Dateinamen angeben.'; continue; fi
      if [[ "$log_path" == */* ]]; then log_dir="${log_path%/*}"; [[ -n "$log_dir" ]] || log_dir='/'; else log_dir='.'; fi
      if mkdir -p -- "$log_dir" 2>/dev/null; then break; fi
      SCREEN_STATUS="Logverzeichnis kann nicht angelegt werden: $log_dir. Pfad und Schreibrechte prüfen."
    done
  fi
  set_update INPUT_LOG_DIR "$log_dir"
  if [[ "$log_file" != "$old_log_file" ]]; then set_update LOG_FILES "$log_file"; fi

  load_default INM2_AUTH_SECRET ''
  secret="$REPLY"
  if [[ ${#secret} -lt 32 ]]; then
    if command -v openssl >/dev/null 2>&1; then
      secret="$(openssl rand -hex 32 2>/dev/null || true)"
    else
      secret="$(od -An -N32 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n' || true)"
    fi
    if [[ ! "$secret" =~ ^[A-Fa-f0-9]{64}$ ]]; then
      LAST_NOTICE='Sitzungsschlüssel konnte nicht erzeugt werden. OpenSSL oder /dev/urandom prüfen; anschließend erneut versuchen.'
      return 1
    fi
    set_update INM2_AUTH_SECRET "$secret"
  fi
  load_default INM2_ADMIN_PASSWORD_HASH ''
  hash="$REPLY"
  if [[ ! "$hash" =~ ^scrypt:[0-9]+:[0-9]+:[0-9]+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$ ]]; then
    set_update INM2_AUTH_SECRET "$secret"
    if ! save_group; then return 1; fi
    if ! generate_password_hash; then return 1; fi
    ENV_UPDATES=()
    set_update INM2_ADMIN_PASSWORD_HASH "$PASSWORD_HASH"
  fi
  if ! save_group; then return 1; fi
  BOOTSTRAP_REQUIRED=0
  SETUP_COMPLETE=1
  if [[ -e "$log_path" ]]; then
    check_log_source "$log_path"
    [[ -n "$SCREEN_STATUS" ]] && LAST_NOTICE+=" $SCREEN_STATUS"
  else
    LAST_NOTICE+=' Die Logdatei fehlt noch; der Collector kann starten, sobald Traefik sie anlegt.'
  fi
}

menu_ports() {
  section 'Ports'
  explain 'Die Weboberfläche ist über den Server-Port erreichbar. Der API-Port ist aus Sicherheitsgründen nur lokal auf dem Server gebunden. Der Collector-Port ist ausschließlich im internen Docker-Netzwerk erreichbar.'
  load_default INM2_UI_PORT 3000
  local ui_default="$REPLY" ui api
  if port_in_use "$ui_default" && suggest_free_ui_port "$ui_default"; then
    explain "Port $ui_default ist belegt. Vorschlag: $REPLY."
    ui_default="$REPLY"
  fi
  while true; do
    prompt_port INM2_UI_PORT 'Server-Port der Weboberfläche' "$ui_default"
    ui="$REPLY"
    if (( 10#$ui > 65535 )); then SCREEN_STATUS='Ports müssen zwischen 1 und 65535 liegen.'; continue; fi
    if port_in_use "$ui"; then SCREEN_STATUS="Port $ui ist belegt. Bitte einen anderen Port wählen."; continue; fi
    break
  done
  load_default INM2_API_PORT 8000
  local api_default="$REPLY"
  while true; do
    prompt_port INM2_API_PORT 'Server-Port der API' "$api_default"
    api="$REPLY"
    if (( 10#$api > 65535 )); then SCREEN_STATUS='Ports müssen zwischen 1 und 65535 liegen.'; continue; fi
    if [[ "$ui" == "$api" ]]; then SCREEN_STATUS='Weboberfläche und API benötigen unterschiedliche Ports.'; continue; fi
    if api_port_in_use "$api"; then SCREEN_STATUS="Port $api ist belegt. Bitte einen anderen Port wählen."; continue; fi
    break
  done
  load_default INM2_COLLECTOR_PORT 8001
  prompt_port INM2_COLLECTOR_PORT 'Interner Collector-Steuerport' "$REPLY"
  if ! save_group; then return 1; fi
}

menu_security() {
  local prior_enabled prior_secret enabled secret
  section 'Zugangssicherheit'
  explain 'Bei HTTPS muss das sichere Sitzungscookie aktiv bleiben. TOTP verlangt beim Login zusätzlich zum Passwort einen zeitabhängigen Code aus einer Authenticator-App.'
  load_default INM2_COOKIE_SECURE true
  prompt_yes_no 'Wird INM2 über HTTPS aufgerufen?' "$REPLY"; set_update INM2_COOKIE_SECURE "$REPLY"
  load_default INM2_TOTP_ENABLED false; prior_enabled="$REPLY"
  load_default INM2_TOTP_SECRET ''; prior_secret="$REPLY"
  prompt_yes_no 'Zweiten Faktor (TOTP) verlangen?' "$prior_enabled"; enabled="$REPLY"
  set_update INM2_TOTP_ENABLED "$enabled"
  if [[ "$enabled" == true ]]; then
    secret="$prior_secret"
    if [[ ! "$secret" =~ ^[A-Z2-7]{32}$ ]]; then
      get_env_value INM2_AUTH_SECRET ''
      if [[ ${#REPLY} -lt 32 ]]; then
        LAST_NOTICE='Bitte zuerst im Menüpunkt Pflichtangaben einen Sitzungsschlüssel einrichten.'
        set_update INM2_TOTP_ENABLED "$prior_enabled"
        return 1
      fi
      if ! validate_compose || ! run_api_build || ! generate_totp_setup; then
        set_update INM2_TOTP_ENABLED "$prior_enabled"
        return 1
      fi
      secret="$TOTP_SECRET"
    fi
    set_update INM2_TOTP_SECRET "$secret"
  else
    set_update INM2_TOTP_SECRET ''
  fi
  if ! save_group; then return 1; fi
}

prompt_percent() {
  local label="$1" default="$2" value
  while true; do
    prompt_value "$label" "$default"; value="$REPLY"
    if [[ "$value" =~ ^[0-9]{1,3}$ ]] && (( 10#$value <= 100 )); then REPLY="$value"; SCREEN_STATUS=''; return; fi
    SCREEN_STATUS='Bitte eine ganze Zahl zwischen 0 und 100 eingeben.'
  done
}

menu_detection() {
  section 'Burst- und Vorfallerkennung'
  explain 'Der Maximalabstand begrenzt die Lücke zwischen Requests; Mindestzahl und Zeitfenster qualifizieren eine Folge als Burst.'
  load_default BURST_MAX_GAP_SECONDS 5; prompt_positive_integer 'Maximaler Request-Abstand im Burst (Sekunden)' "$REPLY"; set_update BURST_MAX_GAP_SECONDS "$REPLY"
  explain 'Ein Burst braucht mindestens diese Anzahl Requests innerhalb des Zeitfensters.'
  load_default BURST_MIN_REQUESTS 5; prompt_positive_integer 'Mindestzahl Requests pro Burst' "$REPLY"; set_update BURST_MIN_REQUESTS "$REPLY"
  explain 'Requests außerhalb dieses Zeitfensters zählen nicht zur Qualifizierung eines Bursts.'
  load_default BURST_WINDOW_SECONDS 60; prompt_positive_integer 'Burst-Zeitfenster (Sekunden)' "$REPLY"; set_update BURST_WINDOW_SECONDS "$REPLY"
  load_default INCIDENT_MERGE_OVERLAP_PERCENT 80
  explain 'Zusammenführung: Kriterien desselben Akteurs werden verbunden, wenn mehr als dieser Anteil des kürzeren Zeitraums überlappt.'
  prompt_percent 'Mindestüberschneidung (Prozent)' "$REPLY"; set_update INCIDENT_MERGE_OVERLAP_PERCENT "$REPLY"
  explain 'In diesem rollierenden Fenster werden passende Pfad-Requests derselben Quell-IP ausgewertet.'
  load_default LOW_SLOW_SCAN_WINDOW_SECONDS 10800; prompt_positive_integer 'Zeitfenster für langsame Scans (Sekunden; 10800 = 3 Stunden)' "$REPLY"; set_update LOW_SLOW_SCAN_WINDOW_SECONDS "$REPLY"
  explain 'Gezählt werden unterschiedliche sensible Pfade oder Pfade mit HTTP-Fehlerantwort.'
  load_default LOW_SLOW_SCAN_MIN_PATHS 12; prompt_positive_integer 'Mindestens unterschiedliche passende Pfade (sensible oder mit HTTP-Fehler)' "$REPLY"; set_update LOW_SLOW_SCAN_MIN_PATHS "$REPLY"
  explain 'Die Pfade müssen mindestens über diese Anzahl verschiedener Hosts verteilt sein.'
  load_default LOW_SLOW_SCAN_MIN_HOSTS 2; prompt_positive_integer 'Mindestens verschiedene Hosts' "$REPLY"; set_update LOW_SLOW_SCAN_MIN_HOSTS "$REPLY"
  explain 'Erster bis letzter passender Request müssen mindestens so weit auseinanderliegen.'
  load_default LOW_SLOW_SCAN_MIN_SPAN_SECONDS 300; prompt_nonnegative_integer 'Mindestens verstrichene Zeit (Sekunden; 300 = 5 Minuten)' "$REPLY"; set_update LOW_SLOW_SCAN_MIN_SPAN_SECONDS "$REPLY"
  if ! save_group; then return 1; fi
}

menu_other_settings() {
  local geo_dir
  section 'Import, Wartung und optionale Daten'
  load_default INPUT_INTERVAL_SECONDS 60; explain 'Wie oft der Collector neue Logzeilen verarbeitet.'; prompt_positive_integer 'Importintervall (Sekunden)' "$REPLY"; set_update INPUT_INTERVAL_SECONDS "$REPLY"
  load_default INPUT_SAVE_MARGIN_CHARACTERS 4096; explain 'Zeichen am Dateiende, die ausgespart werden, damit keine unvollständige Logzeile importiert wird.'; prompt_positive_integer 'Sicherheitspuffer am Logende (Zeichen)' "$REPLY"; set_update INPUT_SAVE_MARGIN_CHARACTERS "$REPLY"
  load_default MAINTENANCE_INTERVAL_DAYS 1; prompt_positive_integer 'Wartungsintervall (Tage)' "$REPLY"; set_update MAINTENANCE_INTERVAL_DAYS "$REPLY"
  load_default MAINTENANCE_INACTIVE_DAYS 90; prompt_nonnegative_integer 'Akteure nach wie vielen inaktiven Tagen bereinigen?' "$REPLY"; set_update MAINTENANCE_INACTIVE_DAYS "$REPLY"
  load_default GEOLITE_DB_DIR './databases/geoip'; explain 'Hostordner mit GeoLite2-City.mmdb und GeoLite2-ASN.mmdb; wird im Container schreibgeschützt unter /geoip eingebunden.'; prompt_value 'Hostverzeichnis der GeoLite2-Datenbanken' "$REPLY"; geo_dir="$REPLY"; set_update GEOLITE_DB_DIR "$geo_dir"
  load_default IGNORE_REQUEST_ROUTES ''; prompt_optional 'Host/Pfad-Präfixe beim Import überspringen' "$REPLY"; set_update IGNORE_REQUEST_ROUTES "$REPLY"
  load_default KNOWN_HOSTS ''; prompt_optional 'Eigene Hostnamen als bekannt markieren' "$REPLY"; set_update KNOWN_HOSTS "$REPLY"
  if ! save_group; then return 1; fi
  mkdir -p -- "$geo_dir" 2>/dev/null || LAST_NOTICE="GeoLite-Verzeichnis konnte nicht angelegt werden: $geo_dir. Bei Bedarf selbst erstellen."
}

menu_password() {
  section 'Admin-Passwort ändern'
  get_env_value INM2_AUTH_SECRET ''
  if [[ ${#REPLY} -lt 32 ]]; then LAST_NOTICE='Der Sitzungsschlüssel fehlt. Bitte zuerst Pflichtangaben einrichten.'; return 1; fi
  if ! generate_password_hash 1; then return; fi
  set_update INM2_ADMIN_PASSWORD_HASH "$PASSWORD_HASH"
  if ! save_group; then return 1; fi
  LAST_NOTICE='Admin-Passwort geändert. Damit es gilt: docker compose up -d api'
}

menu_backup_cleanup() {
  local file count=0 removed=0 failed=0
  local backups=()
  for file in "$ROOT_DIR"/.env.backup.*; do
    [[ -f "$file" || -L "$file" ]] && backups+=("$file")
  done
  if ((${#backups[@]} == 0)); then
    screen_message 'Keine Backupdateien gefunden' "Im Projektverzeichnis $ROOT_DIR gibt es keine Dateien mit dem Muster .env.backup.*. Return: zurück zum Hauptmenü."
    LAST_NOTICE=''
    return 0
  fi

  section 'Backupdateien löschen'
  explain "Gefundene Dateien im Projektverzeichnis $ROOT_DIR:"
  local backup_list=''
  for file in "${backups[@]}"; do
    backup_list+="$file "
  done
  SCREEN_HELP+=$'\n'"${backup_list% }"
  prompt_yes_no 'Angezeigte Backupdateien endgültig löschen?' false
  if [[ "$REPLY" != true ]]; then
    LAST_NOTICE='Löschen abgebrochen. Es wurden keine Backupdateien entfernt.'
    return 0
  fi

  for file in "${backups[@]}"; do
    if rm -f -- "$file"; then ((removed += 1)); else ((failed += 1)); fi
  done
  count=${#backups[@]}
  if (( failed == 0 )); then
    LAST_NOTICE="$removed von $count Backupdateien gelöscht."
  else
    LAST_NOTICE="$removed von $count Backupdateien gelöscht; $failed konnten nicht gelöscht werden."
  fi
}

check_tty
color_init
if [[ -r "$LANGUAGE_FILE" ]]; then
  IFS= read -r language_saved < "$LANGUAGE_FILE" || true
  [[ "$language_saved" == en || "$language_saved" == de ]] && LANGUAGE="$language_saved"
fi
check_compose
require_command awk
require_command grep
require_command sed
require_command mktemp
check_writable_project
while [[ -e "$ENV_FILE" || -L "$ENV_FILE" ]]; do
  if [[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]]; then break; fi
  wait_for_retry '.env muss eine reguläre Datei sein. Nach Ersetzen des symbolischen Links oder ungültigen Objekts durch eine reguläre Datei Eingabetaste zur erneuten Prüfung.'
done
if [[ -f "$ENV_FILE" ]]; then
  ENV_EXISTS=1
else
  ENV_EXISTS=0
  BOOTSTRAP_REQUIRED=1
fi
screen_enter

while true; do
  if [[ -f "$ENV_FILE" ]]; then ENV_EXISTS=1; else ENV_EXISTS=0; fi
  screen_header
  printf '\n%s' "$C_GREEN"; print_wrapped_hanging '[✓] ' 'Systemvoraussetzungen geprüft: Docker, Compose v2, Docker-Dienst und Projektdateien.'; printf '%s\n' "$C_RESET"
  if (( ENV_EXISTS )); then
    printf '%s' "$C_GREEN"; print_wrapped_hanging '[✓] ' 'Vorhandene .env gefunden. Änderungen werden gesichert.'; printf '%s\n' "$C_RESET"
  else
    printf '%s' "$C_YELLOW"; print_wrapped_hanging '[i] ' 'Noch keine .env vorhanden; die Pflichtangaben werden zuerst eingerichtet.'; printf '%s\n' "$C_RESET"
  fi
  printf '\n%s' "$C_CYAN"; screen_box_top 'Hauptmenü'; printf '%s' "$C_RESET"
  first_menu_item= language_switch= language_gap=
  first_menu_item="$(translate '  1  Pflichtangaben und Logquelle prüfen/ändern')"
  if [[ "$LANGUAGE" == de ]]; then language_switch='[E] change to english'
  else language_switch='[D] zu deutsch wechseln'
  fi
  language_gap=$(( SCREEN_TEXT_WIDTH - ${#first_menu_item} - ${#language_switch} ))
  if (( language_gap < 1 )); then language_gap=1; fi
  printf '%s%*s%s%s%s\n' "$first_menu_item" "$language_gap" '' "$C_YELLOW" "$language_switch" "$C_RESET"
  if (( ENV_EXISTS )); then
    print_wrapped '  2  Ports'
    print_wrapped '  3  Zugangssicherheit'
    print_wrapped '  4  Burst- und Vorfallerkennung'
    print_wrapped '  5  Import, Wartung und optionale Daten'
    print_wrapped '  6  Admin-Passwort ändern'
  else
    printf '%s' "$C_YELLOW"; print_wrapped '  Weitere Menüpunkte erscheinen nach der Ersteinrichtung.'; printf '%s\n' "$C_RESET"
  fi
  print_wrapped '  7  .env-Backupdateien löschen'
  print_wrapped '  0  Beenden'
  printf '%s└' "$C_CYAN"; screen_rule; printf '┘%s\n' "$C_RESET"
  if [[ -n "$LAST_NOTICE" ]]; then printf '\n%s' "$C_GREEN"; print_wrapped "$LAST_NOTICE"; printf '%s\n' "$C_RESET"; fi
  if ! read -r -p "$(translate 'Auswahl: ')" MENU_CHOICE </dev/tty; then handle_input_eof; fi
  MENU_CHOICE="${MENU_CHOICE,,}"
  LAST_NOTICE=''
  case "$MENU_CHOICE" in
    1) menu_required || true ;;
    2) if (( ENV_EXISTS )); then menu_ports || true; else LAST_NOTICE='Bitte zuerst die Pflichtangaben einrichten.'; fi ;;
    3) if (( ENV_EXISTS )); then menu_security || true; else LAST_NOTICE='Bitte zuerst die Pflichtangaben einrichten.'; fi ;;
    4) if (( ENV_EXISTS )); then menu_detection || true; else LAST_NOTICE='Bitte zuerst die Pflichtangaben einrichten.'; fi ;;
    5) if (( ENV_EXISTS )); then menu_other_settings || true; else LAST_NOTICE='Bitte zuerst die Pflichtangaben einrichten.'; fi ;;
    6) if (( ENV_EXISTS )); then menu_password || true; else LAST_NOTICE='Bitte zuerst die Pflichtangaben einrichten.'; fi ;;
    7) menu_backup_cleanup || true ;;
    e) if [[ "$LANGUAGE" == de ]]; then toggle_language; else LAST_NOTICE='Die Sprache ist bereits Englisch.'; fi ;;
    d) if [[ "$LANGUAGE" == en ]]; then toggle_language; else LAST_NOTICE='Die Sprache ist bereits Deutsch.'; fi ;;
    0) break ;;
    *) LAST_NOTICE='Bitte eine angezeigte Menünummer wählen.' ;;
  esac
done
screen_leave
printf '\n%sINM2-Setup beendet.%s\n' "$C_GREEN" "$C_RESET"
