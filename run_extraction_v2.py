"""
KI-Produkt-Faktencheck · Phase A · Vollauf V2

Async-parallele Claim-Extraktion mit Claude Sonnet 4.6.
Erweitert um: Fingerprints, Muster-Flags, robuste Validation, besseres Resume.

Aufruf:
    python run_extraction_v2.py --mode pilot --parallel 10
    python run_extraction_v2.py --mode ernaehrung --parallel 15
    python run_extraction_v2.py --mode scope_b --parallel 20 --model claude-opus-4-7

Kostenschätzung Sonnet 4.6 (Scope B, ~1.100 Antworten):
- Input: ~550k Tokens @ $3/M = $1.65
- Output: ~450k Tokens @ $15/M = $6.75
- Gesamt: ~$8.40
"""

import os
import sys
import time
import json
import argparse
import asyncio
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

try:
    from anthropic import AsyncAnthropic
    import pandas as pd
except ImportError:
    print("Fehler: anthropic und pandas erforderlich. pip install anthropic pandas")
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
    "claim_fingerprint": "normalisierte kurzform kleinbuchstaben max 60 zeichen",
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
6. claim_fingerprint: Kleinbuchstaben, Umlaute normalisieren (ä→a), nur alphanumerisch+Leerzeichen, max 60 Zeichen.

INPUT
Prompt: {prompt_text}
Persona: {persona_label}
Modell: {model}

Antwort:
\"\"\"
{text}
\"\"\"

OUTPUT (nur JSON-Array):"""


RETRY_PROMPT = """FEHLER: Deine Antwort war kein valides JSON.

Gib NUR das JSON-Array zurück. KEINE Backticks, KEIN Markdown, KEIN Preamble.
Beispiel korrektes Format:
[{{"claim_text":"...","claim_fingerprint":"...","original_wording":"...","kontext_modifikator":"","claim_type":"Zahl","deutschland_bezug":"unklar","themen_tag":"Naehrstoff"}}]

Falls keine Claims: []

Versuche es erneut:"""


def normalize_fingerprint(text: str) -> str:
    """Normalisiert Text für Claim-Fingerprint."""
    # Umlaute ersetzen
    replacements = {"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "Ä": "a", "Ö": "o", "Ü": "u"}
    for old, new in replacements.items():
        text = text.replace(old, new)

    # NFD-Normalisierung für diakritische Zeichen
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    # Kleinbuchstaben, nur alphanumerisch + Leerzeichen
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)

    # Mehrfache Leerzeichen reduzieren
    text = re.sub(r"\s+", " ", text).strip()

    # Max 60 Zeichen
    return text[:60]


def detect_muster_flags(claim_text: str) -> List[str]:
    """Erkennt Muster im Claim-Text und gibt Liste von Flags zurück."""
    flags = []
    text_lower = claim_text.lower()

    # vitamin_d_cluster
    if ("vitamin d" in text_lower or "vitamin-d" in text_lower) and "milch" in text_lower:
        flags.append("vitamin_d_cluster")

    # dge_empfehlung
    if "dge" in text_lower and ("empfiehlt" in text_lower or "empfehlung" in text_lower or "portion" in text_lower):
        flags.append("dge_empfehlung")

    # biol_wertigkeit
    if "biologische wertigkeit" in text_lower or re.search(r"\bbv\b", text_lower) or re.search(r"\bbw\b", text_lower):
        flags.append("biol_wertigkeit")

    # laktose_cluster
    if "laktose" in text_lower or "laktoseintolerant" in text_lower or "milchzucker" in text_lower:
        flags.append("laktose_cluster")

    # osteoporose_cluster
    if "osteoporose" in text_lower and "milch" in text_lower:
        flags.append("osteoporose_cluster")

    # klima_claim
    if "co2" in text_lower or "treibhausgas" in text_lower or "klimabilanz" in text_lower or "emissionen" in text_lower:
        flags.append("klima_claim")

    # us_referenz_verdacht (Tasse/Glas mit ml > 200)
    if ("tasse" in text_lower or "glas" in text_lower):
        # Suche nach Zahlen mit ml
        ml_matches = re.findall(r"(\d+)\s*ml", text_lower)
        if any(int(m) > 200 for m in ml_matches):
            flags.append("us_referenz_verdacht")

    # superlativ_verdacht
    if any(phrase in text_lower for phrase in ["am besten", "eines der besten", "führende", "beste quelle", "am meisten"]):
        flags.append("superlativ_verdacht")

    return flags


def validate_claim(claim: Dict) -> Optional[str]:
    """Validiert ein Claim-Objekt. Gibt Fehler-String zurück oder None."""
    required = ["claim_text", "original_wording", "claim_type", "deutschland_bezug", "themen_tag"]

    for field in required:
        if field not in claim or not claim[field]:
            return f"Pflichtfeld fehlt oder leer: {field}"

    # claim_fingerprint validieren oder generieren
    if "claim_fingerprint" not in claim or not claim["claim_fingerprint"]:
        claim["claim_fingerprint"] = normalize_fingerprint(claim["claim_text"])

    return None


async def extract_claims_async(
    client: AsyncAnthropic,
    row: Dict,
    semaphore: asyncio.Semaphore,
    model_id: str,
    stats: Dict
) -> Tuple[str, Optional[List[Dict]], Optional[str], Dict]:
    """Extrahiert Claims für eine Antwort (async, mit Retry-Logik und Stats)."""

    response_id = row["response_id"]
    short_model = (
        "Claude" if "claude" in row["model_id"].lower() else
        "GPT" if "gpt" in row["model_id"].lower() else
        "Gemini" if "gemini" in row["model_id"].lower() else
        "Grok" if "grok" in row["model_id"].lower() else "other"
    )

    user_msg = EXTRACTION_USER_TEMPLATE.format(
        prompt_text=row["prompt_text"][:500],  # gekürzt für Kosten
        persona_label=row.get("persona_label", row.get("persona", "")),
        model=short_model,
        text=row["text"][:6000]
    )

    call_stats = {"input_tokens": 0, "output_tokens": 0, "retries": 0}

    async with semaphore:
        # Erster Versuch
        for attempt in range(4):
            try:
                start_time = time.time()

                resp = await client.messages.create(
                    model=model_id,
                    max_tokens=4000,
                    system=EXTRACTION_SYSTEM,
                    messages=[{"role": "user", "content": user_msg}]
                )

                call_stats["input_tokens"] += resp.usage.input_tokens
                call_stats["output_tokens"] += resp.usage.output_tokens
                call_stats["duration"] = time.time() - start_time

                text = resp.content[0].text.strip()

                # Robustes Parsing
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
                    if text.startswith("json"):
                        text = text[4:].strip()

                claims = json.loads(text)

                # Validierung
                valid_claims = []
                for c in claims:
                    err = validate_claim(c)
                    if err:
                        continue  # Skip invalide Claims

                    # Muster-Flags hinzufügen
                    c["muster_hints"] = detect_muster_flags(c["claim_text"])
                    valid_claims.append(c)

                return response_id, valid_claims, None, call_stats

            except json.JSONDecodeError as e:
                # Retry mit verschärftem Prompt
                if attempt == 0:
                    call_stats["retries"] += 1
                    user_msg_retry = user_msg + "\n\n" + RETRY_PROMPT

                    try:
                        resp = await client.messages.create(
                            model=model_id,
                            max_tokens=4000,
                            system=EXTRACTION_SYSTEM,
                            messages=[{"role": "user", "content": user_msg_retry}]
                        )

                        call_stats["input_tokens"] += resp.usage.input_tokens
                        call_stats["output_tokens"] += resp.usage.output_tokens

                        text = resp.content[0].text.strip()
                        if text.startswith("```"):
                            lines = text.split("\n")
                            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

                        claims = json.loads(text)

                        valid_claims = []
                        for c in claims:
                            if validate_claim(c) is None:
                                c["muster_hints"] = detect_muster_flags(c["claim_text"])
                                valid_claims.append(c)

                        return response_id, valid_claims, None, call_stats
                    except:
                        pass

                return response_id, None, f"JSON-Parse-Fehler nach Retry: {str(e)[:100]}", call_stats

            except Exception as e:
                if "rate" in str(e).lower() or "overloaded" in str(e).lower():
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    call_stats["retries"] += 1
                    continue
                return response_id, None, f"API-Fehler: {str(e)[:100]}", call_stats

        return response_id, None, "Max retries erreicht", call_stats


def clean_csv_field(s) -> str:
    """Bereinigt Feld für CSV-Export."""
    if s is None:
        return ""
    if isinstance(s, list):
        s = "|".join(str(x) for x in s)
    return str(s).replace(";", ",").replace("\n", " ").replace("\r", " ")


async def process_batch(
    client: AsyncAnthropic,
    rows: List[Dict],
    semaphore: asyncio.Semaphore,
    output_file: str,
    model_id: str,
    stats: Dict
) -> Tuple[int, int, List]:
    """Verarbeitet einen Batch parallel."""

    tasks = [extract_claims_async(client, row, semaphore, model_id, stats) for row in rows]
    results = await asyncio.gather(*tasks)

    n_ok, n_fail = 0, 0
    errors = []

    with open(output_file, "a", encoding="utf-8") as f:
        for response_id, claims, err, call_stats in results:
            # Stats sammeln
            stats["total_input_tokens"] += call_stats["input_tokens"]
            stats["total_output_tokens"] += call_stats["output_tokens"]
            stats["total_retries"] += call_stats.get("retries", 0)
            if "duration" in call_stats:
                stats["durations"].append(call_stats["duration"])

            if err:
                errors.append({"response_id": response_id, "error": err})
                n_fail += 1
                continue

            # Finde row_data
            row = next(r for r in rows if r["response_id"] == response_id)

            short_model = (
                "Claude" if "claude" in row["model_id"].lower() else
                "GPT" if "gpt" in row["model_id"].lower() else
                "Gemini" if "gemini" in row["model_id"].lower() else
                "Grok" if "grok" in row["model_id"].lower() else "other"
            )

            if not claims:
                # no_claims Marker schreiben
                f.write(f"{response_id};{row['prompt_id']};{row.get('prompt_topic', '')};{short_model};"
                       f"{clean_csv_field(row.get('persona_label', ''))};0;NO_CLAIMS;;;;;;;;\n")
            else:
                for i, c in enumerate(claims, 1):
                    f.write(
                        f"{response_id};"
                        f"{row['prompt_id']};"
                        f"{row.get('prompt_topic', '')};"
                        f"{short_model};"
                        f"{clean_csv_field(row.get('persona_label', ''))};"
                        f"{i};"
                        f"{clean_csv_field(c.get('claim_text', ''))};"
                        f"{clean_csv_field(c.get('claim_fingerprint', ''))};"
                        f"{clean_csv_field(c.get('original_wording', ''))};"
                        f"{clean_csv_field(c.get('kontext_modifikator', ''))};"
                        f"{clean_csv_field(c.get('claim_type', ''))};"
                        f"{clean_csv_field(c.get('deutschland_bezug', ''))};"
                        f"{clean_csv_field(c.get('themen_tag', ''))};"
                        f"{clean_csv_field(c.get('muster_hints', []))}\n"
                    )

            n_ok += 1

    return n_ok, n_fail, errors


async def main_async(args):
    """Haupt-Async-Funktion."""

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt.")
        sys.exit(1)

    # CSV laden
    print(f"Lade {args.input}...")
    df = pd.read_csv(args.input)

    # Kurze Antworten dokumentieren
    short_answers = df[(df["status"] == "success") & (df["text"].fillna("").str.len() < 300)]
    if len(short_answers) > 0:
        short_log = []
        for _, row in short_answers.iterrows():
            short_log.append({
                "response_id": row["response_id"],
                "prompt_id": row.get("prompt_id", ""),
                "text_length": len(row["text"]) if pd.notna(row["text"]) else 0,
                "first_100_chars": row["text"][:100] if pd.notna(row["text"]) else ""
            })
        pd.DataFrame(short_log).to_csv("short_answers.csv", index=False, sep=";")
        print(f"  → {len(short_answers)} kurze Antworten (<300 Zeichen) in short_answers.csv dokumentiert")

    # Filtern
    df = df[df["status"] == "success"]
    df = df[df["text"].fillna("").str.len() >= 300]

    # Mode-Filter
    if args.mode == "pilot":
        if not Path("pilot_20.csv").exists():
            print("Fehler: pilot_20.csv nicht gefunden")
            sys.exit(1)
        pilot = pd.read_csv("pilot_20.csv", sep=";")
        df = df[df["response_id"].isin(pilot["response_id"])]
    elif args.mode == "ernaehrung":
        df = df[df["prompt_topic"] == "Ernährung"]
    elif args.mode == "scope_b":
        df = df[df["prompt_topic"].isin(["Ernährung", "Gesundheit"])]
    elif args.mode == "all_prio":
        if "priority" in df.columns:
            df = df[df["priority"] == "hoch"]
        else:
            print("Warnung: Spalte 'priority' nicht gefunden, verarbeite alle")

    if args.limit:
        df = df.head(args.limit)

    print(f"Zu verarbeitende Antworten: {len(df)}")

    # Resume-Logik (schärfer)
    processed_ids = set()
    if args.resume and Path(args.output).exists():
        existing = pd.read_csv(args.output, sep=";")
        # Nur IDs mit validen Claims oder NO_CLAIMS Marker
        valid_processed = existing[
            (existing["claim_text"].notna() & (existing["claim_text"] != "")) |
            (existing["claim_text"] == "NO_CLAIMS")
        ]
        processed_ids = set(valid_processed["response_id"].unique())
        print(f"Fortsetzen: {len(processed_ids)} Antworten bereits verarbeitet (valide).")
        df = df[~df["response_id"].isin(processed_ids)]
        print(f"Verbleibend: {len(df)}")

    if len(df) == 0:
        print("Keine Antworten zu verarbeiten.")
        return

    # Header schreiben
    if not Path(args.output).exists() or not args.resume:
        header = "response_id;prompt_id;prompt_topic;model_short;persona_label;claim_num;claim_text;claim_fingerprint;original_wording;kontext_modifikator;claim_type;deutschland_bezug;themen_tag;muster_hints\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    # Stats initialisieren
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_retries": 0,
        "durations": []
    }

    # Client und Semaphore
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    semaphore = asyncio.Semaphore(args.parallel)

    # Batches verarbeiten
    rows = df.to_dict("records")
    batch_size = args.parallel
    total_ok, total_fail = 0, 0
    all_errors = []

    start_time = time.time()

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_num = i // batch_size + 1

        n_ok, n_fail, errors = await process_batch(
            client, batch, semaphore, args.output, args.model, stats
        )

        total_ok += n_ok
        total_fail += n_fail
        all_errors.extend(errors)

        # Progress alle 20 Antworten oder bei jedem Batch
        if total_ok % 20 == 0 or batch_num == 1:
            elapsed = time.time() - start_time
            avg_time = elapsed / total_ok if total_ok > 0 else 0
            remaining = len(rows) - total_ok
            eta = avg_time * remaining

            print(f"  Batch {batch_num}: ✓ {n_ok} | ✗ {n_fail} | "
                  f"Gesamt: {total_ok}/{len(rows)} | "
                  f"ETA: {eta/60:.1f}min")

    # Finale Statistik
    elapsed = time.time() - start_time
    avg_duration = sum(stats["durations"]) / len(stats["durations"]) if stats["durations"] else 0

    print(f"\n{'='*70}")
    print(f"FERTIG")
    print(f"{'='*70}")
    print(f"Erfolg: {total_ok} | Fehler: {total_fail}")
    print(f"Laufzeit: {elapsed/60:.1f} Minuten")
    print(f"Ø API-Call: {avg_duration:.2f}s")
    print(f"Input-Tokens: {stats['total_input_tokens']:,}")
    print(f"Output-Tokens: {stats['total_output_tokens']:,}")
    print(f"Rate-Limit-Retries: {stats['total_retries']}")

    # Kostenschätzung
    input_cost = (stats["total_input_tokens"] / 1_000_000) * 3.0
    output_cost = (stats["total_output_tokens"] / 1_000_000) * 15.0
    total_cost = input_cost + output_cost
    print(f"\nKostenschätzung (Sonnet 4.6):")
    print(f"  Input:  ${input_cost:.2f}")
    print(f"  Output: ${output_cost:.2f}")
    print(f"  Gesamt: ${total_cost:.2f}")

    # Fehler loggen
    if all_errors:
        with open("extraction_errors.jsonl", "w", encoding="utf-8") as f:
            for err in all_errors:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
        print(f"\nFehler siehe extraction_errors.jsonl ({len(all_errors)} Einträge)")


def main():
    ap = argparse.ArgumentParser(description="KI-Produkt Claim-Extraktion V2")
    ap.add_argument("--mode", choices=["pilot", "ernaehrung", "scope_b", "all_prio"], required=True)
    ap.add_argument("--input", default="ResponsesWhitepaperPromptSetApril2026_3.csv")
    ap.add_argument("--output", default="claims_v2.csv")
    ap.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude Modell-ID")
    ap.add_argument("--parallel", type=int, default=15, help="Parallele API-Calls")
    ap.add_argument("--resume", action="store_true", help="Aus bestehender CSV fortsetzen")
    ap.add_argument("--limit", type=int, default=None, help="Max Antworten (Debug)")

    args = ap.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
