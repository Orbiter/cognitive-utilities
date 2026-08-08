#!/usr/bin/env python3
"""Kleine HTTP-API zur Volltextsuche in einer lokalen Ausgabe des BGB."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen


BGB_URL = (
    "https://raw.githubusercontent.com/Orbiter/bundestag_gesetze_parser/"
    "refs/heads/master/b/bgb/index.md"
)
BGB_DATEI = Path(__file__).resolve().parent / "bgb.md"
MAX_TREFFER = 5
KONTEXT_ZEILEN_DAVOR = 10
KONTEXT_ZEILEN_DANACH = 20
MAX_ZEILEN_PRO_TREFFERBEREICH = 300


def bgb_bereitstellen():
    """Lädt bgb.md nur dann herunter, wenn die Datei noch nicht existiert."""
    if BGB_DATEI.exists():
        return

    temporaerer_pfad = None
    try:
        with urlopen(BGB_URL) as antwort:
            with NamedTemporaryFile(
                mode="wb",
                dir=BGB_DATEI.parent,
                prefix=".bgb.md.",
                delete=False,
            ) as temporaere_datei:
                temporaerer_pfad = Path(temporaere_datei.name)
                while block := antwort.read(64 * 1024):
                    temporaere_datei.write(block)

        temporaerer_pfad.replace(BGB_DATEI)
        temporaerer_pfad = None
    finally:
        if temporaerer_pfad is not None:
            temporaerer_pfad.unlink(missing_ok=True)


def bgb_suche(q):
    """Durchsucht genau eine lokale Datei und gibt ein JSON-fähiges Objekt zurück."""
    suchwoerter = [wort.casefold() for wort in q.split() if wort]
    if not suchwoerter:
        return {"fehler": "Der Parameter q darf nicht leer sein.", "treffer": []}

    with BGB_DATEI.open(encoding="utf-8", errors="replace") as datei:
        zeilen = datei.readlines()

    rohtreffer = []
    for index, zeile in enumerate(zeilen):
        zeile_klein = zeile.casefold()
        haeufigkeiten = [zeile_klein.count(wort) for wort in suchwoerter]
        if not any(haeufigkeiten):
            continue
        rohtreffer.append({"index": index, "haeufigkeiten": haeufigkeiten})

    gruppen = []
    for rohtreffer_fund in rohtreffer:
        index = rohtreffer_fund["index"]
        von = max(0, index - KONTEXT_ZEILEN_DAVOR)
        bis = min(len(zeilen), index + KONTEXT_ZEILEN_DANACH + 1)

        if bis - von > MAX_ZEILEN_PRO_TREFFERBEREICH:
            bis = min(bis, von + MAX_ZEILEN_PRO_TREFFERBEREICH)
            if index >= bis:
                bis = index + 1
                von = max(0, bis - MAX_ZEILEN_PRO_TREFFERBEREICH)

        kann_zusammenfassen = bool(gruppen)
        if kann_zusammenfassen:
            letzte_gruppe = gruppen[-1]
            neuer_bis_wert = max(letzte_gruppe["bis"], bis)
            kann_zusammenfassen = (
                von < letzte_gruppe["bis"]
                and neuer_bis_wert - letzte_gruppe["von"]
                <= MAX_ZEILEN_PRO_TREFFERBEREICH
            )

        if not kann_zusammenfassen:
            gruppen.append(
                {
                    "von": von,
                    "bis": bis,
                    "indizes": [],
                    "haeufigkeiten": [0] * len(suchwoerter),
                }
            )

        gruppe = gruppen[-1]
        gruppe["bis"] = max(gruppe["bis"], bis)
        gruppe["indizes"].append(index)
        gruppe["haeufigkeiten"] = [
            bisher + neu
            for bisher, neu in zip(
                gruppe["haeufigkeiten"], rohtreffer_fund["haeufigkeiten"]
            )
        ]

    treffer = []
    for gruppe in gruppen:
        verschiedene_woerter = sum(
            anzahl > 0 for anzahl in gruppe["haeufigkeiten"]
        )
        termfrequenz = sum(gruppe["haeufigkeiten"])
        treffer.append(
            {
                "datei": BGB_DATEI.name,
                "zeile": gruppe["indizes"][0] + 1,
                "trefferzeilen": [index + 1 for index in gruppe["indizes"]],
                "kontext_von": gruppe["von"] + 1,
                "kontext_bis": gruppe["bis"],
                "score": verschiedene_woerter * 1000 + termfrequenz,
                "text": "".join(zeilen[gruppe["von"] : gruppe["bis"]]).strip(),
            }
        )

    treffer.sort(key=lambda fund: (-fund["score"], fund["zeile"]))
    return {
        "q": q,
        "anzahl_treffer": len(treffer),
        "anzahl_trefferzeilen": len(rohtreffer),
        "treffer": treffer[:MAX_TREFFER],
    }


class SuchanfrageHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        anfrage = urlsplit(self.path)
        if anfrage.path != "/search":
            self.json_antwort(404, {"fehler": "Unbekannter Pfad."})
            return

        self.send_response(204)
        self.cors_header()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        anfrage = urlsplit(self.path)
        if anfrage.path != "/search":
            self.json_antwort(404, {"fehler": "Unbekannter Pfad."})
            return

        q = parse_qs(anfrage.query).get("q", [""])[0].strip()
        if not q:
            self.json_antwort(
                400,
                {"fehler": "Der GET-Parameter q fehlt oder ist leer.", "treffer": []},
            )
            return

        try:
            self.json_antwort(200, bgb_suche(q))
        except OSError as fehler:
            self.json_antwort(
                500,
                {"fehler": f"Die BGB-Datei konnte nicht gelesen werden: {fehler}"},
            )

    def json_antwort(self, status, inhalt):
        daten = json.dumps(inhalt, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cors_header()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def cors_header(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def main():
    bgb_bereitstellen()
    host = os.environ.get("SEARCH_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SEARCH_API_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), SuchanfrageHandler)
    print(f"BGB-Suche läuft auf http://{host}:{port}/search?q=...", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
