#!/usr/bin/env python3
"""
Interactive Airtable Field Setup Helper

Dieses Script prüft welche Felder in der Airtable-Tabelle fehlen
und gibt Anweisungen zum manuellen Hinzufügen.

Da die Airtable API keine Field-Creation erlaubt, musst du die Felder
manuell über die Web UI hinzufügen.
"""

import os
from pyairtable import Api

# Required fields für verified_facts
REQUIRED_FIELDS = {
    "fact_id": "singleLineText",
    "canonical_text": "multilineText",
    "category": "singleSelect",
    "bewertung": "singleSelect",
    "konfidenz": "singleSelect",
    "numerischer_wert": "singleLineText",
    "einheit": "singleLineText",
    "begründung": "multilineText",
    "korrektur": "multilineText",
    "quellen": "multilineText",
    "quellen_qualität": "singleSelect",
    "erstellt_am": "date",
    "opus_claim_id": "singleLineText",
    "keywords": "multilineText",
    "verified_by": "singleSelect",
    "kontext_hinweis": "multilineText",
}

SELECT_OPTIONS = {
    "category": ["Emissionen", "Nährstoffe", "Wirtschaft", "Tierwohl", "Herkunft", "Verarbeitung", "Gesundheit", "Ethik", "andere"],
    "bewertung": ["RICHTIG", "WEITGEHEND_RICHTIG", "TEILWEISE_RICHTIG", "IRREFÜHREND", "FALSCH"],
    "konfidenz": ["hoch", "mittel", "niedrig"],
    "quellen_qualität": ["gut", "schwach"],
    "verified_by": ["Opus Research", "Manual Review", "Scientific Study", "Government Report"],
}


def check_fields():
    """Prüft welche Felder fehlen."""

    api_token = os.environ.get("AIRTABLE_API_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_id = os.environ.get("AIRTABLE_TABLE_NAME")

    if not all([api_token, base_id, table_id]):
        print("ERROR: Environment variables nicht gesetzt!")
        print("Stelle sicher dass .env geladen ist:")
        print("  set -a; source .env; set +a")
        return False

    # Get table schema
    api = Api(api_token)
    base = api.base(base_id)
    schema = base.schema()

    # Find table
    our_table = None
    for table in schema.tables:
        if table.id == table_id:
            our_table = table
            break

    if not our_table:
        print(f"ERROR: Tabelle {table_id} nicht gefunden!")
        return False

    print(f"\n{'='*70}")
    print(f"AIRTABLE FIELD SETUP - {our_table.name}")
    print(f"{'='*70}\n")

    # Check existing fields
    existing_fields = {field.name: field.type for field in our_table.fields}

    print(f"Existierende Felder ({len(existing_fields)}):")
    for name, type_ in existing_fields.items():
        print(f"  ✓ {name:30s} ({type_})")

    # Find missing fields
    missing_fields = []
    for field_name, field_type in REQUIRED_FIELDS.items():
        if field_name not in existing_fields:
            missing_fields.append((field_name, field_type))

    if not missing_fields:
        print(f"\n✅ Alle benötigten Felder sind vorhanden!")
        print(f"\nDu kannst jetzt den Import starten:")
        print(f"  python airtable_import.py --mode import --input opus_research_test.jsonl")
        return True

    # Show instructions for missing fields
    print(f"\n❌ Fehlende Felder ({len(missing_fields)}):\n")

    print("ANLEITUNG:")
    print("1. Öffne Airtable im Browser:")
    print(f"   https://airtable.com/{base_id}/{table_id}")
    print("\n2. Füge folgende Felder hinzu (klicke auf '+' rechts neben den Spalten):\n")

    for i, (field_name, field_type) in enumerate(missing_fields, 1):
        print(f"\n{i:2d}. Feld: {field_name}")
        print(f"    Typ: {field_type}")

        if field_name in SELECT_OPTIONS:
            print(f"    Optionen:")
            for opt in SELECT_OPTIONS[field_name]:
                print(f"      - {opt}")

    print(f"\n\n{'='*70}")
    print("Nachdem du alle Felder hinzugefügt hast, führe dieses Script erneut aus:")
    print("  python setup_airtable_fields.py")
    print(f"{'='*70}\n")

    return False


if __name__ == "__main__":
    success = check_fields()
    exit(0 if success else 1)
