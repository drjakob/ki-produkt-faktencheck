"""
KI-Produkt-Faktencheck · Phase A · Parallel-Vollauf

Startet die Claim-Extraktion mit 75 parallelen Workers.
Verwendet Claude Sonnet 4.6 via Anthropic API.

Aufruf:
    python run_extraction_parallel.py --mode full --input "Responses-Whitepaper-Prompt-Set-April2026 (4).csv"
"""

import os
import sys
import json
import argparse
import asyncio
import pandas as pd
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    from anthropic import AsyncAnthropic
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


async def extract_claims_async(
    client: AsyncAnthropic,
    row_data: Dict,
    semaphore: asyncio.Semaphore,
    model_id: str = "claude-sonnet-4-20250514"
) -> Tuple[str, Optional[List[Dict]], Optional[str]]:
    """Extrahiert Claims für eine Antwort (async mit Semaphore)."""

    short_model = (
        "Claude" if "claude" in row_data["model_id"].lower() else
        "GPT" if "gpt" in row_data["model_id"].lower() else
        "Gemini" if "gemini" in row_data["model_id"].lower() else
        "Grok" if "grok" in row_data["model_id"].lower() else "other"
    )

    user_msg = EXTRACTION_USER_TEMPLATE.format(
        prompt_text=row_data["prompt_text"],
        persona_label=row_data.get("persona_label", row_data.get("persona", "")),
        model=short_model,
        text=row_data["text"][:6000]
    )

    async with semaphore:
        for attempt in range(4):
            try:
                resp = await client.messages.create(
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
                return row_data["response_id"], claims, None

            except json.JSONDecodeError as e:
                return row_data["response_id"], None, f"JSON-Parse-Fehler: {e}"
            except Exception as e:
                if "rate" in str(e).lower() or "overloaded" in str(e).lower():
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                return row_data["response_id"], None, f"API-Fehler: {e}"

        return row_data["response_id"], None, "Max retries reached"


def clean_csv_field(s) -> str:
    """Bereinigt Felder für CSV-Export."""
    if s is None:
        return ""
    return str(s).replace(";", ",").replace("\n", " ").replace("\r", " ")


async def process_batch(
    client: AsyncAnthropic,
    rows: List[Dict],
    semaphore: asyncio.Semaphore,
    output_file: str,
    model_id: str
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """Verarbeitet einen Batch parallel."""

    tasks = [extract_claims_async(client, row, semaphore, model_id) for row in rows]
    results = await asyncio.gather(*tasks)

    n_ok, n_fail = 0, 0
    errors = []

    # Schreibe in CSV
    with open(output_file, "a", encoding="utf-8") as f:
        for response_id, claims, err in results:
            if err:
                errors.append((response_id, err))
                n_fail += 1
                continue

            # Finde row_data für Metadaten
            row = next(r for r in rows if r["response_id"] == response_id)
            short_model = (
                "Claude" if "claude" in row["model_id"].lower() else
                "GPT" if "gpt" in row["model_id"].lower() else
                "Gemini" if "gemini" in row["model_id"].lower() else
                "Grok" if "grok" in row["model_id"].lower() else "other"
            )

            for i, c in enumerate(claims, 1):
                f.write(
                    f"{response_id};"
                    f"{row['prompt_id']};"
                    f"{short_model};"
                    f"{clean_csv_field(row.get('persona_label', row.get('persona', '')))};"
                    f"{i};"
                    f"{clean_csv_field(c.get('claim_text', ''))};"
                    f"{clean_csv_field(c.get('original_wording', ''))};"
                    f"{clean_csv_field(c.get('kontext_modifikator', ''))};"
                    f"{clean_csv_field(c.get('claim_type', ''))};"
                    f"{clean_csv_field(c.get('deutschland_bezug', ''))};"
                    f"{clean_csv_field(c.get('themen_tag', ''))}\n"
                )
            n_ok += 1

    return n_ok, n_fail, errors


async def main_async(args):
    """Haupt-Async-Funktion."""

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt.")
        sys.exit(1)

    # CSV laden und filtern
    print(f"Lade {args.input}...")
    df = pd.read_csv(args.input)
    df = df[df["status"] == "success"]
    df = df[df["text"].fillna("").str.len() > 300]

    if args.mode == "pilot":
        pilot = pd.read_csv("pilot_20.csv", sep=";")
        df = df[df["response_id"].isin(pilot["response_id"])]
    elif args.mode == "topic":
        df = df[df["prompt_topic"] == args.topic]

    if args.limit:
        df = df.head(args.limit)

    print(f"Zu verarbeitende Antworten: {len(df)}")

    # Resume-Logik
    processed_ids = set()
    if args.resume and Path(args.output).exists():
        existing = pd.read_csv(args.output, sep=";")
        processed_ids = set(existing["response_id"].unique())
        print(f"Fortsetzen: {len(processed_ids)} bereits verarbeitet.")
        df = df[~df["response_id"].isin(processed_ids)]
        print(f"Verbleibend: {len(df)}")

    # Header schreiben
    if not Path(args.output).exists() or not args.resume:
        header = "response_id;prompt_id;model_short;persona_label;claim_num;claim_text;original_wording;kontext_modifikator;claim_type;deutschland_bezug;themen_tag\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    # Async Client und Semaphore
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    semaphore = asyncio.Semaphore(args.workers)

    # In Batches verarbeiten
    rows = df.to_dict("records")
    batch_size = args.workers
    total_ok, total_fail = 0, 0
    all_errors = []

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        print(f"Batch {i // batch_size + 1}: verarbeite {len(batch)} Antworten...")

        n_ok, n_fail, errors = await process_batch(
            client, batch, semaphore, args.output, args.model_id
        )

        total_ok += n_ok
        total_fail += n_fail
        all_errors.extend(errors)

        print(f"  ✓ {n_ok} erfolgreich, ✗ {n_fail} fehlgeschlagen | Gesamt: {total_ok}/{len(rows)}")

    print(f"\n=== Fertig ===")
    print(f"Erfolg: {total_ok} · Fehler: {total_fail}")

    if all_errors:
        with open("extraction_errors.log", "w") as f:
            for rid, err in all_errors:
                f.write(f"{rid}\t{err}\n")
        print(f"Fehler siehe extraction_errors.log ({len(all_errors)} Einträge)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pilot", "full", "topic"], required=True)
    ap.add_argument("--topic", default="Ernährung")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="claims_raw.csv")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=75, help="Parallele Workers")
    ap.add_argument("--model-id", default="claude-sonnet-4-20250514", help="Claude Modell-ID")
    args = ap.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
