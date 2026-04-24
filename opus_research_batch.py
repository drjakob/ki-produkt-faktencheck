#!/usr/bin/env python3
"""
Opus 4.7 Deep Research Script für NICHT_PRÜFBAR Claims

Dieses Script verwendet Claude Opus 4.7 um tiefe Recherchen für Claims durchzuführen,
die von den Standard-APIs nicht beantwortet werden konnten.

Workflow:
1. Liest Top-100 NICHT_PRÜFBAR Claims aus CSV
2. Für jeden Claim: Opus 4.7 Deep Research mit erweiterten Suchstrategien
3. Strukturiertes JSON-Output für Airtable-Import
4. Resume-Funktionalität bei Unterbrechung

Erwartete Quellen:
- Google Scholar (manuelle Suche, verschiedene Suchbegriffe)
- Spezialisierte Journals (ResearchGate, JSTOR)
- Behörden/Industrie-Reports (BLE, Thünen, BMEL)
- Deutsche Fachportale (DLG, LfL Bayern)
"""

import os
import json
import argparse
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

import pandas as pd
from anthropic import AsyncAnthropic


# ============================
# OPUS RESEARCH PROMPT
# ============================

OPUS_RESEARCH_PROMPT = """Du bist ein wissenschaftlicher Recherche-Experte mit Zugang zu einer umfassenden Wissensbasis.

Deine Aufgabe ist es, den folgenden Claim durch tiefe Recherche zu verifizieren:

CLAIM: {claim}

KONTEXT:
- Dieser Claim konnte durch Standard-Web-APIs (Perplexity, USDA, Semantic Scholar, OpenAlex) nicht verifiziert werden
- Frequency: {frequency} (wie oft dieser Claim in LLM-Outputs vorkam)
- Topics: {topics}

RECHERCHE-STRATEGIE:

1. DEUTSCHE FACHQUELLEN (höchste Priorität):
   - Bundesanstalt für Landwirtschaft und Ernährung (BLE)
   - Thünen-Institut (Agrardaten, Studien)
   - Bundesministerium für Ernährung und Landwirtschaft (BMEL)
   - Bayerische Landesanstalt für Landwirtschaft (LfL)
   - Deutsche Landwirtschafts-Gesellschaft (DLG)
   - Statistisches Bundesamt (Destatis) - Agrarstatistiken
   - Deutsches Milchkontor (DMK), Molkerei-Verbände

2. WISSENSCHAFTLICHE LITERATUR:
   - Google Scholar mit deutschen UND englischen Suchbegriffen
   - ResearchGate
   - Fachzeitschriften (z.B. "Milchwissenschaft", "Journal of Dairy Science")
   - Agrarpolitische Berichte

3. BRANCHENBERICHTE & WHITEPAPERS:
   - Milchindustrie-Verband (MIV)
   - Internationale Dairy Federation (IDF)
   - FAO-Berichte (Food and Agriculture Organization)

4. SUCHBEGRIFF-VARIANTEN:
   - Verwende Synonyme (z.B. "Nutzungsdauer" → "Lebensalter", "Abgangsalter")
   - Deutsche + englische Begriffe
   - Spezifischere + allgemeinere Formulierungen

AUSGABEFORMAT (JSON):

{{
  "claim_id": "{claim_id}",
  "canonical_text": "{claim}",
  "bewertung": "RICHTIG|WEITGEHEND_RICHTIG|TEILWEISE_RICHTIG|IRREFÜHREND|FALSCH|NICHT_PRÜFBAR",
  "konfidenz": "hoch|mittel|niedrig",
  "begründung": "Detaillierte Begründung mit Quellenverweise",
  "korrektur": "Korrigierte Version des Claims (falls FALSCH/IRREFÜHREND), sonst null",
  "quellen_qualität": "gut|schwach",
  "numerischer_wert": "Falls Claim numerische Aussage enthält: exakter Wert mit Einheit, sonst null",
  "quellen": [
    {{
      "titel": "Titel der Quelle",
      "url": "https://...",
      "typ": "wissenschaftliche_studie|behördenbericht|branchenbericht|statistik",
      "jahr": 2023,
      "vertrauenswürdigkeit": "hoch|mittel|niedrig",
      "relevanz": "hoch|mittel|niedrig"
    }}
  ],
  "suchstrategie": "Beschreibung welche Suchbegriffe/Quellen verwendet wurden",
  "kontext_hinweis": "Wichtige Einschränkungen oder Kontextinformationen (optional)"
}}

WICHTIGE REGELN:

1. NICHT_PRÜFBAR nur als letztes Mittel:
   - Verwende alle Suchstrategien (deutsche Behörden, Branche, Wissenschaft)
   - Versuche mindestens 5 verschiedene Suchbegriff-Varianten
   - Falls wirklich keine Quellen: dokumentiere versuchte Strategien

2. NUMERISCHE CLAIMS:
   - Falls Claim Zahlen enthält: extrahiere "numerischer_wert" mit Einheit
   - Vergleiche mit gefundenen Daten (Toleranz ±5% für RICHTIG, ±15% für WEITGEHEND_RICHTIG)

3. QUELLENQUALITÄT:
   - "gut": Peer-reviewed Studies, Behördenberichte, offizielle Statistiken
   - "schwach": Blog-Posts, Industrie-Marketing, nicht-peer-reviewed

4. KONFIDENZ:
   - "hoch": Mehrere unabhängige hochwertige Quellen bestätigen
   - "mittel": Einzelne hochwertige Quelle ODER mehrere schwächere Quellen
   - "niedrig": Nur schwache Quellen ODER widersprüchliche Ergebnisse

5. OUTPUT NUR JSON:
   - Keine Erklärungen außerhalb des JSON
   - Valides JSON-Format
   - UTF-8 Encoding für deutsche Umlaute

Beginne jetzt mit der Recherche für den obigen Claim."""


# ============================
# RESEARCH FUNCTIONS
# ============================

async def research_claim_with_opus(
    claim_id: str,
    canonical_text: str,
    frequency: int,
    topics: str,
    client: AsyncAnthropic,
    model: str = "claude-opus-4-7"
) -> Dict:
    """
    Führt Deep Research für einen einzelnen Claim mit Opus 4.7 durch.

    Args:
        claim_id: Canonical ID (z.B. CC0767)
        canonical_text: Der zu prüfende Claim
        frequency: Häufigkeit des Claims
        topics: Themen-Tags
        client: AsyncAnthropic Client
        model: Model-ID (default: Opus 4.7)

    Returns:
        Dict mit Research-Ergebnissen im JSON-Format
    """

    prompt = OPUS_RESEARCH_PROMPT.format(
        claim=canonical_text,
        claim_id=claim_id,
        frequency=frequency,
        topics=topics
    )

    try:
        print(f"  → Recherchiere mit Opus 4.7...", flush=True)

        response = await client.messages.create(
            model=model,
            max_tokens=8000,  # Opus kann lange Recherche-Ergebnisse liefern
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extrahiere JSON aus Response
        content = response.content[0].text.strip()

        # Finde JSON-Block (zwischen ```json und ``` oder direkt als JSON)
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
        elif content.startswith("{"):
            json_str = content
        else:
            # Fallback: versuche JSON zu extrahieren
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            json_str = content[json_start:json_end]

        result = json.loads(json_str)

        # Validierung
        required_fields = ["bewertung", "konfidenz", "begründung", "quellen_qualität"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")

        # Ergänze Metadata
        result["research_timestamp"] = datetime.now().isoformat()
        result["model"] = model

        return result

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON Parse Error: {e}", flush=True)
        print(f"    Content: {content[:200]}...", flush=True)
        return {
            "claim_id": claim_id,
            "canonical_text": canonical_text,
            "bewertung": "NICHT_PRÜFBAR",
            "konfidenz": "niedrig",
            "begründung": f"Opus-Recherche fehlgeschlagen (JSON Parse Error): {str(e)}",
            "korrektur": None,
            "quellen_qualität": "schwach",
            "numerischer_wert": None,
            "quellen": [],
            "suchstrategie": "ERROR",
            "error": str(e)
        }

    except Exception as e:
        print(f"  ✗ Research Error: {e}", flush=True)
        return {
            "claim_id": claim_id,
            "canonical_text": canonical_text,
            "bewertung": "NICHT_PRÜFBAR",
            "konfidenz": "niedrig",
            "begründung": f"Opus-Recherche fehlgeschlagen: {str(e)}",
            "korrektur": None,
            "quellen_qualität": "schwach",
            "numerischer_wert": None,
            "quellen": [],
            "suchstrategie": "ERROR",
            "error": str(e)
        }


async def process_batch(
    claims_df: pd.DataFrame,
    output_file: str,
    resume: bool = True,
    start_index: int = 0,
    limit: Optional[int] = None
) -> None:
    """
    Verarbeitet Batch von Claims mit Opus Deep Research.

    Args:
        claims_df: DataFrame mit Claims (canonical_id, canonical_text, frequency, topics)
        output_file: Ausgabedatei für Ergebnisse (JSON Lines)
        resume: Falls True, überspringe bereits verarbeitete Claims
        start_index: Startindex für Processing
        limit: Maximale Anzahl zu verarbeitender Claims
    """

    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Lade existierende Ergebnisse für Resume
    processed_ids = set()
    if resume and Path(output_file).exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                result = json.loads(line)
                processed_ids.add(result["claim_id"])
        print(f"Resume-Modus: {len(processed_ids)} Claims bereits verarbeitet\n", flush=True)

    # Öffne Output-File im Append-Modus
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_claims = len(claims_df)
    if limit:
        total_claims = min(total_claims - start_index, limit)

    processed = 0
    skipped = 0

    with open(output_file, "a", encoding="utf-8") as f:
        for idx, row in claims_df.iloc[start_index:].iterrows():
            if limit and processed >= limit:
                break

            claim_id = row["canonical_id"]
            canonical_text = row["canonical_text"]
            frequency = row["frequency"]
            topics = row.get("topics", "")

            # Resume-Check
            if claim_id in processed_ids:
                skipped += 1
                continue

            processed += 1
            print(f"\n[{processed}/{total_claims}] {claim_id}: {canonical_text[:80]}...", flush=True)

            # Deep Research
            result = await research_claim_with_opus(
                claim_id=claim_id,
                canonical_text=canonical_text,
                frequency=frequency,
                topics=topics,
                client=client
            )

            # Schreibe JSON Line
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()

            # Status-Output
            bewertung = result.get("bewertung", "UNKNOWN")
            konfidenz = result.get("konfidenz", "unknown")
            num_quellen = len(result.get("quellen", []))
            print(f"  ✓ {bewertung} ({konfidenz}) | {num_quellen} Quellen", flush=True)

            # Rate-Limiting: ~1 Request pro 2 Sekunden (Opus ist teuer!)
            await asyncio.sleep(2)

    print(f"\n{'='*70}", flush=True)
    print(f"BATCH ABGESCHLOSSEN", flush=True)
    print(f"  Verarbeitet: {processed}", flush=True)
    print(f"  Übersprungen: {skipped}", flush=True)
    print(f"  Output: {output_file}", flush=True)


# ============================
# MAIN
# ============================

async def main():
    parser = argparse.ArgumentParser(
        description="Opus 4.7 Deep Research für NICHT_PRÜFBAR Claims"
    )
    parser.add_argument(
        "--input",
        default="claims_nicht_pruefbar_top100.csv",
        help="Input CSV mit NICHT_PRÜFBAR Claims"
    )
    parser.add_argument(
        "--output",
        default="opus_research_results.jsonl",
        help="Output JSON Lines Datei"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Überspringe bereits verarbeitete Claims"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Startindex (default: 0)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximale Anzahl zu verarbeitender Claims (default: alle)"
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-7",
        help="Model ID (default: claude-opus-4-7)"
    )

    args = parser.parse_args()

    # Validiere API Key
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", flush=True)
        return

    # Lade Claims
    print(f"Lade Claims aus {args.input}...", flush=True)
    df = pd.read_csv(args.input, delimiter=";")
    print(f"  {len(df)} Claims geladen\n", flush=True)

    # Validiere Spalten
    required_cols = ["canonical_id", "canonical_text", "frequency"]
    for col in required_cols:
        if col not in df.columns:
            print(f"ERROR: Missing column '{col}' in input CSV", flush=True)
            return

    # Starte Batch-Processing
    await process_batch(
        claims_df=df,
        output_file=args.output,
        resume=args.resume,
        start_index=args.start,
        limit=args.limit
    )


if __name__ == "__main__":
    asyncio.run(main())
