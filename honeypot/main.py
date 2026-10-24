"""Small, rule-based HTTP decoy for common web probes."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import re
import base64
import fcntl
import fnmatch
import html
import shlex
import signal
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

MAX_CAPTURE_BYTES = 10 * 1024 * 1024
INLINE_BODY_BYTES = 64 * 1024
LOG = logging.getLogger("honeypot")
SESSION_COOKIE = "svh_admin_session"
SESSION_IDLE_SECONDS = 30 * 60
MAX_SESSIONS = 10_000
DECOY_USERNAME = "admin"
DECOY_PASSWORD = "Az44O6GRuZhJbJYlmlEy"
DECOY_USERNAMES = {"admin", "administrator", "webmaster", "admin@sv-eichenwacht.example"}
DECOY_PASSWORDS = {
    DECOY_PASSWORD, "admin", "password", "123456", "12345678", "admin123",
    "qwerty", "letmein", "welcome", "welcome1", "changeme", "verein123",
    "eichenwacht1953", "sveichenwacht",
}
_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, object]] = {}
HONEYPOT_UPLOADS: list[dict[str, str]] = []
_LAST_SESSION_CLEANUP = 0.0

WP_LOGIN = re.compile(r"^/(wp-login\.php|wp-admin(?:/.*)?)$", re.IGNORECASE)
PHP_MYADMIN = re.compile(r"^/(phpmyadmin|pma)(?:/.*)?$", re.IGNORECASE)
ADMIN_LOGIN = re.compile(r"^/(admin\.php|administrator\.php|login\.php|signin\.php|console\.php)$", re.IGNORECASE)
API_PATH = re.compile(r"^/(api|graphql|swagger|openapi)(?:/.*)?$", re.IGNORECASE)


def read_request_body(stream, headers) -> tuple[bytes, int, bool]:
    """Read a bounded request body, including chunked uploads."""
    transfer_encoding = headers.get("Transfer-Encoding", "").lower()
    if "chunked" in transfer_encoding:
        body = bytearray()
        total = 0
        clipped = False
        while True:
            line = stream.readline(256)
            if not line:
                raise ConnectionError("Unexpected end of chunked request")
            try:
                size = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError as exc:
                raise ValueError("Invalid chunked request size") from exc
            if size < 0:
                raise ValueError("Invalid negative chunked request size")
            if size == 0:
                while stream.readline(8192) not in (b"\r\n", b"\n", b""):
                    pass
                break
            allowed = max(0, MAX_CAPTURE_BYTES + 1 - len(body))
            chunk = stream.read(min(size, allowed))
            body.extend(chunk)
            total += size
            if len(chunk) != size:
                clipped = True
                break
            if stream.read(2) != b"\r\n":
                raise ValueError("Invalid chunked request terminator")
            if len(body) > MAX_CAPTURE_BYTES:
                clipped = True
                break
        return bytes(body[:MAX_CAPTURE_BYTES]), total, clipped

    length_header = headers.get("Content-Length", "0")
    try:
        content_length = max(0, int(length_header))
    except ValueError:
        content_length = 0
    body = stream.read(min(content_length, MAX_CAPTURE_BYTES + 1)) if content_length else b""
    clipped = content_length > len(body) or len(body) > MAX_CAPTURE_BYTES
    return body[:MAX_CAPTURE_BYTES], content_length, clipped

def _page(title: str, body: str, body_class: str = "") -> str:
    safe_title = _html_escape(title)
    safe_class = _html_escape(body_class)
    dashboard_layout = "dashboard-page" in body_class.split()
    sidebar = (
        '<div class="app-shell"><aside class="app-sidebar"><span class="sidebar-heading">VEREINSLEBEN</span>'
        '<a href="/dashboard.php#spiele"><span>⚽</span> Spiele & Tabellen</a>'
        '<a href="/training.php"><span>◷</span> Training & Termine</a>'
        '<a href="/mitglieder.php"><span>♙</span> Mitglieder</a>'
        '<a href="/brett.php"><span>▤</span> Schwarzes Brett</a>'
        '<span class="sidebar-heading sidebar-heading-spaced">VERWALTUNG</span>'
        '<a href="/useradmin.php"><span>♙</span> Mitgliederverwaltung</a>'
        '<a href="/termine.php"><span>◷</span> Terminverwaltung</a>'
        '<a href="/files.php"><span>↥</span> Dateien & Sicherungen</a>'
        '<a href="/tools/terminal.php"><span>⚙</span> Webmaster</a>'
        '<a href="/logout.php"><span>↪</span> Abmelden</a></aside>'
    ) if dashboard_layout else ""
    main_open = '<main class="page-main">' if not dashboard_layout else sidebar + '<main class="page-main">'
    main_close = '</main></div>' if dashboard_layout else '</main>'
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{safe_title} · SV Eichenwacht</title>'
        '<link rel="icon" href="/favicon.ico" sizes="any">'
        '<link rel="stylesheet" href="/assets/portal.css?v=20261020-1"></head>'
        f'<body class="{safe_class}"><header class="site-header"><div class="header-inner">'
        '<a class="brand" href="/" aria-label="SV Eichenwacht Startseite"><span class="brand-mark club-mark">SV</span>'
        '<span class="brand-copy"><strong>SV Eichenwacht</strong><small>Mitgliederbereich</small></span></a>'
        '<span class="header-secure"><span class="secure-dot"></span>Mitgliederbereich</span>'
        '</div></header>'
        f'{main_open}{body}{main_close}'
        '<footer class="site-footer"><span>© 2026 SV Eichenwacht e.V.</span><span><a href="/kontakt.php">Kontakt</a> · <a href="/impressum.php">Impressum</a></span></footer>'
        '</body></html>'
    )


def _html_escape(value: str) -> str:
    return html.escape(value, quote=True)


def _login_html(title: str, action: str, message: str = "") -> str:
    show_contact_form = title == "Mitgliederbereich"
    portal_label = "SV EICHENWACHT · MITGLIEDERBEREICH"
    aside_eyebrow = "SPORTVEREIN SEIT 1953"
    aside_heading = "SV Eichenwacht"
    aside_description = "Hier verwalten Mitglieder und ehrenamtliche Helfer ihre Vereinsangelegenheiten."
    intro = "Melde dich bitte an"
    contact_panel = (
        '<details class="login-contact"><summary>Noch kein Vereinsmitglied? Kontaktformular anzeigen</summary>'
        '<p>Du möchtest mitmachen oder hast eine Frage zum Verein? Schreib uns.</p>'
        '<form method="post" action="/kontakt.php" class="login-form">'
        '<label for="login-contact-name">Name</label><input id="login-contact-name" name="name" autocomplete="name" required placeholder="Vor- und Nachname">'
        '<label for="login-contact-email">E-Mail-Adresse</label><input id="login-contact-email" name="email" type="email" autocomplete="email" required placeholder="name@example.de">'
        '<label for="login-contact-subject">Betreff</label><input id="login-contact-subject" name="subject" required placeholder="Worum geht es?">'
        '<label for="login-contact-message">Nachricht</label><textarea id="login-contact-message" name="message" rows="4" required placeholder="Deine Nachricht an den Vorstand"></textarea>'
        '<label class="fake-captcha"><input type="checkbox" name="captcha" value="checked" required><span>Ich bin kein Roboter</span><span class="captcha-mark" aria-hidden="true">↻</span></label>'
        '<button class="primary-button" type="submit">Nachricht senden <span aria-hidden="true">→</span></button>'
        '</form></details>'
    ) if show_contact_form else ""
    title = _html_escape(title)
    action = _html_escape(action)
    message_html = f'<div class="form-alert" role="alert">{_html_escape(message)}</div>' if message else ""
    body = (
        f'<section class="auth-layout"><div class="auth-aside"><span class="eyebrow">{aside_eyebrow}</span>'
        f'<h1>{aside_heading}</h1><p>{aside_description}</p>'
        '<div class="aside-note"><span class="aside-icon">✓</span><span><strong>Nur für Vereinsmitglieder</strong><small>Bei Fragen hilft der Mitgliederbereich weiter.</small></span></div>'
        '</div><div class="auth-card"><div class="card-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5z"/><circle cx="12" cy="15" r="1"/></svg></div>'
        f'<span class="eyebrow">{portal_label}</span><h2>{title}</h2><p class="card-intro">{intro}</p>'
        f'{message_html}<form method="post" action="{action}" class="login-form">'
        '<label for="username">Mitgliedsnummer oder Benutzername</label><input id="username" name="username" autocomplete="username" required placeholder="z. B. 1042 oder benutzername">'
        '<label for="password">Passwort</label><input id="password" type="password" name="password" autocomplete="current-password" required placeholder="Passwort eingeben">'
        '<div class="form-options"><label class="remember"><input type="checkbox" name="remember"> Angemeldet bleiben</label><a href="/password/reset.php">Passwort vergessen?</a></div>'
        '<button class="primary-button" type="submit">Anmelden <span aria-hidden="true">→</span></button>'
        '</form><p class="card-footnote">Zugang klappt nicht? <a href="mailto:vorstand@sv-eichenwacht.example">Vereinsbüro kontaktieren</a></p>'
        + contact_panel + '</div></section>'
    )
    return _page(title, body, "auth-page")


def _dashboard_html(session: dict[str, object] | None = None) -> str:
    next_date, next_team, next_detail = _next_training_dates()[0]
    body = (
        '<div class="dashboard-heading"><div><span class="eyebrow">MITGLIEDERBEREICH</span><h1>Hallo, schön dass du da bist!</h1>'
        '<p>Hier findest du die nächsten Termine und Neuigkeiten aus dem Verein.</p></div><a class="secondary-button" href="/logout.php">Abmelden</a></div>'
        '<section class="summary-grid"><article class="summary-card"><span class="summary-icon blue">⚽</span><span class="summary-label">Mitglieder</span><strong>84</strong><small>Davon 19 Jugendliche</small></article>'
        '<article class="summary-card"><span class="summary-icon green">✓</span><span class="summary-label">Nächstes Training</span><strong>' + _html_escape(next_date) + '</strong><small>' + _html_escape(next_team + " · " + next_detail) + '</small></article>'
        '<article class="summary-card"><span class="summary-icon amber">◷</span><span class="summary-label">Nächster Spieltag</span><strong>Samstag</strong><small>Heimspiel · 15:00 Uhr</small></article></section>'
        '<section class="content-card games-card" id="spiele"><div class="section-heading"><div><span class="eyebrow">SAISON 2026/27</span><h2>Spiele und Tabellen</h2></div><a href="/training.php">Alle Termine</a></div>'
        + _games_and_tables_html(session) + '</section>'
    )
    return _page("Mitgliederbereich", body, "dashboard-page")


def _season_leagues() -> dict[str, dict[str, object]]:
    return {
        "1. Mannschaft · Kreisklasse": {
            "teams": ["SV Eichenwacht", "TSV Lindenau", "FC Mühlenrode", "TuS Falkenried", "TSV Birkenau", "SG Waldkirchen", "SV Dorfhain", "JSG Fichtenau", "SC Talheim", "TSV Oberdorf", "SV Kappel", "FC Hinterried"],
            "dates": ["16.08.2026", "23.08.2026", "06.09.2026", "20.09.2026", "04.10.2026", "25.10.2026", "08.11.2026", "22.11.2026", "06.12.2026", "20.12.2026", "10.01.2027"],
            "club_scores": [(3, 1), (2, 2), (1, 0), (2, 1), (0, 1), None, None, None, None, None, None],
            "club_cards": [(2, 0, 1, 0), (1, 0, 3, 0), (2, 0, 2, 1), (1, 0, 2, 0), (3, 1, 1, 0), *[(0, 0, 0, 0)] * 6],
        },
        "Jugend U17 · Herbststaffel": {
            "teams": ["SV Eichenwacht U17", "JSG Höhenkirchen", "TSV Lindenau", "SV Kappel", "FC Mühlenrode", "TSV Birkenau", "TuS Falkenried", "SG Waldkirchen", "SV Dorfhain", "JSG Fichtenau", "SC Talheim", "TSV Oberdorf"],
            "dates": ["22.08.2026", "29.08.2026", "05.09.2026", "19.09.2026", "03.10.2026", "24.10.2026", "07.11.2026", "21.11.2026", "05.12.2026", "19.12.2026", "09.01.2027"],
            "club_scores": [(2, 2), (3, 0), (4, 1), (1, 0), (1, 2), None, None, None, None, None, None],
            "club_cards": [(1, 0, 2, 0), (2, 0, 1, 1), (1, 0, 3, 0), (2, 0, 2, 0), (2, 1, 1, 0), *[(0, 0, 0, 0)] * 6],
        },
        "Jugend U15 · Qualifikationsrunde": {
            "teams": ["SV Eichenwacht U15", "JSG Fichtenau", "SC Talheim", "TSV Oberdorf", "SV Kappel", "FC Hinterried", "TSV Lindenau", "SV Dorfhain", "SG Waldkirchen", "TuS Falkenried", "TSV Birkenau", "FC Mühlenrode"],
            "dates": ["23.08.2026", "30.08.2026", "06.09.2026", "20.09.2026", "04.10.2026", "25.10.2026", "08.11.2026", "22.11.2026", "06.12.2026", "20.12.2026", "10.01.2027"],
            "club_scores": [(1, 0), (2, 1), (2, 2), (0, 1), (3, 1), None, None, None, None, None, None],
            "club_cards": [(2, 0, 1, 0), (1, 0, 2, 0), (3, 0, 1, 0), (2, 1, 2, 0), (1, 0, 3, 0), *[(0, 0, 0, 0)] * 6],
        },
    }


def _club_calendar_events(session: dict[str, object] | None = None) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    kickoffs = {"1. Mannschaft · Kreisklasse": "15:00", "Jugend U17 · Herbststaffel": "11:00", "Jugend U15 · Qualifikationsrunde": "11:00"}
    for league_index, (competition, league) in enumerate(_season_leagues().items()):
        teams = league["teams"]
        rotation = list(teams)
        for round_index, date_text in enumerate(league["dates"]):
            for pair_index in range(len(teams) // 2):
                home, away = rotation[pair_index], rotation[-pair_index - 1]
                if round_index % 2:
                    home, away = away, home
                if home == teams[0] or away == teams[0]:
                    score = league["club_scores"][round_index]
                    if score is not None and home != teams[0]:
                        score = (score[1], score[0])
                    cards = league["club_cards"][round_index]
                    if home != teams[0]:
                        cards = (cards[2], cards[3], cards[0], cards[1])
                    events.append({"id": f"game-{league_index}-{round_index}", "title": f"Spieltag · {home} – {away}", "date": date_text, "time": kickoffs[competition], "team": competition.split(" · ")[0], "game": "1", "home": home, "away": away, "score": "" if score is None else f"{score[0]}:{score[1]}", "yellow_home": str(cards[0]), "red_home": str(cards[1]), "yellow_away": str(cards[2]), "red_away": str(cards[3])})
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    for day, team, detail in _next_training_dates():
        date_text = day.split(", ", 1)[1]
        clock, place = detail.split(" · ", 1)
        events.append({"id": f"training-{len(events)}", "title": f"Training · {team}", "date": date_text, "time": clock, "team": place})
    events.extend([
        {"id": "club-meeting", "title": "Mitgliederversammlung", "date": "13.11.2026", "time": "19:30", "team": "Vereinsleben"},
        {"id": "club-tournament", "title": "Jugend-Hallenturnier", "date": "05.12.2026", "time": "10:00", "team": "Jugend"},
    ])
    if session is not None:
        deleted = set(session.get("deleted_events", []))
        edits = session.get("managed_event_edits", {})
        if not isinstance(edits, dict):
            edits = {}
        events = [edits.get(item["id"], item) for item in events if item["id"] not in deleted]
        for item in events:
            if item.get("game") == "1":
                item["title"] = f"Spieltag · {item.get('home', '')} – {item.get('away', '')}"
        stored = session.get("managed_events", [])
        if isinstance(stored, list):
            events.extend(item for item in stored if isinstance(item, dict) and str(item.get("id", "")) not in deleted)
    return sorted(events, key=lambda item: (datetime.strptime(item["date"], "%d.%m.%Y"), item["time"], item["title"]))


def _games_and_tables_html(session: dict[str, object] | None = None) -> str:
    today = date(2026, 10, 20)
    leagues = _season_leagues()
    overrides = {event["id"]: event for event in _club_calendar_events(session) if event.get("game") == "1"}
    sections = []
    for competition, league in leagues.items():
        teams = league["teams"]
        table = {name: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "for": 0, "against": 0, "points": 0} for name in teams}
        shown_games = []
        rotation = list(teams)
        for round_index, date_text in enumerate(league["dates"]):
            match_day = datetime.strptime(date_text, "%d.%m.%Y").date()
            for pair_index in range(len(teams) // 2):
                home = rotation[pair_index]
                away = rotation[-pair_index - 1]
                if round_index % 2:
                    home, away = away, home
                is_club_match = home == teams[0] or away == teams[0]
                event_id = f"game-{list(leagues).index(competition)}-{round_index}"
                override = overrides.get(event_id, {})
                if is_club_match:
                    home = str(override.get("home", home))
                    away = str(override.get("away", away))
                if is_club_match:
                    club_score = league["club_scores"][round_index]
                    if override.get("score", ""):
                        try:
                            score = tuple(int(part) for part in str(override["score"]).replace("-", ":").split(":", 1))
                        except (ValueError, TypeError):
                            score = club_score
                    elif club_score is None:
                        score = None
                    elif home == teams[0]:
                        score = club_score
                    else:
                        score = (club_score[1], club_score[0])
                    yellow_home, red_home, yellow_away, red_away = league["club_cards"][round_index]
                    cards = (yellow_home, red_home, yellow_away, red_away) if home == teams[0] else (yellow_away, red_away, yellow_home, red_home)
                    if override:
                        cards = tuple(int(override.get(key, default)) for key, default in zip(("yellow_home", "red_home", "yellow_away", "red_away"), cards))
                else:
                    score = None if match_day >= today else ((round_index + pair_index * 2) % 4, (round_index * 2 + pair_index + 1) % 4)
                    cards = (0, 0, 0, 0)
                if score is not None:
                    hg, ag = score
                    if home not in table:
                        table[home] = {"played": 0, "won": 0, "drawn": 0, "lost": 0, "for": 0, "against": 0, "points": 0}
                    if away not in table:
                        table[away] = {"played": 0, "won": 0, "drawn": 0, "lost": 0, "for": 0, "against": 0, "points": 0}
                    h, a = table[home], table[away]
                    h["played"] += 1
                    a["played"] += 1
                    h["for"] += hg
                    h["against"] += ag
                    a["for"] += ag
                    a["against"] += hg
                    if hg > ag:
                        h["won"] += 1
                        a["lost"] += 1
                        h["points"] += 3
                    elif hg < ag:
                        a["won"] += 1
                        h["lost"] += 1
                        a["points"] += 3
                    else:
                        h["drawn"] += 1
                        a["drawn"] += 1
                        h["points"] += 1
                        a["points"] += 1
                if is_club_match:
                    shown_games.append((date_text, home, away, score, cards))
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
        standings = sorted(table.items(), key=lambda item: (-item[1]["points"], -(item[1]["for"] - item[1]["against"]), -item[1]["for"], item[0]))
        table_rows = "".join(
            "<tr><td>" + str(pos) + "</td><td>" + _html_escape(name) + "</td><td>" + str(stats["played"]) + "</td><td>" + str(stats["won"]) + "</td><td>" + str(stats["drawn"]) + "</td><td>" + str(stats["lost"]) + "</td><td>" + str(stats["for"]) + ":" + str(stats["against"]) + "</td><td><strong>" + str(stats["points"]) + "</strong></td></tr>"
            for pos, (name, stats) in enumerate(standings, 1)
        )
        game_rows = "".join(
            "<tr><td>" + _html_escape(match_date) + "</td><td>" + _html_escape(home) + _cards_badges(cards[0], cards[1]) + "</td><td>" + _html_escape(away) + _cards_badges(cards[2], cards[3]) + "</td><td class=\"score-cell\">" + (str(score[0]) + " : " + str(score[1]) if score is not None else "– : –") + "</td></tr>"
            for match_date, home, away, score, cards in shown_games
        )
        sections.append(
            "<div class=\"league-section\"><h3>" + _html_escape(competition) + "</h3><div class=\"league-columns\">"
            "<div class=\"league-table-wrap\"><table class=\"league-table\"><thead><tr><th>#</th><th>Mannschaft</th><th>Sp</th><th>S</th><th>U</th><th>N</th><th>Tore</th><th>Pkt</th></tr></thead><tbody>" + table_rows + "</tbody></table></div>"
            "<div class=\"fixtures-table-wrap\"><table class=\"fixtures-table\"><thead><tr><th>Datum</th><th>Heim</th><th>Gast</th><th>Ergebnis</th></tr></thead><tbody>" + game_rows + "</tbody></table></div></div></div>"
        )
    return "".join(sections) + '<p class="table-note">Tabellenstand aus den erfundenen Ergebnissen; zukünftige Spiele ohne Ergebnis.</p>'


def _cards_badges(yellow: int, red: int) -> str:
    badges = ""
    if yellow:
        badges += '<span class="yellow-card" title="Gelbe Karten">' + str(yellow) + '</span>'
    if red:
        badges += '<span class="red-card" title="Rote Karten">' + str(red) + '</span>'
    return '<span class="match-cards" aria-label="Gelbe und rote Karten">' + badges + '</span>' if badges else ""


def _next_training_dates() -> list[tuple[str, str, str]]:
    """Build a rolling three-month schedule for the club teams."""
    now = datetime.now().astimezone()
    today = now.date()
    end_date = today + timedelta(days=90)
    schedule = [
        (1, "1. Mannschaft", "Sportplatz Eichenwacht", "18:30 Uhr"),
        (1, "Jugend U15", "Nebenplatz", "17:00 Uhr"),
        (2, "Turnen", "Turnhalle Eichenwacht", "19:00 Uhr"),
        (3, "Alte Herren", "Sportplatz Eichenwacht", "19:00 Uhr"),
        (4, "Jugend U17", "Sportplatz Eichenwacht", "17:30 Uhr"),
        (5, "Jugend U11", "Sportplatz Eichenwacht", "10:00 Uhr"),
    ]
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    events: list[tuple[str, str, str]] = []
    for weekday, team, place, clock in schedule:
        days_ahead = (weekday - today.weekday()) % 7
        day = today + timedelta(days=days_ahead)
        if days_ahead == 0 and now.strftime("%H:%M") >= clock[:5]:
            day += timedelta(days=7)
        while day <= end_date:
            date_label = f"{weekdays[day.weekday()]}, {day.strftime('%d.%m.%Y')}"
            events.append((date_label, team, f"{clock} · {place}"))
            day += timedelta(days=7)
    return sorted(events, key=lambda event: (datetime.strptime(event[0].split(", ", 1)[1], "%d.%m.%Y"), event[2], event[1]))


def _training_html(session: dict[str, object] | None = None) -> str:
    rows = "".join('<div class="activity-row"><span class="activity-marker green-marker"></span><span><strong>' + _html_escape(day) + " · " + _html_escape(team) + "</strong><small>" + _html_escape(detail) + "</small></span></div>" for day, team, detail in _next_training_dates())
    other_events = [event for event in _club_calendar_events(session) if not event["id"].startswith("training-") and datetime.strptime(event["date"], "%d.%m.%Y").date() >= date(2026, 10, 20)]
    other_rows = "".join('<div class="activity-row"><span class="activity-marker"></span><span><strong>' + _html_escape(event["date"] + " · " + event["title"]) + '</strong><small>' + _html_escape(event["time"] + " Uhr · " + event["team"]) + '</small></span></div>' for event in other_events)
    body = '<div class="dashboard-heading"><div><span class="eyebrow">TERMINE</span><h1>Training & Termine</h1><p>Trainingsplan, Spieltage und Vereinsveranstaltungen im gemeinsamen Kalender.</p></div><a class="secondary-button" href="/dashboard.php">Zurück</a></div><section class="content-card"><div class="section-heading"><div><span class="eyebrow">ROLLIERENDER PLAN</span><h2>Trainingsplan · nächste drei Monate</h2></div></div>' + rows + '<div class="admin-footnote">Bei Änderungen bitte kurz in die Mannschaftsgruppe schreiben.</div></section><section class="content-card"><span class="eyebrow">SPIELTAGE & VEREIN</span><h2>Weitere Termine</h2>' + other_rows + '</section>'
    return _page("Training & Termine", body, "dashboard-page")


def _members_html(search: str = "", page: int = 1) -> str:
    return _useradmin_html(search, page, admin=False)


def _blackboard_html() -> str:
    next_game = next((event for event in _club_calendar_events() if event["id"].startswith("game-") and datetime.strptime(event["date"], "%d.%m.%Y").date() >= date(2026, 10, 20)), None)
    game_row = ""
    if next_game:
        game_row = '<div class="activity-row"><span class="activity-marker"></span><span><strong>' + _html_escape(next_game["title"]) + '</strong><small>' + _html_escape(next_game["date"] + " · Anstoß " + next_game["time"] + " Uhr") + '</small></span></div>'
    body = ('<div class="dashboard-heading"><div><span class="eyebrow">VEREINSLEBEN</span><h1>Schwarzes Brett</h1><p>Neuigkeiten, Termine und kleine Helfergesuche.</p></div><a class="secondary-button" href="/dashboard.php">Zurück</a></div>'
        '<section class="content-card"><div class="activity-row"><span class="activity-marker"></span><span><strong>Mitgliederversammlung: Rückmeldung erbeten</strong><small>Vorstand · 18. Oktober 2026 · Bitte bis 6. November Bescheid geben</small></span></div><div class="activity-row"><span class="activity-marker green-marker"></span><span><strong>Neue Trainingszeiten ab November</strong><small>Fußball · 16. Oktober 2026 · Dienstag 18:30 Uhr, Donnerstag 19:00 Uhr</small></span></div><div class="activity-row"><span class="activity-marker"></span><span><strong>Mitgliederversammlung</strong><small>Freitag, 13. November 2026 · 19:30 Uhr im Sportheim</small></span></div>' + game_row + '<div class="activity-row"><span class="activity-marker green-marker"></span><span><strong>Jugend-Hallenturnier</strong><small>Samstag, 5. Dezember 2026 · Helfer für den Aufbau gesucht</small></span></div><div class="activity-row"><span class="activity-marker"></span><span><strong>Trikotsätze zurückgeben</strong><small>Bitte bis Ende des Monats bei Thomas abgeben.</small></span></div></section>')
    return _page("Schwarzes Brett", body, "dashboard-page")


def _resolve_fake_path(cwd: str, value: str) -> str:
    if value == "~":
        return "/home/admin"
    if value.startswith("~/"):
        return posixpath.normpath("/home/admin/" + value[2:])
    if value.startswith("/"):
        return posixpath.normpath(value)
    return posixpath.normpath(posixpath.join(cwd, value or "."))


def _uploaded_execution_attempt(session: dict[str, object], raw_command: str) -> str | None:
    """Identify attempts to run an uploaded file without executing its contents."""
    cwd = str(session.get("terminal_cwd", "/home/admin"))
    known_names: set[str] = set()
    uploads = session.get("uploaded_files", [])
    upload_items = list(uploads) if isinstance(uploads, list) else []
    with _SESSION_LOCK:
        upload_items.extend(HONEYPOT_UPLOADS)
    for item in upload_items:
        if isinstance(item, dict) and item.get("name"):
            known_names.add(posixpath.basename(str(item["name"])))
    if not known_names:
        return None

    try:
        lexer = shlex.shlex(raw_command, posix=True, punctuation_chars="|;&><")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None

    # Split command chains just enough to inspect each argv. This parser never
    # invokes a shell or evaluates command substitutions.
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"|", ";", "&&", "||"}:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    interpreters = {"php", "bash", "sh", "dash", "zsh", "python", "python2", "python3", "node", "perl", "ruby"}
    command_cwd = cwd
    for argv in segments:
        if not argv:
            continue
        executable = posixpath.basename(argv[0])
        args = argv[1:]
        if executable == "cd":
            if args:
                command_cwd = _resolve_fake_path(command_cwd, args[0])
            else:
                command_cwd = "/home/admin"
            continue
        # `source file` and `. file` are shell execution forms too.
        if executable in {"source", "."}:
            candidates = args[:1]
        elif executable in interpreters:
            if executable == "php" and "-l" in args:
                continue  # Syntax checks inspect the file without running it.
            candidates = [arg for arg in args if not arg.startswith("-")]
        else:
            # A direct invocation (./file, /path/file, or a file in cwd) is
            # an execution attempt. chmod/cat/less/etc. are inspection/setup.
            if executable in {"chmod", "chown", "cat", "less", "more", "head", "tail", "grep", "find", "file", "stat", "wc", "ls", "cp", "mv", "rm", "touch", "sha256sum", "md5sum"}:
                continue
            candidates = [argv[0]] if "/" in argv[0] or posixpath.splitext(argv[0])[1] in {".php", ".sh", ".py", ".pl", ".rb", ".js"} else []

        for candidate in candidates:
            if not candidate or candidate.startswith("-"):
                continue
            target = _resolve_fake_path(command_cwd, candidate)
            if posixpath.basename(target) not in known_names:
                continue
            if target.startswith(("/home/admin/uploads/", "/var/www/sv-eichenwacht/public/uploads/")):
                return posixpath.basename(target)
    return None


def _fake_terminal_command(session: dict[str, object], raw_command: str) -> str:
    """Run commands against a tiny in-memory Linux-like filesystem, never the host."""
    command = raw_command.strip()
    if not command:
        return ""
    shell_env = {
        "HOME": "/home/admin",
        "USER": "admin",
        "SHELL": "/bin/bash",
        "PWD": str(session.get("terminal_cwd", "/home/admin")),
        "CLUB_NAME": "SV Eichenwacht",
        "SITE_URL": "https://cloud.krokolani.de",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_DB": "sv_eichenwacht",
    }
    custom_env = session.get("terminal_env", {})
    if isinstance(custom_env, dict):
        shell_env.update({str(key): str(value) for key, value in custom_env.items()})
    command = re.sub(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
        lambda match: shell_env.get(match.group(1) or match.group(2), ""),
        command,
    )

    # Support familiar command chaining and pipes, but send every segment to our
    # allowlisted simulator. No shell, process, network, or host filesystem calls.
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&><")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError as exc:
        return f"bash: {exc}"
    segments: list[tuple[list[str], str]] = []
    current: list[str] = []
    connector = ";"
    for token in tokens:
        if token in {"|", ";", "&&", "||"}:
            if current:
                segments.append((current, connector))
                current = []
            connector = token
        else:
            current.append(token)
    if current:
        segments.append((current, connector))
    if not segments:
        return ""

    cwd = str(session.get("terminal_cwd", "/home/admin"))
    dirs = {
        "/", "/home", "/home/admin", "/home/admin/scripts", "/home/admin/backups", "/home/admin/uploads",
        "/var", "/var/www", "/var/www/sv-eichenwacht", "/var/www/sv-eichenwacht/public",
        "/var/www/sv-eichenwacht/public/uploads", "/var/www/sv-eichenwacht/storage",
        "/var/www/sv-eichenwacht/storage/logs", "/etc", "/etc/php", "/etc/php/8.2",
        "/etc/php/8.2/fpm", "/tmp", "/usr", "/usr/bin", "/bin",
    }
    session_dirs = session.setdefault("terminal_directories", [])
    if isinstance(session_dirs, list):
        dirs.update(str(path) for path in session_dirs)
    files = {
        "/home/admin/README.txt": "SV Eichenwacht e.V.\nKleine Vereinsseite, betreut in der Freizeit.\nWebmaster: admin\nHomepage: https://cloud.krokolani.de\n",
        "/home/admin/scripts/backup.sh": "#!/bin/sh\n# Vereinsseite sichern\ntar -czf /home/admin/backups/Vereinssicherung.tar.gz /var/www/sv-eichenwacht\n",
        "/home/admin/backups/Vereinssicherung_2026-10-18.tar.gz": "[binary backup archive]\n",
        "/var/www/sv-eichenwacht/.env": "CLUB_NAME=SV Eichenwacht\nSITE_URL=https://cloud.krokolani.de\nADMIN_USER=admin\nADMIN_PASS=Az44O6GRuZhJbJYlmlEy\nMYSQL_HOST=127.0.0.1\nMYSQL_DB=sv_eichenwacht\nMYSQL_USER=verein_web\nMYSQL_PASS=Eichenwacht-Db-2026!\nMAIL_TO=vorstand@sv-eichenwacht.example\nUPLOAD_DIR=/var/www/sv-eichenwacht/public/uploads\nBACKUP_DIR=/var/www/sv-eichenwacht/backups\n",
        "/var/www/sv-eichenwacht/public/index.php": "<?php\n// Vereinsseite\nrequire __DIR__ . '/../config.php';\n",
        "/var/www/sv-eichenwacht/config.php": "<?php\n// Einfache Konfiguration der Vereinsseite\n$dbHost = '127.0.0.1';\n$dbName = 'sv_eichenwacht';\n$dbUser = 'verein_web';\n",
        "/etc/php/8.2/fpm/php.ini": "memory_limit = 256M\nupload_max_filesize = 64M\npost_max_size = 72M\ndisplay_errors = Off\n",
        "/var/www/sv-eichenwacht/storage/logs/portal.log": "[2026-10-18 20:12:04] production.INFO: Mitgliederbereich aufgerufen\n",
    }
    virtual_files = session.setdefault("terminal_files", {})
    if not isinstance(virtual_files, dict):
        virtual_files = {}
        session["terminal_files"] = virtual_files
    files.update({path: str(content) for path, content in virtual_files.items()})
    uploads = session.get("uploaded_files", [])
    upload_items = list(uploads) if isinstance(uploads, list) else []
    with _SESSION_LOCK:
        upload_items.extend(HONEYPOT_UPLOADS)
    for item in upload_items:
        if isinstance(item, dict) and item.get("name"):
            content = item.get("content") or f"[uploaded file: {item['name']}]\n"
            files[f"/var/www/sv-eichenwacht/public/uploads/{item['name']}"] = str(content)
            files[f"/home/admin/uploads/{item['name']}"] = str(content)

    def run(argv: list[str], stdin: str = "") -> str:
        nonlocal cwd
        name, args = argv[0], argv[1:]
        allowed = {
            "php", "ls", "pwd", "cd", "whoami", "id", "uname", "hostname", "date", "uptime", "df", "free",
            "cat", "less", "more", "head", "tail", "wc", "env", "printenv", "export", "which", "whereis",
            "file", "stat", "du", "find", "grep", "ps", "top", "systemctl", "service", "history", "echo",
            "printf", "clear", "help", "composer", "git", "sudo", "touch", "mkdir", "rm", "cp", "mv",
            "chmod", "chown", "curl", "wget", "tar", "gzip", "unzip", "nginx", "python3", "node", "true",
            "false", "test", "apt", "dpkg",
        }
        if name not in allowed:
            return f"bash: {name}: command not found"
        if name == "help":
            return "Common commands: ls, cd, pwd, cat, less, head, tail, grep, find, wc, touch, mkdir, cp, mv, rm, chmod, php -v, php --version, php -m, composer --version, git status, curl, wget, tar, whoami, id, uname -a, df -h, free -h, ps, top, systemctl status, env, export, history, clear"
        if name == "clear":
            session["terminal_history"] = []
            return ""
        if name == "pwd": return cwd
        if name == "cd":
            target_arg = args[0] if args else "/home/admin"
            target = str(session.get("terminal_previous_cwd", "/home/admin")) if target_arg == "-" else _resolve_fake_path(cwd, target_arg)
            if target not in dirs: return f"bash: cd: {target_arg}: No such file or directory"
            session["terminal_previous_cwd"] = cwd
            cwd = target
            session["terminal_cwd"] = target
            return ""
        if name in {"whoami", "id", "hostname"}:
            return {"whoami": "admin", "id": "uid=1001(admin) gid=1001(admin) groups=1001(admin),33(www-data)", "hostname": "sv-web01"}[name]
        if name == "uname": return "Linux sv-web01 6.1.0-21-amd64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux" if "-a" in args else "Linux"
        if name == "date": return datetime.now().astimezone().strftime("%a %b %d %H:%M:%S %Z %Y")
        if name == "uptime": return " 20:14:02 up 38 days,  4:17,  1 user,  load average: 0.08, 0.05, 0.01"
        if name == "df": return "Filesystem      Size  Used Avail Use% Mounted on\n/dev/vda1        40G   11G   27G  29% /\ntmpfs           256M  1.2M  255M   1% /tmp"
        if name == "free": return "               total        used        free      shared  buff/cache   available\nMem:           3.8Gi       1.1Gi       1.4Gi        42Mi       1.3Gi       2.5Gi\nSwap:          1.0Gi          0B       1.0Gi"
        if name in {"env", "printenv", "export"}:
            env = {"HOME": "/home/admin", "USER": "admin", "SHELL": "/bin/bash", "PWD": cwd, "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "CLUB_NAME": "SV Eichenwacht", "SITE_URL": "https://cloud.krokolani.de", "ADMIN_USER": "admin", "MYSQL_HOST": "127.0.0.1", "MYSQL_DB": "sv_eichenwacht", "MYSQL_USER": "verein_web", "UPLOAD_DIR": "/var/www/sv-eichenwacht/public/uploads", "BACKUP_DIR": "/var/www/sv-eichenwacht/backups"}
            custom = session.setdefault("terminal_env", {})
            if isinstance(custom, dict): env.update({str(k): str(v) for k, v in custom.items()})
            if name == "export":
                if not args: return "\n".join(f'declare -x {k}="{v}"' for k, v in env.items())
                for value in args:
                    if "=" in value:
                        key, val = value.split("=", 1)
                        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key): custom[key] = val
                return ""
            return env.get(args[0], "") if args else "\n".join(f"{k}={v}" for k, v in env.items())
        if name == "history":
            hist = session.get("terminal_history", [])
            return "\n".join(f"{i:4}  {entry.get('command', '')}" for i, entry in enumerate(hist, 1) if isinstance(entry, dict))
        if name == "echo": return " ".join(args) if args else stdin.rstrip("\n")
        if name == "printf":
            if not args: return ""
            output = args[0]
            vals = iter(args[1:])
            return re.sub(r"%[sdi]", lambda _m: str(next(vals, "")), output).replace(r"\n", "\n").replace(r"\t", "\t")
        if name == "php":
            if not args or args[0] in {"-v", "--version"}: return "PHP 8.2.12 (cli) (built: Oct 12 2026 09:18:42) (NTS)\nCopyright (c) The PHP Group\nZend Engine v4.2.12, Copyright (c) Zend Technologies\n    with Zend OPcache v8.2.12, Copyright (c), by Zend Technologies"
            if args[0] == "-m": return "[PHP Modules]\nbcmath\ncalendar\nCore\nctype\ncurl\ndate\ndom\nfileinfo\nfilter\ngd\niconv\njson\nlibxml\nmbstring\nmysqli\nmysqlnd\nopenssl\nPDO\npdo_mysql\npdo_sqlite\nPhar\nsession\nSimpleXML\nsodium\nSPL\nZend OPcache\nzip\nzlib\n\n[Zend Modules]\nZend OPcache"
            if args[0] == "--ini": return "Configuration File (php.ini) Path: /etc/php/8.2/cli\nLoaded Configuration File: /etc/php/8.2/cli/php.ini\nScan for additional .ini files in: /etc/php/8.2/cli/conf.d"
            target = _resolve_fake_path(cwd, args[-1])
            return f"No syntax errors detected in {target}" if args[0] == "-l" and target in files else ("SV Eichenwacht e.V." if target.endswith("index.php") and target in files else f"Could not open input file: {args[-1]}")
        if name == "ls":
            options = [a for a in args if a.startswith("-")]
            paths = [a for a in args if not a.startswith("-") and not a.startswith("--")]
            target = _resolve_fake_path(cwd, paths[-1]) if paths else cwd
            if target in files: return posixpath.basename(target)
            if target not in dirs: return f"ls: cannot access '{paths[-1] if paths else target}': No such file or directory"
            tree = {"/": ["home", "tmp", "usr", "var", "etc"], "/home": ["admin"], "/home/admin": ["README.txt", "backups", "scripts", "uploads"], "/home/admin/uploads": [], "/home/admin/scripts": ["backup.sh"], "/home/admin/backups": ["Vereinssicherung_2026-10-18.tar.gz"], "/var": ["www"], "/var/www": ["sv-eichenwacht"], "/var/www/sv-eichenwacht": [".env", "config.php", "public", "storage"], "/var/www/sv-eichenwacht/public": ["index.php", "uploads"], "/var/www/sv-eichenwacht/storage": ["logs"], "/var/www/sv-eichenwacht/storage/logs": ["portal.log"], "/etc": ["php"], "/etc/php": ["8.2"], "/etc/php/8.2": ["fpm"], "/etc/php/8.2/fpm": ["php.ini"], "/tmp": [], "/usr": ["bin"], "/usr/bin": ["php", "composer", "git", "curl", "wget", "python3", "node"], "/bin": ["bash", "cat", "ls", "grep", "find"]}
            entries = list(tree.get(target, [])) + [posixpath.basename(f) for f in files if posixpath.dirname(f) == target]
            entries += [posixpath.basename(f) for f in virtual_files if posixpath.dirname(f) == target]
            if target in {"/var/www/sv-eichenwacht/public/uploads", "/home/admin/uploads"}:
                entries += [posixpath.basename(path) for path in files if posixpath.dirname(path) == target]
            show_hidden = any(not o.startswith("--") and "a" in o[1:] for o in options) or "--all" in options
            entries = sorted(set(e for e in entries if show_hidden or not e.startswith(".")))
            if show_hidden: entries = [".", ".."] + entries
            if any("l" in o and not o.startswith("--") for o in options):
                return "total 24\n" + "\n".join(("drwxr-xr-x 2 admin www-data 4096 Oct 18 20:10 " if e in tree.get(target, []) else "-rw-r--r-- 1 admin www-data  842 Oct 18 20:10 ") + e for e in entries)
            return "  ".join(entries)
        if name in {"cat", "less", "more", "head", "tail", "wc", "grep"}:
            if name == "grep":
                operands = [a for a in args if not a.startswith("-")]
                file_arg = operands[1] if len(operands) > 1 else ""
            else:
                file_arg = next((a for a in reversed(args) if not a.startswith("-") and not a.isdigit()), "")
            path = _resolve_fake_path(cwd, file_arg) if file_arg else ""
            text = files.get(path, stdin if not file_arg else "")
            if not text and file_arg: return f"{name}: {file_arg}: No such file or directory"
            if name == "grep":
                pattern = next((a for a in args if not a.startswith("-")), "")
                lines = text.splitlines()
                if "-i" in args: lines = [line for line in lines if pattern.lower() in line.lower()]
                else: lines = [line for line in lines if pattern in line]
                return "\n".join(lines)
            if name in {"head", "tail"}:
                count = 10
                if "-n" in args:
                    try: count = max(0, min(200, int(args[args.index("-n") + 1])))
                    except (ValueError, IndexError): pass
                lines = text.splitlines()
                return "\n".join(lines[:count] if name == "head" else lines[-count:])
            if name == "wc": return f"{len(text.splitlines()):3} {len(text.split()):3} {len(text.encode()):4} {file_arg}" if file_arg else f"{len(text.splitlines()):3} {len(text.split()):3} {len(text.encode()):4}"
            return text
        if name == "find":
            roots = [a for a in args if not a.startswith("-") and a not in {"-name", "-type"}]
            root = _resolve_fake_path(cwd, roots[0]) if roots else cwd
            pattern = args[args.index("-name") + 1] if "-name" in args and args.index("-name") + 1 < len(args) else "*"
            candidates = [*dirs, *files, *virtual_files]
            candidates += [path for path in files if path.startswith(("/var/www/sv-eichenwacht/public/uploads/", "/home/admin/uploads/"))]
            return "\n".join(sorted(x for x in set(candidates) if (x == root or x.startswith(root.rstrip("/") + "/")) and fnmatch.fnmatch(posixpath.basename(x), pattern)))
        if name == "touch":
            if not args: return "touch: missing file operand"
            virtual_files.setdefault(_resolve_fake_path(cwd, args[-1]), "")
            return ""
        if name == "mkdir":
            if not args: return "mkdir: missing operand"
            target = _resolve_fake_path(cwd, args[-1])
            if "-p" not in args and posixpath.dirname(target) not in dirs: return f"mkdir: cannot create directory '{args[-1]}': No such file or directory"
            if "-p" in args:
                missing = []
                parent = target
                while parent and parent != "/" and parent not in dirs:
                    missing.append(parent)
                    parent = posixpath.dirname(parent)
                dirs.update(missing)
            else:
                dirs.add(target)
            if isinstance(session_dirs, list):
                session_dirs.extend(path for path in dirs if path not in session_dirs)
            return ""
        if name == "rm":
            if not args: return "rm: missing operand"
            target = _resolve_fake_path(cwd, args[-1])
            if target not in virtual_files: return f"rm: cannot remove '{args[-1]}': No such file or directory"
            del virtual_files[target]
            return ""
        if name in {"cp", "mv"}:
            if len(args) < 2: return f"{name}: missing file operand"
            source, dest = (_resolve_fake_path(cwd, x) for x in args[-2:])
            content = virtual_files.get(source, files.get(source))
            if content is None: return f"{name}: cannot stat '{args[-2]}': No such file or directory"
            virtual_files[dest] = content
            if name == "mv" and source in virtual_files: del virtual_files[source]
            return ""
        if name == "sudo": return "admin is not in the sudoers file. This incident will be reported."
        if name == "systemctl" or name == "service":
            service = args[-1] if args else ""
            label = "php8.2-fpm" if service in {"php-fpm", "php8.2-fpm"} else service
            if label in {"nginx", "php8.2-fpm"}: return f"● {label}.service - {'A high performance web server' if label == 'nginx' else 'The PHP 8.2 FastCGI Process Manager'}\n     Loaded: loaded (/lib/systemd/system/{label}.service; enabled)\n     Active: active (running) since Mon 2026-10-01 08:12:41 CEST"
            return f"Unit {service}.service could not be found."
        if name == "ps" or name == "top": return "USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\nroot           1  0.0  0.2  16840  9216 ?        Ss   Oct01   0:31 php-fpm: master process\nwww-data     184  0.1  1.4 284120 55248 ?        S    19:42   0:08 php-fpm: pool www\nwww-data     206  0.0  0.8  97284 32812 ?        S    19:45   0:02 nginx: worker process"
        if name == "which" or name == "whereis":
            paths = {"php": "/usr/bin/php", "composer": "/usr/bin/composer", "git": "/usr/bin/git", "curl": "/usr/bin/curl", "python3": "/usr/bin/python3", "node": "/usr/bin/node", "ls": "/usr/bin/ls"}
            return "\n".join(f"{arg}: {paths[arg]}" if name == "whereis" and arg in paths else paths[arg] for arg in args if arg in paths) or ""
        if name == "nginx": return "nginx version: nginx/1.24.0" if "-v" in args or "-V" in args else "nginx: configuration file /etc/nginx/nginx.conf test is successful"
        if name == "python3": return "Python 3.11.2" if args and args[0] in {"--version", "-V"} else "python3: can't open file: [Errno 2] No such file or directory"
        if name == "node": return "v20.11.1" if args and args[0] in {"--version", "-v"} else "Welcome to Node.js v20.11.1.\nType \".help\" for more information."
        if name == "composer": return "Composer version 2.7.9 2024-09-04 14:43:28\nPHP version 8.2.12 (/usr/bin/php8.2)" if "--version" in args or "-V" in args else "Composer could not find a composer.json file in " + cwd
        if name == "git": return "On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean" if args[:1] == ["status"] else "usage: git <command> [<args>]"
        if name in {"curl", "wget"}:
            url = next((a for a in args if a.startswith(("http://", "https://"))), "")
            if not url: return f"{name}: missing URL"
            if name == "wget": return "HTTP request sent, awaiting response... 200 OK\nLength: 1842 (1.8K) [text/html]\nSaving to: ‘index.php’\n\nindex.php saved [1842/1842]"
            return "<!doctype html>\n<html><title>SV Eichenwacht</title><body>Vereinsseite</body></html>"
        if name == "tar": return "verein/.env\nverein/public/index.php\nverein/storage/logs/portal.log" if any(a.startswith("-t") for a in args) else "tar: operation completed"
        if name == "unzip": return "Archive: verein-backup.zip\n  Length      Date    Time    Name\n      328  2026-10-18 20:10   .env\n     1842  2026-10-18 20:10   public/index.php" if "-l" in args else "Archive extracted."
        if name == "gzip": return "gzip: operation completed"
        if name in {"apt", "dpkg"}: return "Permission denied. Administrative privileges are required."
        if name == "file":
            target = _resolve_fake_path(cwd, args[-1]) if args else cwd
            return f"{target}: PHP script, ASCII text" if target.endswith(".php") else f"{target}: ASCII text"
        if name == "stat":
            target = _resolve_fake_path(cwd, args[-1]) if args else cwd
            return f"  File: {target}\n  Size: 842\tBlocks: 8\tIO Block: 4096 regular file\nAccess: (0644/-rw-r--r--)  Uid: (1001/admin)   Gid: (33/www-data)"
        if name == "du": return f"12K\t{_resolve_fake_path(cwd, args[-1] if args else '.') }"
        if name == "true" or name == "test": return ""
        if name == "false": return ""
        if name == "chmod" or name == "chown": return ""
        return f"bash: {name}: command not found"

    stdin = ""
    output = ""
    visible_output: list[str] = []
    previous_status = 0
    for index, (argv, connector) in enumerate(segments):
        if connector == "&&" and previous_status != 0: continue
        if connector == "||" and previous_status == 0: continue
        redirect = None
        append = False
        for operator in (">>", ">"):
            if operator in argv:
                redirect_index = argv.index(operator)
                if redirect_index + 1 < len(argv):
                    redirect = _resolve_fake_path(cwd, argv[redirect_index + 1])
                    append = operator == ">>"
                    argv = argv[:redirect_index]
                break
        output = run(argv, stdin if connector == "|" else "") if argv else ""
        if redirect:
            prior = str(virtual_files.get(redirect, "")) if append else ""
            virtual_files[redirect] = prior + output + ("\n" if output and not output.endswith("\n") else "")
            output = ""
        stdin = output
        previous_status = 1 if argv[:1] == ["false"] or output.startswith(("bash:", "ls:", "cat:", "rm:", "mkdir:")) else 0
        next_is_pipe = index + 1 < len(segments) and segments[index + 1][1] == "|"
        if not next_is_pipe and output:
            visible_output.append(output)
    return "\n".join(visible_output)


def _terminal_html(session: dict[str, object]) -> str:
    history = session.get("terminal_history", [])
    login_time = datetime.now().astimezone().strftime('%a %b %d %H:%M:%S %Z %Y')
    output = ['<div class="terminal-line">Linux sv-web01 6.1.0-21-amd64 #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux</div>', '<div class="terminal-line">Last login: ' + _html_escape(login_time) + ' from 192.0.2.44</div>', '<div class="terminal-line">&nbsp;</div>']
    if isinstance(history, list):
        for item in history[-30:]:
            if isinstance(item, dict):
                output.append('<div class="terminal-prompt">admin@sv-web01:' + _html_escape(str(item.get("cwd", "/home/admin"))) + '$ ' + _html_escape(str(item.get("command", ""))) + '</div>')
                if item.get("output"):
                    output.append('<pre class="terminal-result">' + _html_escape(str(item["output"])) + '</pre>')
    cwd = _html_escape(str(session.get("terminal_cwd", "/home/admin")))
    body = ('<div class="dashboard-heading"><div><span class="eyebrow">WEBMASTER · WARTUNG</span><h1>Vereinsserver</h1><p>Kleine Wartungskonsole für die Vereinsseite.</p></div><a class="secondary-button" href="/dashboard.php">Zurück zum Mitgliederbereich</a></div>'
        '<section class="terminal-shell"><div class="terminal-window"><div class="terminal-titlebar"><span class="terminal-icon">$_</span><strong>admin@sv-web01: ~</strong><span class="terminal-status">bash</span></div><div class="terminal-screen">' + "".join(output) + '</div>'
        '<form method="post" action="/tools/terminal.php" class="terminal-form"><label for="command">admin@sv-web01:' + cwd + '$</label><input id="command" name="command" autocomplete="off" autofocus spellcheck="false" aria-label="Befehl eingeben"></form></div>'
        '<p class="terminal-help">Zum Beispiel: <code>php -v</code>, <code>ls -la</code>, <code>cd /var/www/sv-eichenwacht</code>, <code>cat .env</code>, <code>find . -name "*.php"</code>, <code>ps aux</code>, <code>php -v | head -n 2</code>, <code>echo test &gt; /tmp/test.txt</code>. ↑/↓ zeigt frühere Eingaben.</p><script>(()=>{const i=document.getElementById("command"),s=document.querySelector(".terminal-screen");if(!i)return;const h=[...document.querySelectorAll(".terminal-prompt")].map(e=>e.textContent.split("$ ").slice(1).join("$ ")).filter(Boolean);let n=h.length;i.addEventListener("keydown",e=>{if(e.key==="ArrowUp"){e.preventDefault();if(n>0)n--;i.value=h[n]||""}else if(e.key==="ArrowDown"){e.preventDefault();if(n<h.length)n++;i.value=h[n]||""}});if(s)s.scrollTop=s.scrollHeight})()</script></section>')
    return _page("Terminal", body, "dashboard-page terminal-page")


def _useradmin_html(search: str = "", page: int = 1, admin: bool = True, mode: str = "", member_id: str = "", notice: str = "", session: dict[str, object] | None = None) -> str:
    members = [
        ("00017", "Weber, Martin", "12.04.1987", "1. Mannschaft", "01.07.2014", "Aktiv", "martin.weber@sv-eichenwacht.example"),
        ("00024", "Fischer, Sabine", "08.11.1974", "Vorstand", "01.03.2008", "Aktiv", "sabine.fischer@sv-eichenwacht.example"),
        ("00031", "Becker, Thomas", "22.02.1969", "Alte Herren", "01.04.1998", "Aktiv", "thomas.becker@sv-eichenwacht.example"),
        ("00048", "Richter, Jana", "19.06.2002", "Jugendleitung", "01.05.2021", "Aktiv", "jana.richter@sv-eichenwacht.example"),
        ("00053", "Schulz, Peter", "04.09.1958", "Fördernd", "01.01.2001", "Aktiv", "peter.schulz@sv-eichenwacht.example"),
        ("00061", "Yilmaz, Emre", "27.03.2011", "Jugend U15", "01.08.2020", "Aktiv", "familie.yilmaz@sv-eichenwacht.example"),
        ("00069", "Hoffmann, Laura", "15.12.1994", "Turnen", "01.09.2018", "Aktiv", "laura.hoffmann@sv-eichenwacht.example"),
        ("00074", "Neumann, Klaus", "30.01.1962", "Fördernd", "01.02.2023", "Beitrag offen", "klaus.neumann@sv-eichenwacht.example"),
        ("00081", "Krause, Finn", "09.08.2009", "Jugend U17", "01.06.2019", "Aktiv", "familie.krause@sv-eichenwacht.example"),
        ("00083", "Brandt, Nicole", "17.05.1981", "Turnen", "01.10.2016", "Aktiv", "nicole.brandt@sv-eichenwacht.example"),
    ]
    first_names = ["Anna", "Andreas", "Clara", "Daniel", "Elena", "Felix", "Greta", "Jan", "Lena", "Markus", "Miriam"]
    last_names = ["Ahrens", "Baumann", "Conrad", "Dietrich", "Engel", "Franke", "Günther"]
    departments = ["1. Mannschaft", "Jugend U11", "Jugend U15", "Jugend U17", "Turnen", "Fördernd", "Alte Herren"]
    for index in range(74):
        given = first_names[index % len(first_names)]
        surname = last_names[index // len(first_names)]
        department = departments[index % len(departments)]
        birth_year = 2009 + index % 6 if department.startswith("Jugend") else 1960 + index % 40
        birth_date = datetime(birth_year, 1 + index % 12, 1 + index % 27).strftime("%d.%m.%Y")
        joined = datetime(2005 + index % 21, 1 + (index * 3) % 12, 1 + (index * 5) % 27).strftime("%d.%m.%Y")
        status = "Beitrag offen" if index in {19, 47, 68} else "Aktiv"
        members.append((f"{85 + index:05d}", f"{surname}, {given}", birth_date, department, joined, status, f"{given.lower()}.{surname.lower()}@sv-eichenwacht.example"))

    if admin and session is not None:
        deleted = set(session.get("deleted_members", []))
        edits = session.get("member_edits", {})
        if not isinstance(edits, dict):
            edits = {}
        members = [edits.get(member[0], member) for member in members if member[0] not in deleted]
        added = session.get("added_members", [])
        if isinstance(added, list):
            members.extend(member for member in added if isinstance(member, tuple) and member[0] not in deleted)
    members.sort(key=lambda member: member[1].split(",", 1)[0].casefold())
    if admin and mode in {"new", "edit", "delete"}:
        selected = next((member for member in members if member[0] == member_id), None)
        if mode != "new" and selected is None:
            mode = "new"
        selected = selected or ("", "", "", "", "", "Aktiv", "")
        if mode == "delete":
            action_body = "".join([
                '<div class="dashboard-heading"><div><span class="eyebrow">MITGLIEDERREGISTER</span><h1>Mitglied löschen?</h1><p>',
                _html_escape(selected[1]), ' wird aus der Liste entfernt.</p></div></div>',
                '<section class="content-card action-form-card"><form method="post" action="/useradmin.php?mode=delete&id=',
                quote(selected[0], safe=""), '"><a class="secondary-button" href="/useradmin.php">Abbrechen</a> ',
                '<button class="danger-button" type="submit">Löschen</button></form></section>',
            ])
        else:
            mode_label = "Neues Mitglied" if mode == "new" else "Mitglied bearbeiten"
            action_body = "".join([
                '<div class="dashboard-heading"><div><span class="eyebrow">MITGLIEDERREGISTER</span><h1>', mode_label,
                '</h1><p>Mitgliedsdaten im Vereinsregister pflegen.</p></div></div>',
                '<section class="content-card action-form-card"><form method="post" action="/useradmin.php?mode=', mode,
                '&id=', quote(selected[0], safe=""), '" class="login-form">',
                '<label for="member-name">Name</label><input id="member-name" name="name" value="', _html_escape(selected[1]), '" required>',
                '<label for="member-email">E-Mail-Adresse</label><input id="member-email" name="email" type="email" value="', _html_escape(selected[6]), '" required>',
                '<label for="member-department">Abteilung</label><input id="member-department" name="department" value="', _html_escape(selected[3]), '" required>',
                '<label for="member-birth">Geburtsdatum</label><input id="member-birth" name="birth_date" value="', _html_escape(selected[2]), '" placeholder="TT.MM.JJJJ">',
                '<label for="member-joined">Eintritt</label><input id="member-joined" name="joined" value="', _html_escape(selected[4]), '" placeholder="TT.MM.JJJJ">',
                '<label for="member-status">Status</label><select id="member-status" name="status"><option>Aktiv</option><option',
                ' selected' if selected[5] == "Beitrag offen" else '', '>Beitrag offen</option></select>',
                '<div class="action-form-buttons"><a class="secondary-button" href="/useradmin.php">Abbrechen</a><button class="primary-button" type="submit">Speichern</button></div></form></section>',
            ])
        return _page("Mitgliederverwaltung", action_body, "dashboard-page useradmin-page")
    filtered = [member for member in members if search.casefold() in " ".join(member).casefold()] if search else members
    per_page = 8
    page_count = max(1, (len(filtered) + per_page - 1) // per_page)
    page = max(1, min(page, page_count))
    page_members = filtered[(page - 1) * per_page:page * per_page]
    rows = "".join(
        "<tr>" + "".join("<td>" + _html_escape(value) + "</td>" for value in member[:5])
        + '<td><span class="' + ("invite-pill" if member[5] == "Beitrag offen" else "status-pill") + '">'
        + _html_escape(member[5]) + '</span></td><td><a href="mailto:' + _html_escape(member[6])
        + '">Kontakt</a></td>' + (
            '<td class="row-actions"><a href="/useradmin.php?mode=edit&id=' + quote(member[0], safe="") + '">Bearbeiten</a><a class="delete-link" href="/useradmin.php?mode=delete&id=' + quote(member[0], safe="") + '">Löschen</a></td>' if admin else ''
        ) + '</tr>'
        for member in page_members
    )
    if not rows:
        rows = '<tr><td colspan="' + ("8" if admin else "7") + '" class="empty-members">Keine passenden Mitglieder gefunden.</td></tr>'
    start = (page - 1) * per_page + 1 if filtered else 0
    end = min(page * per_page, len(filtered))
    result_count = f"Einträge {start}–{end} von {len(filtered)}" if not search else f"{len(filtered)} Treffer"

    def page_link(target: int, label: str, extra_class: str = "") -> str:
        query = f"?page={target}" + ("&q=" + quote(search, safe="") if search else "")
        aria_current = ' aria-current="page"' if target == page else ""
        route = "/useradmin.php" if admin else "/mitglieder.php"
        return f'<a class="page-control {extra_class}" href="{route}{query}"{aria_current}>{label}</a>'



    title = "Mitgliederverwaltung" if admin else "Mitglieder"
    action_controls = '<a class="primary-button small-action" href="/useradmin.php?mode=new">+ Neu</a>' if admin else ''
    notice_html = '<div class="form-alert success-alert">' + _html_escape(notice) + '</div>' if notice else ''
    list_route = "/useradmin.php" if admin else "/mitglieder.php"
    columns = '<th>Nr.</th><th>Name</th><th>Geburtsdatum</th><th>Abteilung</th><th>Eintritt</th><th>Status</th><th>Kontakt</th>' + ('<th>Aktionen</th>' if admin else '')
    body = "".join([
        '<div class="dashboard-heading"><div><span class="eyebrow">VEREINSBÜRO</span><h1>' + title + '</h1><p>Mit Mannschaften und Kontakten im Blick behalten.</p></div><a class="secondary-button" href="/logout.php">Abmelden</a></div>',
        '<section class="summary-grid"><article class="summary-card"><span class="summary-icon blue">♙</span><span class="summary-label">Mitglieder gesamt</span><strong>84</strong><small>Aktueller Stand</small></article><article class="summary-card"><span class="summary-icon green">⚽</span><span class="summary-label">Aktive Spieler</span><strong>46</strong><small>3 Mannschaften</small></article><article class="summary-card"><span class="summary-icon amber">✉</span><span class="summary-label">Neue Anträge</span><strong>2</strong><small>Bitte Rückmeldung geben</small></article></section>',
        '<section class="content-card user-table-card"><div class="section-heading"><div><span class="eyebrow">MITGLIEDERREGISTER</span><h2>Mitgliederliste</h2></div>' + action_controls + '<span class="status-pill">84 Mitglieder</span></div>' + notice_html,
        '<form class="member-filter" method="get" action="' + list_route + '"><input name="q" value="' + _html_escape(search) + '" placeholder="Name, Mitgliedsnummer oder Mannschaft" aria-label="Mitglieder suchen"><button class="secondary-button" type="submit">Suchen</button></form>',
        '<div class="table-note">Sortiert nach Nachname</div><div class="user-table-wrap"><table class="user-table"><thead><tr>' + columns + '</tr></thead><tbody>' + rows + '</tbody></table></div>',
        '<nav class="table-pagination" aria-label="Seitennavigation"><span class="pagination-summary">' + result_count + '</span><div class="pagination-controls">' + page_link(max(1, page - 1), '‹ Zurück', 'is-disabled' if page == 1 else '') + '<span class="page-indicator">Seite ' + str(page) + ' von ' + str(page_count) + '</span>' + page_link(min(page_count, page + 1), 'Weiter ›', 'is-disabled' if page == page_count else '') + '</div></nav></section>',
        '<div class="admin-footnote"><span class="secure-dot"></span>Änderungen am Mitgliederbestand werden vom Vereinsbüro gepflegt.</div>',
    ])
    return _page(title, body, "dashboard-page useradmin-page")


def _files_html(session: dict[str, object]) -> str:
    uploaded_files = session.get("uploaded_files", [])
    uploaded_rows = "".join(
        '<div class="activity-row"><span class="activity-marker"></span><span><strong>'
        + _html_escape(str(item.get("name", "uploaded-package")))
        + '</strong><small>Gerade eben · Vereinsdatei</small></span>'
        + '<a class="secondary-button" href="/uploads/'
        + quote(str(item.get("name", "uploaded-package")), safe="")
        + '">Öffnen</a></div>'
        for item in reversed(uploaded_files)
        if isinstance(item, dict)
    )
    if not uploaded_rows:
        uploaded_rows = '<p class="card-intro">Noch keine Dateien hochgeladen.</p>'
    body = (
        '<div class="dashboard-heading"><div><span class="eyebrow">WEBMASTER</span><h1>Vereinsdateien</h1>'
        '<p>Unterlagen und Dateien für die Vereinsseite.</p></div><a class="secondary-button" href="/logout.php">Abmelden</a></div>'
        '<section class="content-card"><div class="section-heading"><div><span class="eyebrow">DATEIVERWALTUNG</span><h2>Unterlagen einreichen</h2></div><span class="status-pill">Vereinsbereich</span></div>'
        '<p class="card-intro">Fotos, Sicherungen und weitere Vereinsunterlagen können an das Vereinsbüro übermittelt werden.</p>'
        '<a class="primary-button" href="/files/upload.php">Datei einreichen <span aria-hidden="true">→</span></a></section>'
        '<section class="content-card"><div class="section-heading"><div><span class="eyebrow">VEREINSUNTERLAGEN</span><h2>Zuletzt abgelegte Unterlagen</h2></div><a href="/backups/import.php">Sicherung einspielen</a></div>'
        + uploaded_rows +
        '<div class="activity-row"><span class="activity-marker green-marker"></span><span><strong>Vereinssicherung_2026-10-18.tar.gz</strong><small>18.10.2026 · 248 MB · Bereit zum Einspielen</small></span></div>'
        '<div class="activity-row"><span class="activity-marker"></span><span><strong>Mannschaftsfotos_2026-10-12.zip</strong><small>12.10.2026 · 3,2 MB · Bereit zum Einspielen</small></span></div></section>'
    )
    return _page("Vereinsdateien", body, "dashboard-page files-page")


def _uploaded_filename(body: bytes) -> str:
    match = re.search(rb'Content-Disposition:\s*form-data;[^\r\n]*?filename="?([^";\r\n]*)', body, re.IGNORECASE)
    if not match:
        return "uploaded-package"
    name = match.group(1).decode("utf-8", errors="replace").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip()
    return name[:180] or "uploaded-package"


def _uploaded_file_content(body: bytes) -> str:
    """Extract a bounded text preview of a multipart upload for the fake shell."""
    disposition = re.search(rb'Content-Disposition:\s*form-data;[^\r\n]*?filename="?[^";\r\n]*"?', body, re.IGNORECASE)
    if not disposition:
        return ""
    separator = body.find(b"\r\n\r\n", disposition.start())
    if separator < 0:
        return ""
    start = separator + 4
    end = body.find(b"\r\n--", start)
    payload = body[start:end] if end >= 0 else body[start:]
    text = payload[:65536].decode("utf-8", errors="replace")
    return "".join(char for char in text if char.isprintable() or char in "\r\n\t")


def _reset_html(message: str = "") -> str:
    notice = f'<div class="form-alert success-alert">{_html_escape(message)}</div>' if message else ""
    body = (
        '<section class="simple-card"><a class="back-link" href="/login.php">← Zurück zur Anmeldung</a>'
        '<div class="card-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4m0 0-3-3m3 3 3-3M5 11a7 7 0 1 0 2-5"/><path d="M5 4v4h4"/></svg></div>'
        '<span class="eyebrow">VEREINSBÜRO</span><h1>Passwort zurücksetzen</h1>'
        '<p class="card-intro">Gib deine E-Mail-Adresse ein. Wenn ein Zugang besteht, schicken wir dir weitere Informationen.</p>'
        f'{notice}<form method="post" class="login-form"><label for="email">E-Mail-Adresse</label><input id="email" name="email" type="email" autocomplete="email" required placeholder="name@example.de">'
        '<button class="primary-button" type="submit">Weiter <span aria-hidden="true">→</span></button></form></section>'
    )
    return _page("Passwort zurücksetzen", body, "auth-page")


def _impressum_html() -> str:
    body = (
        '<section class="simple-card legal-card"><a class="back-link" href="/">← Zur Anmeldung</a>'
        '<span class="eyebrow">VEREINSBÜRO</span><h1>Impressum</h1>'
        '<section class="notice-panel"><h2>Hinweis zur Website</h2><p>Diese Website ist eine bewusst fiktive Vereinsseite. Sie dient dazu, automatisierte Zugriffe und Botangriffe zu analysieren. Der dargestellte Verein und die gezeigten Inhalte sind erfunden.</p></section>'
        '<h2>Angaben gemäß § 5 DDG</h2><p>SV Eichenwacht e. V.<br>Mühlenweg 7<br>12345 Eichenwacht</p>'
        '<h2>Vertreten durch</h2><p>Den Vorstand, vertreten durch die Vorsitzende Jana Hoffmann.</p>'
        '<h2>Kontakt</h2><p>Telefon: 01234 567890<br>E-Mail: <a href="mailto:vorstand@sv-eichenwacht.example">vorstand@sv-eichenwacht.example</a></p>'
        '<h2>Registereintrag</h2><p>Vereinsregister: Amtsgericht Waldheim<br>Registernummer: VR 2188</p>'
        '<h2>Verantwortlich für den Inhalt</h2><p>Jana Hoffmann<br>Mühlenweg 7<br>12345 Eichenwacht</p></section>'
    )
    return _page("Impressum", body, "auth-page")


def _events_admin_html(session: dict[str, object], mode: str = "", event_id: str = "", notice: str = "") -> str:
    events = _club_calendar_events(session)
    selected = next((item for item in events if str(item.get("id", "")) == event_id), None)
    notice_html = '<div class="form-alert success-alert">' + _html_escape(notice) + '</div>' if notice else ""
    editor = ""
    if mode in {"new", "edit"}:
        if mode == "edit" and selected is None and events:
            selected = events[0]
        selected = selected or {"title": "", "date": "", "time": "", "team": ""}
        title = "Neuen Termin anlegen" if mode == "new" else "Termin bearbeiten"
        editor = "".join([
            '<section class="content-card event-editor"><div class="section-heading"><div><span class="eyebrow">TERMINVERWALTUNG</span><h2>', title, '</h2></div></div>',
            '<form method="post" action="/termine.php?mode=', mode, '&id=', quote(str(selected.get("id", "")), safe=""), '" class="login-form event-form">',
            '<label for="event-title">Bezeichnung</label><input id="event-title" name="title" value="', _html_escape(str(selected.get("title", ""))), '" required>',
            '<label for="event-date">Datum</label><input id="event-date" name="date" type="text" value="', _html_escape(str(selected.get("date", ""))), '" placeholder="TT.MM.JJJJ" required>',
            '<label for="event-time">Uhrzeit</label><input id="event-time" name="time" value="', _html_escape(str(selected.get("time", ""))), '" placeholder="15:00 Uhr" required>',
            '<label for="event-team">Mannschaft / Bereich</label><input id="event-team" name="team" value="', _html_escape(str(selected.get("team", ""))), '" required>',
            ('<fieldset class="game-result-fields"><legend>Spielangaben</legend>'
             '<label for="event-away">Gastmannschaft</label><input id="event-away" name="away" value="' + _html_escape(str(selected.get("away", ""))) + '" required>'
             '<label for="event-score">Ergebnis (Heim:Gast)</label><input id="event-score" name="score" value="' + _html_escape(str(selected.get("score", ""))) + '" placeholder="z. B. 2:1">'
             '<div class="event-card-fields"><label>Gelbe Karten Heim<input name="yellow_home" type="number" min="0" max="20" value="' + _html_escape(str(selected.get("yellow_home", "0"))) + '"></label><label>Rote Karten Heim<input name="red_home" type="number" min="0" max="10" value="' + _html_escape(str(selected.get("red_home", "0"))) + '"></label><label>Gelbe Karten Gast<input name="yellow_away" type="number" min="0" max="20" value="' + _html_escape(str(selected.get("yellow_away", "0"))) + '"></label><label>Rote Karten Gast<input name="red_away" type="number" min="0" max="10" value="' + _html_escape(str(selected.get("red_away", "0"))) + '"></label></div></fieldset>') if selected.get("game") == "1" else '',
            '<div class="action-form-buttons"><a class="secondary-button" href="/termine.php">Abbrechen</a><button class="primary-button" type="submit">Termin speichern</button></div></form></section>',
        ])
    elif mode == "delete":
        selected = selected or {"id": event_id, "title": "", "date": "", "time": "", "team": ""}
        editor = "".join([
            '<section class="content-card event-editor"><h2>Termin löschen?</h2><p>',
            _html_escape(str(selected.get("date", "")) + ' · ' + str(selected.get("title", ""))), '</p>',
            '<form method="post" action="/termine.php?mode=delete&id=', quote(str(selected.get("id", "")), safe=""), '">',
            '<a class="secondary-button" href="/termine.php">Abbrechen</a> <button class="danger-button" type="submit">Löschen</button></form></section>',
        ])
    rows = "".join(
        '<tr><td>' + _html_escape(str(item.get("date", ""))) + '</td><td>' + _html_escape(str(item.get("time", ""))) + '</td><td><strong>' + _html_escape(str(item.get("title", ""))) + '</strong><small class="table-subline">' + _html_escape(str(item.get("team", ""))) + '</small></td>'
        + '<td class="row-actions"><a href="/termine.php?mode=edit&id=' + quote(str(item.get("id", "")), safe="") + '">Bearbeiten</a><a class="delete-link" href="/termine.php?mode=delete&id=' + quote(str(item.get("id", "")), safe="") + '">Löschen</a></td></tr>'
        for item in events
    )
    body = "".join([
        '<div class="dashboard-heading"><div><span class="eyebrow">VEREINSBÜRO</span><h1>Terminverwaltung</h1><p>Training, Spiele und Vereinsveranstaltungen planen.</p></div></div>'
        + notice_html + editor,
        '<section class="content-card event-list"><div class="section-heading"><div><span class="eyebrow">KALENDER</span><h2>Termine bearbeiten</h2></div><a class="primary-button small-action" href="/termine.php?mode=new">+ Neuer Termin</a></div>'
        '<div class="user-table-wrap"><table class="user-table event-table"><thead><tr><th>Datum</th><th>Uhrzeit</th><th>Termin</th><th>Aktionen</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>',
    ])
    return _page("Terminverwaltung", body, "dashboard-page events-page")


def _contact_html(submitted: bool = False) -> str:
    if submitted:
        body = (
            '<section class="simple-card"><a class="back-link" href="/">← Zur Startseite</a>'
            '<div class="card-icon">✓</div><span class="eyebrow">KONTAKT</span><h1>Vielen Dank für deine Nachricht</h1>'
            '<p class="card-intro">Wir haben deine Anfrage erhalten und melden uns so bald wie möglich.</p>'
            '<a class="primary-button" href="/">Zur Startseite</a></section>'
        )
    else:
        body = (
            '<section class="simple-card contact-card"><a class="back-link" href="/">← Zur Startseite</a>'
            '<div class="card-icon">✉</div><span class="eyebrow">WIR HELFEN GERNE</span><h1>Kontakt</h1>'
            '<p class="card-intro">Du hast eine Frage zum Verein oder möchtest bei uns mitmachen? Schreib uns.</p>'
            '<form method="post" action="/kontakt.php" class="login-form">'
            '<label for="contact-name">Name</label><input id="contact-name" name="name" autocomplete="name" required placeholder="Vor- und Nachname">'
            '<label for="contact-email">E-Mail-Adresse</label><input id="contact-email" name="email" type="email" autocomplete="email" required placeholder="name@example.de">'
            '<label for="contact-subject">Betreff</label><input id="contact-subject" name="subject" required placeholder="Worum geht es?">'
            '<label for="contact-message">Nachricht</label><textarea id="contact-message" name="message" rows="6" required placeholder="Deine Nachricht an den Vorstand"></textarea>'
            '<label class="fake-captcha"><input type="checkbox" name="captcha" value="checked" required><span>Ich bin kein Roboter</span><span class="captcha-mark" aria-hidden="true">↻</span></label>'
            '<button class="primary-button" type="submit">Nachricht senden <span aria-hidden="true">→</span></button>'
            '</form><p class="card-footnote">Alternativ erreichst du den Vorstand unter <a href="mailto:vorstand@sv-eichenwacht.example">vorstand@sv-eichenwacht.example</a>.</p>'
            '<p class="card-footnote">Fotos oder Unterlagen für den Verein? <a href="/files/upload.php">Datei einreichen</a></p></section>'
        )
    return _page("Kontakt", body, "auth-page")


def _phpinfo_html() -> str:
    overview = [
        ("System", "Linux sv-web01 6.1.0 x86_64"), ("Build Date", "Oct 12 2026 09:18:42"),
        ("Build System", "Linux 6.1.0 x86_64"), ("Build Provider", "Debian"),
        ("Server API", "FPM/FastCGI"), ("Virtual Directory Support", "disabled"),
        ("Configuration File (php.ini) Path", "/etc/php/8.2/fpm"), ("Loaded Configuration File", "/etc/php/8.2/fpm/php.ini"),
        ("Scan this dir for additional .ini files", "/etc/php/8.2/fpm/conf.d"),
        ("Additional .ini files parsed", "10-mysqlnd.ini, 10-opcache.ini, 10-pdo.ini, 20-bcmath.ini, 20-calendar.ini, 20-ctype.ini, 20-curl.ini, 20-gd.ini, 20-mbstring.ini, 20-mysqli.ini, 20-pdo_mysql.ini, 20-zip.ini"),
        ("PHP API", "20220829"), ("PHP Extension", "20220829"), ("Zend Extension", "420220829"),
        ("Debug Build", "no"), ("Thread Safety", "disabled"), ("Zend Signal Handling", "enabled"),
        ("Zend Memory Manager", "enabled"), ("IPv6 Support", "enabled"), ("DTrace Support", "available, disabled"),
        ("Registered PHP Streams", "https, ftps, php, file, glob, data, http, ftp, phar, zip, compress.zlib"),
        ("Registered Stream Filters", "zlib.*, string.rot13, string.toupper, string.tolower, convert.*, consumed, dechunk, convert.iconv.*"),
        ("Zend Engine", "v4.2.12"), ("Zend OPcache", "v8.2.12"),
    ]
    server = [
        ("HTTP_HOST", "cloud.krokolani.de"), ("SERVER_NAME", "cloud.krokolani.de"), ("SERVER_ADDR", "172.20.0.8"),
        ("SERVER_PORT", "443"), ("REMOTE_ADDR", "203.0.113.42"), ("DOCUMENT_ROOT", "/var/www/sv-eichenwacht/public"),
        ("SCRIPT_FILENAME", "/var/www/sv-eichenwacht/public/phpinfo.php"), ("REQUEST_SCHEME", "https"), ("HTTPS", "on"),
        ("SERVER_SOFTWARE", "nginx/1.24.0"), ("GATEWAY_INTERFACE", "CGI/1.1"), ("REQUEST_METHOD", "GET"),
        ("REQUEST_URI", "/phpinfo.php"), ("SERVER_PROTOCOL", "HTTP/2.0"), ("PHP_SELF", "/phpinfo.php"),
    ]
    variables = [
        ("_ENV[CLUB_NAME]", "SV Eichenwacht"), ("_ENV[SITE_URL]", "https://cloud.krokolani.de"),
        ("_ENV[ADMIN_USER]", "admin"), ("_ENV[ADMIN_PASS]", "Az44O6GRuZhJbJYlmlEy"),
        ("_ENV[MYSQL_HOST]", "127.0.0.1"), ("_ENV[MYSQL_DB]", "sv_eichenwacht"),
        ("_ENV[MYSQL_USER]", "verein_web"), ("_ENV[MYSQL_PASS]", "Eichenwacht-Db-2026!"),
        ("_ENV[MAIL_TO]", "vorstand@sv-eichenwacht.example"),
        ("_ENV[UPLOAD_DIR]", "/var/www/sv-eichenwacht/public/uploads"),
        ("_ENV[BACKUP_DIR]", "/var/www/sv-eichenwacht/backups"),
    ]
    directives = {
        "Core": [("allow_url_fopen", "On", "On"), ("allow_url_include", "Off", "Off"), ("default_charset", "UTF-8", "UTF-8"), ("disable_functions", "exec, passthru, shell_exec, system", "exec, passthru, shell_exec, system"), ("display_errors", "Off", "Off"), ("error_reporting", "22527", "22527"), ("expose_php", "On", "On"), ("file_uploads", "On", "On"), ("max_execution_time", "120", "120"), ("max_input_time", "120", "120"), ("max_input_vars", "5000", "5000"), ("memory_limit", "256M", "256M"), ("open_basedir", "/var/www/sv-eichenwacht:/tmp", "/var/www/sv-eichenwacht:/tmp"), ("post_max_size", "72M", "72M"), ("upload_max_filesize", "64M", "64M"), ("upload_tmp_dir", "/var/www/sv-eichenwacht/storage/tmp", "/var/www/sv-eichenwacht/storage/tmp"), ("variables_order", "EGPCS", "EGPCS"), ("zend.assertions", "-1", "-1")],
        "date": [("date.timezone", "Europe/Berlin", "Europe/Berlin"), ("Default timezone", "Europe/Berlin", "Europe/Berlin"), ("timelib version", "2022.10", "2022.10")],
        "curl": [("cURL support", "enabled", "enabled"), ("cURL Information", "7.88.1", "7.88.1"), ("SSL Version", "OpenSSL/3.0.15", "OpenSSL/3.0.15"), ("Protocols", "dict, file, ftp, ftps, http, https, imap, imaps, mqtt, pop3, pop3s, smtp, smtps", "dict, file, ftp, ftps, http, https, imap, imaps, mqtt, pop3, pop3s, smtp, smtps")],
        "mysqli": [("MysqlI Support", "enabled", "enabled"), ("Client API library version", "mysqlnd 8.2.12", "mysqlnd 8.2.12"), ("Active Persistent Links", "0", "0"), ("Active Links", "0", "0"), ("mysqli.default_port", "3306", "3306"), ("mysqli.max_persistent", "Unlimited", "Unlimited"), ("mysqli.reconnect", "Off", "Off")],
        "PDO": [("PDO support", "enabled", "enabled"), ("PDO drivers", "mysql, sqlite", "mysql, sqlite")],
        "pdo_mysql": [("PDO Driver for MySQL", "enabled", "enabled"), ("Client API version", "mysqlnd 8.2.12", "mysqlnd 8.2.12"), ("pdo_mysql.default_socket", "/run/mysqld/mysqld.sock", "/run/mysqld/mysqld.sock")],
        "mbstring": [("Multibyte Support", "enabled", "enabled"), ("Multibyte string engine", "libmbfl", "libmbfl"), ("HTTP input encoding translation", "disabled", "disabled"), ("mbstring.language", "neutral", "neutral"), ("mbstring.regex stack limit", "100000", "100000")],
        "openssl": [("OpenSSL support", "enabled", "enabled"), ("OpenSSL Library Version", "OpenSSL 3.0.15 3 Sep 2024", "OpenSSL 3.0.15 3 Sep 2024"), ("Openssl default config", "/usr/lib/ssl/openssl.cnf", "/usr/lib/ssl/openssl.cnf")],
        "session": [("Session Support", "enabled", "enabled"), ("Registered save handlers", "files, user", "files, user"), ("Registered serializer handlers", "php, php_binary, php_serialize", "php, php_binary, php_serialize"), ("session.auto_start", "Off", "Off"), ("session.cookie_httponly", "On", "On"), ("session.cookie_secure", "On", "On"), ("session.gc_maxlifetime", "1440", "1440"), ("session.save_handler", "files", "files"), ("session.save_path", "/var/lib/php/sessions", "/var/lib/php/sessions")],
        "Zend OPcache": [("Opcode Caching", "Up and Running", "Up and Running"), ("Optimization", "Enabled", "Enabled"), ("SHM Cache", "Enabled", "Enabled"), ("File Cache", "Disabled", "Disabled"), ("JIT", "Disabled", "Disabled"), ("Cache hits", "184293", "—"), ("Cache misses", "318", "—"), ("Used memory", "96.42 MB", "—"), ("Free memory", "31.58 MB", "—"), ("Cached scripts", "427", "—")],
    }
    extensions = ["bcmath", "calendar", "Core", "ctype", "curl", "date", "dom", "exif", "fileinfo", "filter", "gd", "gettext", "hash", "iconv", "intl", "json", "libxml", "mbstring", "mysqli", "mysqlnd", "openssl", "pcntl", "pcre", "PDO", "pdo_mysql", "pdo_sqlite", "Phar", "posix", "readline", "Reflection", "session", "SimpleXML", "sodium", "SPL", "sqlite3", "standard", "tokenizer", "xml", "xmlreader", "xmlwriter", "Zend OPcache", "zip", "zlib"]

    def info_table(title: str, rows: list[tuple[str, str]]) -> str:
        body = "".join(f'<tr><td class="e">{_html_escape(key)}</td><td class="v">{_html_escape(value)}</td></tr>' for key, value in rows)
        return f'<table class="info"><tr><th class="h" colspan="2">{_html_escape(title)}</th></tr>{body}</table>'

    def directive_table(title: str, rows: list[tuple[str, str, str]]) -> str:
        body = "".join(f'<tr><td class="e">{_html_escape(key)}</td><td class="v">{_html_escape(local)}</td><td class="v">{_html_escape(master)}</td></tr>' for key, local, master in rows)
        return f'<table class="info directives"><tr><th class="h" colspan="3">{_html_escape(title)}</th></tr><tr><td class="e">Directive</td><td class="e">Local Value</td><td class="e">Master Value</td></tr>{body}</table>'

    extension_rows = "".join(f'<tr><td class="e">{_html_escape(name)}</td><td class="v">enabled</td></tr>' for name in extensions)
    directive_sections = "".join(directive_table(title, values) for title, values in directives.items())
    debug_section = info_table("PHP Debug Build", [("Debug Build", "no"), ("Thread Safety", "disabled"), ("Compiler", "GCC 12.2.0"), ("Architecture", "x86_64"), ("Zend Signal Handling", "enabled"), ("Zend Memory Manager", "enabled"), ("Memory Allocation Tracking", "disabled"), ("IPv6 Support", "enabled"), ("DTrace Support", "available, disabled"), ("Systemtap Support", "disabled")])
    environment = info_table("Environment", [("CLUB_NAME", "SV Eichenwacht"), ("SITE_URL", "https://cloud.krokolani.de"), ("ADMIN_USER", "admin"), ("MYSQL_HOST", "127.0.0.1"), ("MYSQL_DB", "sv_eichenwacht"), ("MYSQL_USER", "verein_web"), ("MAIL_TO", "vorstand@sv-eichenwacht.example"), ("UPLOAD_DIR", "/var/www/sv-eichenwacht/public/uploads"), ("BACKUP_DIR", "/var/www/sv-eichenwacht/backups")])
    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>PHP 8.2.12 - phpinfo()</title><style>'
        'body{margin:8px;background:#fff;color:#000;font:13px Arial,Helvetica,sans-serif}h1{font-size:24px;margin:5px 0}.info{width:100%;border:0;border-spacing:1px;background:#fff;margin:10px auto 18px}.info td,.info th{padding:4px 6px;vertical-align:baseline}.info .h{background:#9999cc;color:#000;text-align:left;font-weight:bold}.info .e{background:#ccccff;color:#000;font-weight:bold;width:28%}.info .v{background:#eeeeee;color:#000}.info tr:nth-child(odd) .v{background:#f5f5f5}.directives .e{width:34%}.brand{width:100%;border-spacing:1px;background:#fff}.brand td{background:#9999cc;padding:8px}.brand .logo{width:120px;font-size:32px;font-weight:bold;letter-spacing:-3px;color:#4f5b93}.brand .logo span{color:#777bb3}.brand h1{text-align:center}.note{color:#555;font-size:11px;text-align:center}a{color:#00c;text-decoration:underline}'
        '</style></head><body><table class="brand"><tr><td class="logo"><span>php</span></td><td><h1>PHP Version 8.2.12</h1></td></tr></table>'
        + info_table("PHP Version", overview)
        + info_table("Server Environment", server)
        + info_table("PHP Variables", variables)
        + '<table class="info"><tr><th class="h" colspan="2">Additional Modules</th></tr>' + extension_rows + '</table>'
        + debug_section
        + directive_sections
        + environment
        + '<p class="note">PHP Documentation · <a href="https://www.php.net/">https://www.php.net/</a> · cloud.krokolani.de</p>'
        + '</body></html>'
    )


def _session_for(headers) -> tuple[str, dict[str, object]]:
    global _LAST_SESSION_CLEANUP
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("Cookie", ""))
    except (TypeError, ValueError):
        cookie = SimpleCookie()
    morsel = cookie.get(SESSION_COOKIE)
    session_id = morsel.value if morsel and re.fullmatch(r"[a-f0-9]{32}", morsel.value) else ""
    now = time.monotonic()
    with _SESSION_LOCK:
        if now - _LAST_SESSION_CLEANUP >= 60:
            for key, value in list(_SESSIONS.items()):
                if now - float(value.get("last_seen", 0)) > SESSION_IDLE_SECONDS:
                    _SESSIONS.pop(key, None)
            _LAST_SESSION_CLEANUP = now
        session = _SESSIONS.get(session_id) if session_id else None
        created = session is None
        if created:
            if len(_SESSIONS) >= MAX_SESSIONS:
                oldest = min(_SESSIONS, key=lambda key: float(_SESSIONS[key].get("last_seen", 0)))
                _SESSIONS.pop(oldest, None)
            session_id = uuid.uuid4().hex
            session = {"last_seen": now, "attempts": 0, "authenticated": False, "role": None, "permissions": [], "phase": "anonymous"}
            _SESSIONS[session_id] = session
        session["last_seen"] = now
        return session_id, session


def _portal_response(path: str, method: str, body: bytes, session: dict[str, object], query: str = ""):
    normalized = path.rstrip("/") or "/"
    login_paths = {"/login.php", "/signin.php", "/admin.php", "/administrator.php", "/console.php"}
    verb = method.upper()
    authenticated = bool(session.get("authenticated"))

    if normalized == "/impressum.php":
        return "club-imprint", 200, "text/html; charset=utf-8", _impressum_html(), []

    if normalized == "/termine.php":
        if not authenticated:
            session["phase"] = "login-required"
            return "club-event-admin-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/termine.php")]
        query_values = parse_qs(query)
        mode = query_values.get("mode", [""])[0]
        event_id = query_values.get("id", [""])[0]
        notice = ""
        if verb == "POST":
            try:
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            except ValueError:
                form = {}
            if mode == "delete":
                deleted_events = session.setdefault("deleted_events", [])
                if isinstance(deleted_events, list) and event_id not in deleted_events:
                    deleted_events.append(event_id)
                notice = "Termin wurde gelöscht."
            else:
                event = {
                    "id": event_id if mode == "edit" else uuid.uuid4().hex[:10],
                    "title": (form.get("title") or [""])[0].strip()[:100],
                    "date": (form.get("date") or [""])[0].strip()[:20],
                    "time": (form.get("time") or [""])[0].strip()[:20],
                    "team": (form.get("team") or [""])[0].strip()[:80],
                }
                if mode == "edit":
                    existing = next((item for item in _club_calendar_events(session) if item.get("id") == event_id), {})
                    if existing.get("game") == "1":
                        event.update({key: str((form.get(key) or [existing.get(key, "")])[0]).strip() for key in ("home", "away", "score", "yellow_home", "red_home", "yellow_away", "red_away")})
                        event["game"] = "1"
                if all(event[key] for key in ("title", "date", "time", "team")):
                    if mode == "edit":
                        edits = session.setdefault("managed_event_edits", {})
                        if isinstance(edits, dict):
                            edits[event_id] = event
                        notice = "Termin wurde gespeichert."
                    else:
                        events = session.setdefault("managed_events", [])
                        if not isinstance(events, list):
                            events = []
                            session["managed_events"] = events
                        events.append(event)
                        del events[:-50]
                        notice = "Neuer Termin wurde eingetragen."
                else:
                    mode = "new"
                    notice = "Bitte alle Terminangaben ergänzen."
            session["phase"] = "club-event-updated"
            mode = ""
        return "club-event-admin", 200, "text/html; charset=utf-8", _events_admin_html(session, mode, event_id, notice), []

    if normalized == "/tools/terminal.php":
        if not authenticated:
            session["phase"] = "login-required"
            return "club-terminal-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/tools/terminal.php")]
        if verb == "POST":
            try:
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            except ValueError:
                form = {}
            command = (form.get("command") or [""])[0][:500]
            cwd = str(session.get("terminal_cwd", "/home/admin"))
            attempted_file = _uploaded_execution_attempt(session, command)
            # Keep uploaded code inert. A quiet, plausible response is enough
            # for the fake terminal while the event itself is classified.
            result = "" if attempted_file else _fake_terminal_command(session, command)
            history = session.setdefault("terminal_history", [])
            if not isinstance(history, list):
                history = []
                session["terminal_history"] = history
            if command.strip() != "clear":
                history.append({"cwd": cwd, "command": command, "output": result})
                del history[:-30]
            session["phase"] = "uploaded-execution-attempt" if attempted_file else "terminal-command"
            rule = "uploaded-execution-attempt" if attempted_file else "club-terminal-command"
            return rule, 200, "text/html; charset=utf-8", _terminal_html(session), []
        session["phase"] = "terminal-opened"
        return "club-terminal", 200, "text/html; charset=utf-8", _terminal_html(session), []

    if normalized == "/kontakt.php":
        if verb == "POST":
            session["phase"] = "contact-message-submitted"
            return "contact-form-submitted", 200, "text/html; charset=utf-8", _contact_html(True), []
        session["phase"] = "contact-form-viewed"
        return "contact-form", 200, "text/html; charset=utf-8", _contact_html(), []

    if normalized == "/training.php":
        if not authenticated:
            session["phase"] = "login-required"
            return "club-training-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/training.php")]
        return "club-training-schedule", 200, "text/html; charset=utf-8", _training_html(session), []

    if normalized == "/brett.php":
        if not authenticated:
            session["phase"] = "login-required"
            return "club-notice-board-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/brett.php")]
        return "club-notice-board", 200, "text/html; charset=utf-8", _blackboard_html(), []

    if normalized == "/mitglieder.php":
        if not authenticated:
            session["phase"] = "login-required"
            return "club-members-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/mitglieder.php")]
        session["phase"] = "club-members-viewed"
        return "club-members", 200, "text/html; charset=utf-8", _members_html(parse_qs(query).get("q", [""])[0], int(parse_qs(query).get("page", ["1"])[0]) if parse_qs(query).get("page", ["1"])[0].isdigit() else 1), []

    if normalized in {"/useradmin.php", "/useradmin/login.php", "/useradmin/dashboard.php", "/useradmin/users.php", "/useradmin/settings.php"}:
        if not authenticated:
            session["phase"] = "login-required"
            return "useradmin-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/useradmin.php")]
        if "manage_users" not in session.get("permissions", []):
            session["phase"] = "useradmin-access-denied"
            denied = _page("Access denied", '<section class="content-card"><span class="eyebrow">ACCESS CONTROL</span><h1>Access denied</h1><p>Your account does not have permission to manage users.</p><a class="primary-button" href="/dashboard.php">Return to account</a></section>', "dashboard-page")
            return "useradmin-access-denied", 403, "text/html; charset=utf-8", denied, []
        session["phase"] = "useradmin-viewed"
        query_values = parse_qs(query)
        mode = query_values.get("mode", [""])[0]
        member_id = query_values.get("id", [""])[0]
        notice = ""
        if verb == "POST":
            try:
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            except ValueError:
                form = {}
            if mode == "delete":
                deleted = session.setdefault("deleted_members", [])
                if isinstance(deleted, list) and member_id not in deleted:
                    deleted.append(member_id)
                notice = "Mitglied wurde gelöscht."
            elif mode in {"new", "edit"}:
                values = (
                    member_id or ("N" + uuid.uuid4().hex[:8].upper()),
                    (form.get("name") or [""])[0][:120],
                    (form.get("birth_date") or [""])[0][:20],
                    (form.get("department") or [""])[0][:80],
                    (form.get("joined") or [""])[0][:20],
                    (form.get("status") or ["Aktiv"])[0][:30],
                    (form.get("email") or [""])[0][:160],
                )
                if mode == "new":
                    added = session.setdefault("added_members", [])
                    if isinstance(added, list):
                        added.append(values)
                    notice = "Neues Mitglied wurde aufgenommen."
                else:
                    edits = session.setdefault("member_edits", {})
                    if isinstance(edits, dict):
                        edits[member_id] = values
                    notice = "Mitgliedsdaten wurden gespeichert."
            else:
                notice = "Änderungen wurden gespeichert."
            mode = ""
        return "useradmin-dashboard", 200, "text/html; charset=utf-8", _useradmin_html(
            query_values.get("q", [""])[0],
            int(query_values.get("page", ["1"])[0]) if query_values.get("page", ["1"])[0].isdigit() else 1,
            mode=mode,
            member_id=member_id,
            notice=notice,
            session=session,
        ), []

    uploaded_path = normalized.removeprefix("/uploads/") if normalized.startswith("/uploads/") else ""
    if uploaded_path:
        uploads = session.get("uploaded_files", [])
        selected = next((item for item in uploads if isinstance(item, dict) and item.get("name") == uploaded_path), None) if isinstance(uploads, list) else None
        if selected:
            session["phase"] = "uploaded-script-requested" if uploaded_path.lower().endswith(".php") else "uploaded-file-opened"
            if uploaded_path.lower().endswith(".php"):
                rendered = _page("SV Eichenwacht", '<section class="content-card"><span class="eyebrow">SV EICHENWACHT E.V.</span><h1>Vereinsseite</h1><p>Willkommen beim SV Eichenwacht.</p><div class="activity-row"><span class="activity-marker green-marker"></span><span><strong>Vereinsbüro</strong><small>Erreichbar · PHP 8.2.12</small></span></div></section>', "dashboard-page")
                return "uploaded-php-request", 200, "text/html; charset=utf-8", rendered, []
            return "uploaded-file-request", 200, "text/plain; charset=utf-8", f"File received: {uploaded_path}\n", []

    if normalized == "/files/upload.php" and verb not in {"POST", "PUT", "PATCH"}:
        body = (
            '<section class="simple-card"><a class="back-link" href="/kontakt.php">← Zurück zum Kontakt</a>'
            '<div class="card-icon">↥</div><span class="eyebrow">SV EICHENWACHT</span><h1>Datei einreichen</h1>'
            '<p class="card-intro">Du möchtest Fotos, Dokumente oder andere Unterlagen mit dem Verein teilen? Hier kannst du sie an das Vereinsbüro senden.</p>'
            '<form method="post" action="/files/upload.php" enctype="multipart/form-data" class="login-form">'
            '<label for="public-package">Datei auswählen</label><input id="public-package" name="package" type="file" required>'
            '<label for="public-upload-note">Hinweis (optional)</label><input id="public-upload-note" name="note" placeholder="Zum Beispiel: Mannschaftsfoto vom Samstag">'
            '<button class="primary-button" type="submit">Datei senden <span aria-hidden="true">→</span></button>'
            '</form></section>'
        )
        session["phase"] = "public-upload-form-viewed"
        return "public-file-upload-form", 200, "text/html; charset=utf-8", _page("Datei einreichen", body, "auth-page files-page"), []

    if normalized in {"/files.php", "/files/upload.php", "/backups.php", "/backups/import.php"}:
        if verb in {"POST", "PUT", "PATCH"} and normalized == "/files/upload.php":
            session["phase"] = "file-upload-received"
            uploads = session.setdefault("uploaded_files", [])
            if not isinstance(uploads, list):
                uploads = []
                session["uploaded_files"] = uploads
            upload = {"id": uuid.uuid4().hex, "name": _uploaded_filename(body), "content": _uploaded_file_content(body)}
            uploads.append(upload)
            del uploads[:-20]
            with _SESSION_LOCK:
                HONEYPOT_UPLOADS.append({"name": upload["name"], "content": upload["content"]})
                del HONEYPOT_UPLOADS[:-100]
            filename = _html_escape(upload["name"])
            public_path = "/uploads/" + quote(upload["name"], safe="")
            return "file-upload-captured", 202, "text/html; charset=utf-8", _page(
                "Upload aufgenommen", '<section class="simple-card"><span class="eyebrow">VEREINSUNTERLAGEN</span><h1>Datei aufgenommen</h1><p class="card-intro"><strong>' + filename + '</strong> wurde zu den Dateien der Vereinsseite hinzugefügt.</p><p>Website-Pfad: <a href="' + public_path + '">' + _html_escape(public_path) + '</a></p><p><a href="/files.php">Dateiliste ansehen</a></p></section>', "auth-page"
            ), []
        if not authenticated:
            session["phase"] = "login-required"
            return "file-manager-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php?next=/files.php")]
        session["phase"] = "file-manager-viewed"
        return "file-manager", 200, "text/html; charset=utf-8", _files_html(session), []

    if normalized in login_paths:
        if verb == "POST":
            try:
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            except ValueError:
                form = {}
            username = (form.get("username") or form.get("user") or form.get("email") or [""])[0]
            password = (form.get("password") or form.get("pass") or [""])[0]
            if username.strip().lower() in DECOY_USERNAMES and password in DECOY_PASSWORDS:
                session["authenticated"] = True
                session["role"] = "administrator"
                session["permissions"] = ["manage_users"]
                session["phase"] = "authenticated"
                next_target = parse_qs(query).get("next", [""])[0]
                destination = next_target if next_target in {"/useradmin.php", "/files.php", "/tools/terminal.php", "/mitglieder.php", "/training.php", "/brett.php", "/termine.php"} else "/dashboard.php"
                return "portal-login-success", 302, "text/plain; charset=utf-8", "Redirecting to account.\n", [("Location", destination)]
            session["attempts"] = int(session.get("attempts", 0)) + 1
            session["phase"] = f"login-attempt-{session['attempts']}"
            return "portal-login-failed", 200, "text/html; charset=utf-8", _login_html("Mitgliederbereich", normalized, "Mitgliedsnummer oder Passwort stimmt nicht."), []
        if authenticated:
            return "portal-dashboard", 200, "text/html; charset=utf-8", _dashboard_html(session), []
        next_target = parse_qs(query).get("next", [""])[0]
        action = f"/login.php?next={next_target}" if next_target in {"/useradmin.php", "/files.php", "/tools/terminal.php", "/mitglieder.php", "/training.php", "/brett.php", "/termine.php"} else normalized
        return "portal-login", 200, "text/html; charset=utf-8", _login_html("Mitgliederbereich", action), []

    if normalized in ("/dashboard.php", "/admin/settings.php"):
        if authenticated:
            session["phase"] = "authenticated"
            return "portal-dashboard", 200, "text/html; charset=utf-8", _dashboard_html(session), []
        session["phase"] = "login-required"
        return "portal-login-required", 302, "text/plain; charset=utf-8", "Redirecting to sign in.\n", [("Location", "/login.php")]

    if normalized == "/logout.php":
        session["authenticated"] = False
        session["role"] = None
        session["permissions"] = []
        session["phase"] = "signed-out"
        return "portal-logout", 302, "text/plain; charset=utf-8", "Signed out.\n", [("Location", "/login.php")]

    if normalized == "/password/reset.php":
        if verb == "POST":
            session["phase"] = "password-reset-requested"
            return "portal-password-reset", 200, "text/html; charset=utf-8", _reset_html("If the account exists, recovery instructions will be sent."), []
        return "portal-password-reset", 200, "text/html; charset=utf-8", _reset_html(), []

    if normalized == "/" and authenticated:
        return "portal-dashboard", 200, "text/html; charset=utf-8", _dashboard_html(session), []
    return None


def _static_asset(path: str) -> tuple[str, str, bytes] | None:
    assets = {
        "/assets/portal.css": ("portal-stylesheet", "text/css; charset=utf-8", "portal.css"),
        "/favicon.ico": ("portal-favicon", "image/x-icon", "favicon.ico"),
    }
    asset = assets.get(path)
    if asset is None:
        return None
    rule, content_type, filename = asset
    try:
        content = (Path(__file__).with_name("assets") / filename).read_bytes()
    except OSError:
        return None
    return rule, content_type, content


def decoy(path: str, method: str) -> tuple[str, int, str, str]:
    if re.fullmatch(r"/phpinfo\.php", path, re.IGNORECASE):
        return "phpinfo-probe", 200, "text/html; charset=utf-8", _phpinfo_html()
    if path in ("/.env", "/.env.production"):
        return (
            "environment-file-probe", 200, "text/plain; charset=utf-8",
            "CLUB_NAME=SV Eichenwacht\nSITE_URL=https://cloud.krokolani.de\nADMIN_USER=admin\nADMIN_PASS=Az44O6GRuZhJbJYlmlEy\nMYSQL_HOST=127.0.0.1\nMYSQL_DB=sv_eichenwacht\nMYSQL_USER=verein_web\nMYSQL_PASS=Eichenwacht-Db-2026!\nMAIL_TO=vorstand@sv-eichenwacht.example\nUPLOAD_DIR=/var/www/sv-eichenwacht/public/uploads\nBACKUP_DIR=/var/www/sv-eichenwacht/backups\n",
        )
    if path == "/.git/config":
        return (
            "git-config-probe", 200, "text/plain; charset=utf-8",
            '[core]\n\trepositoryformatversion = 0\n\tbare = false\n'
            '[remote "origin"]\n\turl = https://git.example.invalid/acme/portal.git\n',
        )
    if path == "/server-status":
        return (
            "server-status-probe", 200, "text/html; charset=utf-8",
            "<html><title>Apache Status</title><body><h1>Server Status</h1><p>Server uptime: 2 days</p></body></html>",
        )
    if WP_LOGIN.fullmatch(path):
        return "wordpress-login", 200, "text/html; charset=utf-8", _login_html("WordPress", "/wp-login.php")
    if PHP_MYADMIN.fullmatch(path):
        return "phpmyadmin-login", 200, "text/html; charset=utf-8", _login_html("phpMyAdmin", "/phpmyadmin/")
    if ADMIN_LOGIN.fullmatch(path):
        return "admin-login", 200, "text/html; charset=utf-8", _login_html("Administration", path)
    if API_PATH.fullmatch(path):
        return "api-probe", 200, "application/json", '{"status":"ok","version":"2.4.1","service":"portal-api"}'
    if path in ("/", "/index.php"):
        return "portal-login", 200, "text/html; charset=utf-8", _login_html("Mitgliederbereich", "/login.php")
    if path.startswith("/.well-known/"):
        return "well-known-probe", 404, "text/plain; charset=utf-8", "Not Found"
    if method.upper() == "OPTIONS":
        return "options", 204, "text/plain; charset=utf-8", ""
    return "unmatched", 404, "text/html; charset=utf-8", "<!doctype html><title>Not Found</title><h1>404 Not Found</h1>"


def response_page(rule: str) -> str:
    """Describe the page returned for an event in a human-readable way."""
    pages = {
        "portal-login": "Login-Seite",
        "portal-login-failed": "Login-Seite",
        "portal-login-required": "Login-Seite",
        "wordpress-login": "WordPress-Loginseite",
        "phpmyadmin-login": "phpMyAdmin-Loginseite",
        "admin-login": "Administrations-Loginseite",
        "contact-form": "Kontaktseite",
        "contact-form-submitted": "Kontaktseite",
        "portal-dashboard": "Mitgliederbereich",
        "portal-login-success": "Mitgliederbereich",
        "club-imprint": "Impressum",
        "club-training-schedule": "Trainings- und Terminseite",
        "club-training-login-required": "Login-Seite",
        "club-notice-board": "Schwarzes Brett",
        "club-notice-board-login-required": "Login-Seite",
        "club-members": "Mitgliederliste",
        "club-members-login-required": "Login-Seite",
        "club-event-admin": "Terminverwaltung",
        "club-event-admin-login-required": "Login-Seite",
        "useradmin-dashboard": "Mitgliederverwaltung",
        "useradmin-login-required": "Login-Seite",
        "useradmin-access-denied": "Zugriff-verweigert-Seite",
        "file-manager": "Dateiverwaltung",
        "file-manager-login-required": "Login-Seite",
        "public-file-upload-form": "Uploadformular",
        "file-upload-captured": "Upload-Bestätigung",
        "club-terminal": "Webmaster-Terminal",
        "club-terminal-login-required": "Login-Seite",
        "uploaded-file-request": "Hochgeladene Datei",
        "uploaded-php-request": "Hochgeladene PHP-Datei",
        "portal-password-reset": "Passwort-zurücksetzen-Seite",
        "portal-logout": "Abmeldung",
        "phpinfo-probe": "PHP-Info-Seite",
        "server-status-probe": "Serverstatus-Seite",
        "api-probe": "API-Antwort",
        "unmatched": "404-Fehlerseite",
        "well-known-probe": "404-Fehlerseite",
        "options": "OPTIONS-Antwort",
        "environment-file-probe": "Konfigurationsdatei",
        "git-config-probe": "Git-Konfiguration",
        "portal-stylesheet": "Stylesheet",
        "portal-favicon": "Favicon",
    }
    return pages.get(rule, "Antwort")


def preview_html(path: str, rule: str) -> str | None:
    """Render the matching fixed HTML page for an event without mutating a session."""
    def inline_assets(content: str) -> str:
        stylesheet = (Path(__file__).with_name("assets") / "portal.css").read_text(encoding="utf-8")
        return content.replace(
            '<link rel="stylesheet" href="/assets/portal.css?v=20261020-1">',
            f"<style>{stylesheet}</style>",
        )

    if rule == "portal-login-failed":
        return inline_assets(_login_html("Mitgliederbereich", path.rstrip("/") or "/", "Mitgliedsnummer oder Passwort stimmt nicht."))
    session: dict[str, object] = {"authenticated": False, "phase": "anonymous"}
    portal = _portal_response(path, "GET", b"", session)
    if portal is not None:
        rendered_rule, _status, content_type, content, _headers = portal
        if rendered_rule == rule and content_type.startswith("text/html"):
            return inline_assets(content)
    rendered_rule, _status, content_type, content = decoy(path, "GET")
    if rendered_rule == rule and content_type.startswith("text/html"):
        return inline_assets(content)
    return None


class HoneypotHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = ""
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def handle_one_request(self) -> None:
        # Keep the request-line/header read bounded by the same 10 second budget.
        self.connection.settimeout(10)
        super().handle_one_request()

    def _respond(self) -> None:
        request_started_ns = time.perf_counter_ns()
        body, content_length, clipped = read_request_body(self.rfile, self.headers)
        if clipped:
            self.close_connection = True

        parsed = urlsplit(self.path)
        decoded_path = unquote(parsed.path)
        session_id, session = _session_for(self.headers)
        asset = _static_asset(decoded_path)
        if asset is not None:
            rule, content_type, payload = asset
            status = 200
            response_headers = [("Cache-Control", "no-cache, must-revalidate")]
        else:
            portal = _portal_response(decoded_path, self.command, body, session, parsed.query)
            if portal is None:
                rule, status, content_type, response = decoy(decoded_path, self.command)
                if rule == "environment-file-probe":
                    host = self.headers.get("Host", "cloud.krokolani.de")
                    response = response.replace("cloud.example.invalid", host)
                response_headers = []
            else:
                rule, status, content_type, response, response_headers = portal
            payload = response.encode("utf-8")
        expected_html = preview_html(decoded_path, rule) if content_type.startswith("text/html") else None
        response_html = payload.decode("utf-8", errors="replace") if content_type.startswith("text/html") else None
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if asset is None:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if asset is None:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower() == "https" else ""
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_IDLE_SECONDS}{secure}")
        for name, value in response_headers:
            self.send_header(name, value)
        if clipped:
            self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command.upper() != "HEAD" and payload:
            self.wfile.write(payload)

        forwarded = self.headers.get("X-Forwarded-For", "")
        client_ip = forwarded.split(",")[-1].strip() if forwarded else ""
        if not client_ip:
            client_ip = self.client_address[0]
        event_id = uuid.uuid4().hex
        event = {
            "event_id": event_id,
            "time": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "client_ip": client_ip,
            "host": self.headers.get("Host", ""),
            "scheme": self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0].strip().lower(),
            "method": self.command,
            "path": parsed.path,
            "user_agent": self.headers.get("User-Agent", "")[:512],
            "content_type": self.headers.get("Content-Type", "")[:128],
            "body_bytes": content_length,
            "body_clipped": clipped,
            "body_sha256": hashlib.sha256(body).hexdigest() if body else "",
            "rule": rule,
            "response_page": response_page(rule),
            "response_html": response_html if expected_html is not None and response_html != expected_html else None,
            "status": status,
            "duration": time.perf_counter_ns() - request_started_ns,
            "session_id": session_id,
            "session_phase": session.get("phase", "anonymous"),
        }
        log_path = Path(os.environ.get("HONEYPOT_LOG_PATH", "/logs/honeypot.jsonl"))
        body_directory = Path(os.environ.get("HONEYPOT_BODY_DIR", "/logs/honeypot-bodies"))
        if body:
            if len(body) > INLINE_BODY_BYTES:
                body_directory.mkdir(parents=True, exist_ok=True)
                body_file = f"{event_id}.bin"
                (body_directory / body_file).write_bytes(body)
                event["body_file"] = body_file
            else:
                try:
                    event["body_text"] = body.decode("utf-8")
                except UnicodeDecodeError:
                    event["body_base64"] = base64.b64encode(body).decode("ascii")

        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._respond()

    def do_POST(self) -> None:  # noqa: N802
        self._respond()

    def do_PUT(self) -> None:  # noqa: N802
        self._respond()

    def do_PATCH(self) -> None:  # noqa: N802
        self._respond()

    def do_DELETE(self) -> None:  # noqa: N802
        self._respond()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._respond()

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond()

    def log_message(self, fmt: str, *args: object) -> None:
        # One structured event per request is emitted by _respond().
        return

    def __getattr__(self, name: str):
        # net/http serves arbitrary methods; keep unknown HTTP methods on the
        # same rule path instead of BaseHTTPRequestHandler's default 501.
        if name.startswith("do_"):
            return self._respond
        raise AttributeError(name)


def main() -> None:
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    address = os.environ.get("HONEYPOT_ADDR", ":8080")
    if address.startswith(":"):
        host, port = "", int(address[1:])
    else:
        host, separator, raw_port = address.rpartition(":")
        if not separator:
            raise ValueError("HONEYPOT_ADDR must be in host:port form")
        port = int(raw_port)
    state_path = Path(os.environ.get("HONEYPOT_STATE_PATH", "/logs/honeypot.state"))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    server = ThreadingHTTPServer((host, port), HoneypotHandler)
    server.daemon_threads = True
    server.request_queue_size = 64
    def stop_on_signal(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_on_signal)
    state_path.write_text("running\n", encoding="ascii")
    LOG.info("HTTP decoy listening on %s", address)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        state_path.unlink(missing_ok=True)
        server.server_close()


if __name__ == "__main__":
    main()
