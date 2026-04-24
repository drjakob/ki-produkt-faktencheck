"""
KI-Produkt-Faktencheck · Phase A · Vollauf-Skript

Startet die Claim-Extraktion für alle Ernährungs-Antworten im Whitepaper-Set.
Verwendet Claude Opus 4.7 via Anthropic API.

Voraussetzungen:
- anthropic-python installiert: pip install anthropic
- API-Key in Environment: ANTHROPIC_API_KEY
- pilot_20.csv und ResponsesWhitepaperPromptSetApril2026_3.csv im Pfad

Aufruf:
    python run_extraction_fullrun.py --mode pilot     # erst Pilot wiederholen
    python run_extraction_fullrun.py --mode full      # 696 Antworten
    python run_extraction_fullrun.py --mode topic --topic Ernährung  # topic-spezifisch

Kostenschätzung Vollauf (Ernährung):
- Input: ~400k Tokens
- Output: ~350k Tokens
- Modell: claude-opus-4-7 (passender Alias)
- Grober Preis: je nach Tarif ~40 bis 60 Euro

Sicherheit:
- Schreibt nach jedem Call in CSV (kein Datenverlust bei Abbruch)
- Kann mit --resume aus bestehender CSV fortsetzen
- Exponentielles Backoff bei Rate-Limits
"""

import os
import sys
import time
import json
import argparse
import pandas as pd
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Fehler: anthropic-Package nicht installiert. pip install anthropic")
    sys.exit(1)


EXTRACTION_SYSTEM = """Du bist Extraktions-Assistent für den KI-Produkt-Faktencheck. Deine einzige Aufgabe: aus einer KI-Antwort harte, prüfbare Claims extrahieren und als JSON-Array zurückgeben. Kein Kommentar, kein Preamble, nur valides JSON."""


EXTRACTION_USER_TEMPLATE = """AUFGABE
Extrahiere aus der folgenden KI-Antwort alle harten Claims.

HARTE CLAIMS sind Aussagen, die sich gegen eine Quelle prüfen lassen:
- Zahlen und Mengen (Prozente, Gramm, Liter, Jahresangaben)
- Studienlagen ("Studien zeigen...", "laut WHO...")
- Definitionen ("X ist Y")
- Ursache-Wirkung-Behauptungen ("X bewirkt Y", "X fördert Y")
- Mengenvergleiche ("X enthält mehr/weniger Y als Z")
- Tatsachenbehauptungen über Produktion, Herkunft, Verarbeitung

NICHT extrahieren:
- Werturteile ("Produkt ist lecker", "ist zu teuer", "ist gesund")
- Rhetorische Fragen
- Persönliche Empfehlungen ohne Faktengehalt ("Du solltest mal probieren...")
- Bloße Meinungsäußerungen
- Grußformeln, Smalltalk, Persona-Bezug
- Beschreibungen eigener Kommunikationsabsicht ("Ich erkläre dir...")

NORMALISIERUNG
- Formuliere jeden Claim als eigenständigen, prüfbaren Satz auf Deutsch
- Entferne Persona-Bezüge ("Für dich als Erzieherin..." → weg)
- Entferne abschwächende Floskeln aus dem claim_text; schreibe sie in kontext_modifikator
- Behalte Zahlen exakt, inklusive Einheit
- Deutschland-Bezug: "ja" bei expliziten DE-Bezügen; "nein" bei global; "unklar" bei mehrdeutig

JSON-OUTPUT-SCHEMA (nur dies, kein Preamble, keine Markdown-Blöcke):
[
  {{
    "claim_text": "Normalisierte, prüfbare Aussage",
    "original_wording": "Wörtlicher Ausschnitt, max. 200 Zeichen",
    "kontext_modifikator": "Einordnung wie 'laut WHO'; leer wenn keine",
    "claim_type": "Zahl | Definition | Studienlage | Ursache-Wirkung | Vergleich | qualitativ",
    "deutschland_bezug": "ja | nein | unklar",
    "themen_tag": "Naehrstoff | Verarbeitung | Gesundheit | Herkunft | Wirtschaft | Ethik | andere"
  }}
]

REGELN
1. Keine harten Claims → exakt `[]`.
2. Keine Dubletten innerhalb derselben Antwort.
3. Nicht interpretieren, nur extrahieren.
4. Bei Unsicherheit über Härte → extrahieren mit claim_type "qualitativ".
5. Nur JSON, kein Markdown, keine Backticks.

INPUT
Prompt: {prompt_text}
Persona: {persona_label}
Modell: {model}

Antwort:
\"\"\"
{text}
\"\"\"

OUTPUT (nur JSON-Array):"""


def extract_claims(client, prompt_text, persona_label, model_name, response_text, model_id="claude-opus-4-7"):
    """Extrahiert Claims für eine einzelne Antwort via API."""
    user_msg = EXTRACTION_USER_TEMPLATE.format(
        prompt_text=prompt_text,
        persona_label=persona_label,
        model=model_name,
        text=response_text[:6000]  # safety cap
    )
    
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=model_id,
                max_tokens=4000,
                system=EXTRACTION_SYSTEM,
                messages=[{"role": "user", "content": user_msg}]
            )
            text = resp.content[0].text.strip()
            # Robustes Parsing
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            claims = json.loads(text)
            return claims, None
        except json.JSONDecodeError as e:
            return None, f"JSON-Parse-Fehler: {e}; raw: {text[:200]}"
        except Exception as e:
            if "rate" in str(e).lower() or "overloaded" in str(e).lower():
                wait = 2 ** attempt
                print(f"  Rate-Limit, warte {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return None, f"API-Fehler: {e}"
    return None, "Max retries reached"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pilot", "full", "topic"], required=True)
    ap.add_argument("--topic", default="Ernährung", help="Topic-Filter wenn mode=topic")
    ap.add_argument("--input", default="ResponsesWhitepaperPromptSetApril2026_3.csv")
    ap.add_argument("--output", default="claims_raw.csv")
    ap.add_argument("--resume", action="store_true", help="aus bestehender Output-CSV fortsetzen")
    ap.add_argument("--limit", type=int, default=None, help="nur N Antworten verarbeiten (Debug)")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt.")
        sys.exit(1)

    df = pd.read_csv(args.input)
    df = df[df["status"] == "success"]
    df = df[df["text"].fillna("").str.len() > 300]

    if args.mode == "pilot":
        pilot = pd.read_csv("pilot_20.csv", sep=";")
        df = df[df["response_id"].isin(pilot["response_id"])]
    elif args.mode == "topic":
        df = df[df["prompt_topic"] == args.topic]
    # mode=full: alle Antworten

    if args.limit:
        df = df.head(args.limit)

    print(f"Zu verarbeitende Antworten: {len(df)}")

    # Resume-Logik
    processed_ids = set()
    if args.resume and Path(args.output).exists():
        existing = pd.read_csv(args.output, sep=";")
        processed_ids = set(existing["response_id"].unique())
        print(f"Fortsetzen: {len(processed_ids)} Antworten bereits verarbeitet.")

    # Header schreiben, wenn neue Datei
    if not Path(args.output).exists() or not args.resume:
        header = "response_id;prompt_id;model_short;persona_label;claim_num;claim_text;original_wording;kontext_modifikator;claim_type;deutschland_bezug;themen_tag\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    client = Anthropic()
    n_ok, n_fail = 0, 0
    errors = []

    for idx, row in df.iterrows():
        if row["response_id"] in processed_ids:
            continue

        short_model = (
            "Claude" if "claude" in row["model_id"].lower() else
            "GPT" if "gpt" in row["model_id"].lower() else
            "Gemini" if "gemini" in row["model_id"].lower() else
            "Grok" if "grok" in row["model_id"].lower() else "other"
        )

        claims, err = extract_claims(
            client,
            row["prompt_text"],
            row.get("persona_label", row.get("persona", "")),
            short_model,
            row["text"],
        )

        if err:
            print(f"  [{idx}] FAIL {row['response_id']}: {err}")
            errors.append((row["response_id"], err))
            n_fail += 1
            continue

        # Ans CSV anhängen
        with open(args.output, "a", encoding="utf-8") as f:
            for i, c in enumerate(claims, 1):
                # CSV-escape Semikolons und Newlines in Text
                def clean(s):
                    if s is None:
                        return ""
                    return str(s).replace(";", ",").replace("\n", " ").replace("\r", " ")
                f.write(f"{row['response_id']};{row['prompt_id']};{short_model};{clean(row.get('persona_label', row.get('persona', '')))};{i};{clean(c.get('claim_text',''))};{clean(c.get('original_wording',''))};{clean(c.get('kontext_modifikator',''))};{clean(c.get('claim_type',''))};{clean(c.get('deutschland_bezug',''))};{clean(c.get('themen_tag',''))}\n")

        n_ok += 1
        if n_ok % 10 == 0:
            print(f"  [{n_ok}/{len(df)}] verarbeitet")

        time.sleep(0.2)  # leichtes Throttling

    print(f"\nFertig. Erfolg: {n_ok} · Fehler: {n_fail}")
    if errors:
        with open("extraction_errors.log", "w") as f:
            for rid, err in errors:
                f.write(f"{rid}\t{err}\n")
        print("Fehler siehe extraction_errors.log")


if __name__ == "__main__":
    main()
