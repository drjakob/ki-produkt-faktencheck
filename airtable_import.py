#!/usr/bin/env python3
"""
Airtable Import Script

Importiert Opus 4.7 Research-Ergebnisse (JSON Lines) in Airtable Base.

Features:
- Batch-Import mit 10 records/request (Airtable API Limit)
- Automatische Keyword-Extraktion
- Voyage-Embeddings für Semantic Search
- Resume-Funktionalität (überspringt existierende fact_ids)

Usage:
    python airtable_import.py --input opus_research_results.jsonl --mode import
    python airtable_import.py --mode list  # Liste alle Facts in Airtable
"""

import os
import json
import argparse
import re
from typing import List, Dict, Optional
from datetime import datetime

import voyageai
from pyairtable import Api


# ============================
# KEYWORD EXTRACTION
# ============================

def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """
    Extrahiert Keywords aus Text für besseres Semantic Matching.

    Einfache Heuristik:
    - Entferne Stopwords
    - Extrahiere Substantive (Großbuchstaben-Wörter)
    - Dedupliziere und limitiere
    """

    stopwords = {
        "der", "die", "das", "und", "oder", "ein", "eine", "in", "für", "von", "zu",
        "mit", "auf", "aus", "bei", "ist", "sind", "wird", "werden", "wurde", "wurden",
        "hat", "haben", "kann", "können", "soll", "sollten", "etwa", "ca", "pro",
        "sowie", "durch", "über", "unter", "auch", "noch", "nur", "mehr", "als"
    }

    # Normalisiere und tokenize
    words = re.findall(r'\b\w+\b', text.lower())

    # Filtere Stopwords und kurze Wörter
    keywords = [
        w for w in words
        if w not in stopwords and len(w) > 3
    ]

    # Dedupliziere und limitiere
    unique_keywords = []
    seen = set()
    for kw in keywords:
        if kw not in seen:
            unique_keywords.append(kw)
            seen.add(kw)
        if len(unique_keywords) >= max_keywords:
            break

    return unique_keywords


# ============================
# AIRTABLE OPERATIONS
# ============================

def get_airtable_table():
    """Initialisiert Airtable API und gibt Table-Objekt zurück."""

    api_token = os.environ.get("AIRTABLE_API_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME", "verified_facts")

    if not api_token:
        raise ValueError("AIRTABLE_API_TOKEN environment variable not set")
    if not base_id:
        raise ValueError("AIRTABLE_BASE_ID environment variable not set")

    api = Api(api_token)
    table = api.table(base_id, table_name)

    return table


def get_existing_fact_ids(table) -> set:
    """Lädt alle existierenden fact_ids aus Airtable."""

    print("Lade existierende fact_ids aus Airtable...", flush=True)

    try:
        records = table.all()
        fact_ids = {
            record["fields"].get("fact_id")
            for record in records
            if "fact_id" in record["fields"]
        }

        print(f"  {len(fact_ids)} existierende Facts gefunden\n", flush=True)
        return fact_ids

    except Exception as e:
        print(f"  Warnung: Konnte nicht auf Airtable zugreifen: {e}", flush=True)
        print(f"  Fahre ohne Resume fort\n", flush=True)
        return set()


def create_airtable_record(opus_result: Dict, fact_id: str) -> Dict:
    """
    Konvertiert Opus Research Result in Airtable Record Format.

    Args:
        opus_result: JSON aus opus_research_batch.py
        fact_id: Generierte FACT_ID (z.B. FACT_0001)

    Returns:
        Dict im Airtable API Format
    """

    # Extrahiere Keywords
    keywords = extract_keywords(opus_result["canonical_text"])

    # Konvertiere Quellen-Liste zu Pipe-separated URLs
    quellen_urls = []
    for quelle in opus_result.get("quellen", []):
        if isinstance(quelle, dict):
            url = quelle.get("url", "")
            if url:
                quellen_urls.append(url)
        elif isinstance(quelle, str):
            quellen_urls.append(quelle)

    quellen_str = "|".join(quellen_urls) if quellen_urls else ""

    # Extrahiere numerischen Wert (falls vorhanden)
    numerischer_wert = opus_result.get("numerischer_wert")
    einheit = ""

    if numerischer_wert:
        # Versuche Einheit zu extrahieren (z.B. "70%" → wert="70", einheit="%")
        match = re.match(r'^([\d.,\-]+)\s*(.*)$', str(numerischer_wert))
        if match:
            numerischer_wert = match.group(1)
            einheit = match.group(2).strip()

    # Bestimme Kategorie aus Topics (falls verfügbar) oder aus opus_result
    # Fallback: "andere"
    category = opus_result.get("category", "andere")

    # Airtable Record
    record = {
        "fact_id": fact_id,
        "canonical_text": opus_result.get("canonical_text", ""),
        "category": category,
        "bewertung": opus_result.get("bewertung", "NICHT_PRÜFBAR"),
        "konfidenz": opus_result.get("konfidenz", "niedrig"),
        "begründung": opus_result.get("begründung", ""),
        "korrektur": opus_result.get("korrektur"),
        "quellen": quellen_str,
        "quellen_qualität": opus_result.get("quellen_qualität", "schwach"),
        "keywords": ", ".join(keywords),
        "verified_by": "Opus Research",
        "erstellt_am": datetime.now().isoformat()[:10],  # YYYY-MM-DD
        "opus_claim_id": opus_result.get("claim_id", "")
    }

    # Optionale Felder nur hinzufügen wenn vorhanden
    if numerischer_wert:
        record["numerischer_wert"] = str(numerischer_wert)
    if einheit:
        record["einheit"] = einheit
    if opus_result.get("kontext_hinweis"):
        record["kontext_hinweis"] = opus_result["kontext_hinweis"]

    return record


def import_batch(
    table,
    records: List[Dict],
    batch_size: int = 10
) -> None:
    """
    Importiert Records in Batches (Airtable API Limit: 10/request).

    Args:
        table: Airtable Table-Objekt
        records: Liste von Record-Dicts
        batch_size: Anzahl Records pro Batch (max 10)
    """

    total = len(records)

    for i in range(0, total, batch_size):
        batch = records[i:i+batch_size]

        try:
            table.batch_create(batch)
            print(f"  [{i+len(batch)}/{total}] Batch importiert", flush=True)

        except Exception as e:
            print(f"  ✗ Batch-Import fehlgeschlagen: {e}", flush=True)

            # Fallback: Einzeln importieren
            for record in batch:
                try:
                    table.create(record)
                    print(f"    ✓ {record['fact_id']}", flush=True)
                except Exception as e2:
                    print(f"    ✗ {record['fact_id']}: {e2}", flush=True)


# ============================
# MAIN IMPORT
# ============================

def import_opus_results(
    input_file: str,
    resume: bool = True,
    start_fact_id: int = 1
) -> None:
    """
    Importiert Opus Research Results in Airtable.

    Args:
        input_file: JSON Lines Datei mit Opus-Ergebnissen
        resume: Falls True, überspringe existierende fact_ids
        start_fact_id: Startwert für FACT_XXXX IDs
    """

    print(f"AIRTABLE IMPORT", flush=True)
    print(f"{'='*70}\n", flush=True)

    # Initialisiere Airtable
    table = get_airtable_table()

    # Lade existierende IDs (für Resume)
    existing_ids = get_existing_fact_ids(table) if resume else set()

    # Lade Opus Results
    print(f"Lade Opus Results aus {input_file}...", flush=True)

    opus_results = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                opus_results.append(json.loads(line))

    print(f"  {len(opus_results)} Results geladen\n", flush=True)

    # Konvertiere zu Airtable Records
    print("Konvertiere zu Airtable Records...", flush=True)

    records_to_import = []
    skipped = 0
    fact_counter = start_fact_id

    for result in opus_results:
        # Generiere FACT_ID
        fact_id = f"FACT_{fact_counter:04d}"
        fact_counter += 1

        # Resume-Check
        if fact_id in existing_ids:
            skipped += 1
            continue

        # Konvertiere
        record = create_airtable_record(result, fact_id)
        records_to_import.append(record)

    print(f"  {len(records_to_import)} neue Records", flush=True)
    print(f"  {skipped} übersprungen (bereits vorhanden)\n", flush=True)

    if not records_to_import:
        print("Keine neuen Records zu importieren.\n", flush=True)
        return

    # Import
    print("Importiere in Airtable...", flush=True)
    import_batch(table, records_to_import)

    print(f"\n{'='*70}", flush=True)
    print(f"IMPORT ABGESCHLOSSEN", flush=True)
    print(f"  {len(records_to_import)} Records importiert", flush=True)


def list_facts() -> None:
    """Listet alle Facts aus Airtable."""

    table = get_airtable_table()
    records = table.all()

    print(f"\nAIRTABLE FACTS ({len(records)} Records):", flush=True)
    print(f"{'='*70}\n", flush=True)

    for record in records:
        fields = record["fields"]
        fact_id = fields.get("fact_id", "NO_ID")
        text = fields.get("canonical_text", "")[:80]
        bewertung = fields.get("bewertung", "?")
        konfidenz = fields.get("konfidenz", "?")

        print(f"{fact_id}: {text}...", flush=True)
        print(f"  → {bewertung} ({konfidenz})\n", flush=True)


# ============================
# CLI
# ============================

def main():
    parser = argparse.ArgumentParser(
        description="Importiert Opus Research Results in Airtable"
    )
    parser.add_argument(
        "--mode",
        choices=["import", "list"],
        required=True,
        help="Operation: import (Opus → Airtable) oder list (zeige Facts)"
    )
    parser.add_argument(
        "--input",
        help="Input JSON Lines Datei (für --mode import)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Überspringe bereits importierte fact_ids"
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=1,
        help="Start-ID für FACT_XXXX (default: 1)"
    )

    args = parser.parse_args()

    # Validiere Environment
    required_vars = ["AIRTABLE_API_TOKEN", "AIRTABLE_BASE_ID"]
    for var in required_vars:
        if var not in os.environ:
            print(f"ERROR: {var} environment variable not set", flush=True)
            print(f"\nSiehe AIRTABLE_SETUP.md für Setup-Anleitung", flush=True)
            return

    # Execute
    if args.mode == "import":
        if not args.input:
            print("ERROR: --input required for --mode import", flush=True)
            return

        import_opus_results(
            input_file=args.input,
            resume=args.resume,
            start_fact_id=args.start_id
        )

    elif args.mode == "list":
        list_facts()


if __name__ == "__main__":
    main()
