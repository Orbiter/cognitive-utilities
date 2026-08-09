#!/usr/bin/env python3
"""Interaktiver RAG-Chat über die lokale BGB-Such-API."""

import http.client
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


# Beispielprompts:
# Welche Gewährleistungsregeln gelten für digitale Produkte und Software-Updates?
# Wann ist die Entwicklung einer individuellen Software als Werkvertrag einzuordnen?
# Welche Ansprüche können entstehen, wenn ein Programmierauftrag mangelhaft ausgeführt wurde?
# Sind das Umgehen von Zugangsschutz und der Besitz von Hackerwerkzeugen im BGB geregelt?
# Welche BGB-Regeln können für einen Vertrag über frei verfügbare Daten gelten?
# Kann allein anhand des BGB beurteilt werden, ob Daten frei verwendet werden dürfen?

MAX_DURCHLAEUFE = 10
SEARCH_API_URL = os.environ.get(
    "SEARCH_API_URL", "http://127.0.0.1:8080/search"
)

SYSTEMPROMPT = """Du beantwortest Fragen anhand des Bürgerlichen Gesetzbuchs.
Dir steht mit bgb_suche ein Werkzeug zur Volltextsuche über eine lokale
HTTP-API zur Verfügung. Benutze es, wenn du den Gesetzestext für eine
zuverlässige Antwort benötigst oder wenn sich eine Frage auf das BGB bezieht
oder beziehen könnte. Eine Antwort, die Paragraphen erwähnt oder scheinbar
daraus zitiert, ohne dass vorher eine Suche mit bgb_suche stattgefunden hat,
ist nicht zulässig. Du musst dich dann korrigieren und trotzdem eine Suche
durchführen. Eine Suche darf und soll mehrfach ausgeführt werden, wenn die
Qualität der Treffer noch nicht ausreicht. Verwende bei einer erneuten Suche
andere, passendere oder spezifischere Suchwörter. Die Suchwörter werden wie bei
einer Suchmaschine durch Leerzeichen getrennt. Stütze Aussagen über den Inhalt
des BGB auf die gefundenen Textstellen und nenne möglichst die Paragraphen.
Sobald du genügend Informationen hast, antworte ohne weiteren Werkzeugaufruf."""

WERKZEUGE = [
    {
        "type": "function",
        "function": {
            "name": "bgb_suche",
            "description": (
                "Durchsucht das BGB über eine lokale Such-API nach Stichwörtern. "
                "Mehrere Stichwörter werden leerzeichen-separiert angegeben."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": (
                            "Leerzeichen-separierte Suchanfrage, zum Beispiel "
                            "Kauf Mangel Nacherfüllung"
                        ),
                    }
                },
                "required": ["q"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


def bgb_suche(q):
    """Ruft die Such-API mit genau einem GET-Parameter q auf."""
    url = f"{SEARCH_API_URL}?{urlencode({'q': q})}"
    try:
        with urlopen(url, timeout=30) as antwort:
            inhalt = json.loads(antwort.read().decode("utf-8"))
    except HTTPError as fehler:
        try:
            inhalt = json.loads(fehler.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            inhalt = {"fehler": f"Such-API antwortet mit HTTP {fehler.code}."}
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        inhalt = {"fehler": f"Such-API nicht erreichbar: {fehler}", "treffer": []}

    treffer = inhalt.get("treffer", [])
    print(f"Treffer gefunden: {inhalt.get('anzahl_treffer', 0)}")
    print(f"Selektierte Treffer ({len(treffer)}):")
    for fund in treffer:
        zeilennummern = ", ".join(
            str(zeile) for zeile in fund.get("trefferzeilen", [])
        )
        print(f"- {fund.get('datei', 'bgb.md')}: Zeilen {zeilennummern}")
        print(
            "  Zusammengefasster Bereich: "
            f"Zeilen {fund.get('kontext_von')}-{fund.get('kontext_bis')}"
        )
    print(flush=True)

    return json.dumps(inhalt, ensure_ascii=False)


def chat_anfrage(messages):
    basis_url = urlsplit(os.environ["OPENAI_BASE_URL"])
    if basis_url.scheme not in {"http", "https"} or not basis_url.hostname:
        raise RuntimeError("OPENAI_BASE_URL ist keine gültige HTTP(S)-URL.")

    payload = {
        "model": os.environ["OPENAI_MODEL"],
        "temperature": float(os.environ["OPENAI_TEMPERATURE"]),
        "reasoning_effort": os.environ["OPENAI_REASONING_EFFORT"],
        "max_tokens": 2048,
        "stream": False,
        "messages": messages,
        "tools": WERKZEUGE,
    }
    pfad = f"{basis_url.path.rstrip('/')}/v1/chat/completions"
    verbindungsklasse = (
        http.client.HTTPSConnection
        if basis_url.scheme == "https"
        else http.client.HTTPConnection
    )
    verbindung = verbindungsklasse(basis_url.hostname, basis_url.port, timeout=600)
    try:
        verbindung.request(
            "POST",
            pfad,
            json.dumps(payload),
            {
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        response = verbindung.getresponse()
        response_text = response.read().decode()
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}: {response_text}")
        return json.loads(response_text)["choices"][0]["message"]
    finally:
        verbindung.close()


def agentic_loop(gespraech, prompt):
    arbeitskontext = gespraech + [{"role": "user", "content": prompt}]

    for _ in range(MAX_DURCHLAEUFE):
        antwort = chat_anfrage(arbeitskontext)
        tool_calls = antwort.get("tool_calls") or []
        if not tool_calls:
            return antwort.get("content") or ""
        if antwort.get("content"):
            print(antwort["content"], flush=True)
        arbeitskontext.append(antwort)

        for tool_call in tool_calls:
            name = tool_call.get("function", {}).get("name")
            try:
                argumente = json.loads(
                    tool_call.get("function", {}).get("arguments", "{}")
                )
                if name != "bgb_suche":
                    ergebnis = json.dumps(
                        {"fehler": f"Unbekanntes Werkzeug: {name}"},
                        ensure_ascii=False,
                    )
                else:
                    q = argumente.get("q", "")
                    print(f"\nSuche nach: {q}", flush=True)
                    ergebnis = bgb_suche(q)
            except (json.JSONDecodeError, TypeError) as fehler:
                ergebnis = json.dumps(
                    {"fehler": f"Ungültige Werkzeugargumente: {fehler}"},
                    ensure_ascii=False,
                )

            arbeitskontext.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": name,
                    "content": ergebnis,
                }
            )

    raise RuntimeError(
        f"Die Agentic Loop wurde nach {MAX_DURCHLAEUFE} Durchläufen beendet."
    )


def main():
    gespraech = [{"role": "system", "content": SYSTEMPROMPT}]

    while True:
        try:
            prompt = input("Frage: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue
        if prompt.casefold() in {"exit", "quit", "ende"}:
            break

        try:
            antwort = agentic_loop(gespraech, prompt)
            print(f"\n{antwort}\n")
            # Nur Frage und finale Antwort werden für die nächste Frage bewahrt.
            # Werkzeugaufrufe und Treffer bleiben im temporären Arbeitskontext.
            gespraech.extend(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": antwort},
                ]
            )
        except (
            OSError,
            RuntimeError,
            KeyError,
            ValueError,
            json.JSONDecodeError,
        ) as fehler:
            print(f"\nFehler: {fehler}\n")


if __name__ == "__main__":
    main()
