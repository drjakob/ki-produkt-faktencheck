#!/usr/bin/env python3
"""
Opus 4.7 Deep Research Script (PARALLELISIERT) für NICHT_PRÜFBAR Claims

WICHTIG: Diese Version verarbeitet Claims parallel für schnellere Durchlaufzeiten.
         Verwende mit Vorsicht - höhere Kosten und potenzielle Rate-Limit-Probleme!

Unterschiede zur sequenziellen Version:
- Parallele Verarbeitung mit asyncio.gather() und Semaphore
- Konfigurierbarer Parallelitätsgrad (--parallel)
- ~5-10x schneller als sequenzielle Version
- Höhere API-Kosten durch mehr simultane Requests

Workflow:
1. Liest Top-100 NICHT_PRÜFBAR Claims aus CSV
2. Verarbeitet N Claims parallel mit Opus 4.7 Deep Research
3. Strukturiertes JSON-Output für Airtable-Import
4. Resume-Funktionalität bei Unterbrechung

Usage:
    # Konservativ (5 parallel):
    python opus_research_parallel.py --input claims.csv --parallel 5

    # Aggressiv (10 parallel, schneller aber teurer):
    python opus_research_parallel.py --input claims.csv --parallel 10

    # Mit Resume:
    python opus_research_parallel.py --input claims.csv --parallel 5 --resume
"""

import os
import json
import argparse
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from collections import defaultdict

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
    semaphore: asyncio.Semaphore,
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
        semaphore: Asyncio Semaphore für Rate-Limiting
        model: Model-ID (default: Opus 4.7)

    Returns:
        Dict mit Research-Ergebnissen im JSON-Format
    """

    async with semaphore:  # Limitiert parallele Requests
        prompt = OPUS_RESEARCH_PROMPT.format(
            claim=canonical_text,
            claim_id=claim_id,
            frequency=frequency,
            topics=topics
        )

        try:
            print(f"  → [{claim_id}] Recherchiere mit Opus 4.7...", flush=True)

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

            # Erfolgs-Output
            bewertung = result.get("bewertung", "UNKNOWN")
            konfidenz = result.get("konfidenz", "unknown")
            num_quellen = len(result.get("quellen", []))
            print(f"  ✓ [{claim_id}] {bewertung} ({konfidenz}) | {num_quellen} Quellen", flush=True)

            return result

        except json.JSONDecodeError as e:
            print(f"  ✗ [{claim_id}] JSON Parse Error: {e}", flush=True)
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
            print(f"  ✗ [{claim_id}] Research Error: {e}", flush=True)
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


async def process_batch_parallel(
    claims_df: pd.DataFrame,
    output_file: str,
    resume: bool = True,
    start_index: int = 0,
    limit: Optional[int] = None,
    parallel: int = 5,
    model: str = "claude-opus-4-7"
) -> None:
    """
    Verarbeitet Batch von Claims mit paralleler Opus Deep Research.

    Args:
        claims_df: DataFrame mit Claims (canonical_id, canonical_text, frequency, topics)
        output_file: Ausgabedatei für Ergebnisse (JSON Lines)
        resume: Falls True, überspringe bereits verarbeitete Claims
        start_index: Startindex für Processing
        limit: Maximale Anzahl zu verarbeitender Claims
        parallel: Anzahl paralleler Requests (default: 5)
        model: Model-ID (default: claude-opus-4-7)
    """

    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Semaphore für Rate-Limiting
    semaphore = asyncio.Semaphore(parallel)

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

    # Filtere zu verarbeitende Claims
    claims_to_process = []
    for idx, row in claims_df.iloc[start_index:].iterrows():
        if limit and len(claims_to_process) >= limit:
            break

        claim_id = row["canonical_id"]

        # Resume-Check
        if claim_id in processed_ids:
            continue

        claims_to_process.append({
            "claim_id": claim_id,
            "canonical_text": row["canonical_text"],
            "frequency": row["frequency"],
            "topics": row.get("topics", "")
        })

    total_claims = len(claims_to_process)

    if total_claims == 0:
        print("Keine Claims zu verarbeiten.\n", flush=True)
        return

    print(f"Verarbeite {total_claims} Claims mit {parallel} parallelen Requests\n", flush=True)

    # Verarbeite in Batches
    batch_size = parallel * 2  # Größere Batches für bessere Auslastung

    with open(output_file, "a", encoding="utf-8") as f:
        for batch_start in range(0, total_claims, batch_size):
            batch = claims_to_process[batch_start:batch_start + batch_size]

            print(f"\n{'='*70}", flush=True)
            print(f"BATCH {batch_start // batch_size + 1}: Claims {batch_start + 1}-{min(batch_start + len(batch), total_claims)} von {total_claims}", flush=True)
            print(f"{'='*70}\n", flush=True)

            # Parallele Verarbeitung der Batch
            tasks = [
                research_claim_with_opus(
                    claim_id=claim["claim_id"],
                    canonical_text=claim["canonical_text"],
                    frequency=claim["frequency"],
                    topics=claim["topics"],
                    client=client,
                    semaphore=semaphore,
                    model=model
                )
                for claim in batch
            ]

            # Warte auf alle Tasks in dieser Batch
            results = await asyncio.gather(*tasks)

            # Schreibe Ergebnisse
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()

            print(f"\n✓ Batch abgeschlossen ({len(results)} Claims verarbeitet)", flush=True)

    print(f"\n{'='*70}", flush=True)
    print(f"BATCH PROCESSING ABGESCHLOSSEN", flush=True)
    print(f"  Verarbeitet: {total_claims}", flush=True)
    print(f"  Output: {output_file}", flush=True)
    print(f"  Parallelität: {parallel}", flush=True)


# ============================
# MAIN
# ============================

async def main():
    parser = argparse.ArgumentParser(
        description="Opus 4.7 Deep Research (PARALLEL) für NICHT_PRÜFBAR Claims"
    )
    parser.add_argument(
        "--input",
        default="claims_nicht_pruefbar_top100.csv",
        help="Input CSV mit NICHT_PRÜFBAR Claims"
    )
    parser.add_argument(
        "--output",
        default="opus_research_results_parallel.jsonl",
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
        "--parallel",
        type=int,
        default=5,
        help="Anzahl paralleler Requests (default: 5, empfohlen: 3-10)"
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

    # Warnung bei hoher Parallelität
    if args.parallel > 10:
        print(f"WARNUNG: --parallel {args.parallel} ist sehr hoch!", flush=True)
        print(f"  - Höhere Kosten durch viele simultane Opus-Requests", flush=True)
        print(f"  - Mögliche Rate-Limit-Probleme", flush=True)
        print(f"  - Empfohlen: 3-10 parallele Requests\n", flush=True)

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
    await process_batch_parallel(
        claims_df=df,
        output_file=args.output,
        resume=args.resume,
        start_index=args.start,
        limit=args.limit,
        parallel=args.parallel,
        model=args.model
    )


if __name__ == "__main__":
    asyncio.run(main())
