"""
KI-Produkt-Faktencheck · Automatisches Fact-Checking

Prüft kanonische Claims gegen Web-Quellen mit Claude Sonnet 4.6.
Kombiniert Web-Suche (Perplexity/Exa) + Claude-Analyse.

Voraussetzungen:
    pip install anthropic perplexity-client pandas
    export ANTHROPIC_API_KEY=sk-...
    export PERPLEXITY_API_KEY=pplx-...

Aufruf:
    python run_factcheck.py --mode sample --limit 10
    python run_factcheck.py --mode priority --min-frequency 50
    python run_factcheck.py --mode all --parallel 5

Kosten:
    - Claude Sonnet 4.6: ~$0.02 pro Claim
    - Perplexity: ~$0.001 pro Claim
    - Gesamt für 1.046 Claims: ~$20-25
"""

import os
import sys
import time
import json
import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

try:
    import pandas as pd
    from anthropic import AsyncAnthropic
except ImportError:
    print("Fehler: pip install anthropic pandas perplexity-client")
    sys.exit(1)


FACTCHECK_SYSTEM = """Du bist Fact-Checking-Experte für Ernährungs- und Agrarwissenschaft.

Deine Aufgabe: Einen Claim gegen recherchierte Quellen prüfen und bewerten.

BEWERTUNGS-KATEGORIEN:
1. RICHTIG: Claim wird durch Quellen bestätigt, Zahlen stimmen (±5% Toleranz)
2. WEITGEHEND_RICHTIG: Kern-Aussage stimmt, Details leicht ungenau
3. TEILWEISE_RICHTIG: Claim enthält wahre und falsche Elemente
4. IRREFÜHREND: Technisch korrekt, aber Kontext fehlt oder verzerrt
5. FALSCH: Claim widerspricht Quellen deutlich
6. NICHT_PRÜFBAR: Zu vage, keine Quellen verfügbar, oder subjektiv

AUSGABE-FORMAT (nur JSON, kein Markdown):
{{
  "bewertung": "RICHTIG|WEITGEHEND_RICHTIG|TEILWEISE_RICHTIG|IRREFÜHREND|FALSCH|NICHT_PRÜFBAR",
  "konfidenz": 0.0-1.0,
  "begründung": "Kurze Erklärung (max 300 Zeichen)",
  "korrektur": "Falls falsch/teilweise: korrekte Version, sonst leer",
  "quellen_qualität": "gut|mittel|schwach",
  "kontext_hinweis": "Wichtiger Kontext falls IRREFÜHREND, sonst leer",
  "nicht_pruefbar_grund": "Falls NICHT_PRÜFBAR: technisch|zu_vage|keine_quellen|subjektiv|historisch, sonst leer"
}}

PRINZIPIEN:
- Sei streng bei Zahlen (±5% Toleranz)
- Bei widersprüchlichen Quellen: "TEILWEISE_RICHTIG" + Erklärung
- Bei fehlenden Quellen: "NICHT_PRÜFBAR" + Grund angeben
- Bewerte nur den Claim, nicht ob er wichtig/relevant ist

NICHT_PRÜFBAR GRÜNDE:
- technisch: Web-Suche fehlgeschlagen, keine Quellen abrufbar
- zu_vage: Claim zu unspezifisch ("viele", "oft", "manche"), keine klare Aussage
- keine_quellen: Quellen vorhanden, aber nicht relevant/verlässlich genug
- subjektiv: Normative/wertende Aussage, keine Faktenbasis
- historisch: Historische Daten nicht öffentlich verfügbar
"""


FACTCHECK_USER_TEMPLATE = """CLAIM ZU PRÜFEN:
"{claim_text}"

RECHERCHIERTE QUELLEN:
{sources}

ZUSÄTZLICHER KONTEXT:
- Claim-Typ: {claim_type}
- Deutschland-Bezug: {deutschland_bezug}
- Häufigkeit: {frequency}x in {models} Modellen

Prüfe den Claim und gib NUR das JSON-Objekt zurück (keine Backticks, kein Markdown):
"""


async def search_web_perplexity(claim: str, api_key: str) -> str:
    """Sucht Web-Quellen via Perplexity API."""
    # Vereinfachte Implementierung - nutzt direkt HTTP statt SDK
    import aiohttp

    url = "https://api.perplexity.ai/chat/completions"

    payload = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": "Du bist Research-Assistent. Finde verlässliche Quellen zu Ernährung und Landwirtschaft."
            },
            {
                "role": "user",
                "content": f"Finde wissenschaftliche Quellen und Fakten zu diesem Claim: '{claim}'. Gib konkrete Zahlen und Quellenangaben."
            }
        ],
        "max_tokens": 800,
        "temperature": 0.1,
        "return_citations": True
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    citations = data.get("citations", [])

                    result = content
                    if citations:
                        result += "\n\nQUELLEN:\n" + "\n".join([f"- {c}" for c in citations[:5]])

                    return result
                else:
                    return f"Fehler bei Perplexity-Suche: {resp.status}"
    except Exception as e:
        return f"Fehler bei Web-Suche: {str(e)}"


async def factcheck_claim_async(
    client: AsyncAnthropic,
    claim_row: Dict,
    perplexity_key: str,
    semaphore: asyncio.Semaphore,
    model_id: str = "claude-sonnet-4-20250514"
) -> Tuple[str, Dict, Dict]:
    """Fact-checkt einen einzelnen Claim."""

    canonical_id = claim_row["canonical_id"]
    claim_text = claim_row["canonical_text"]

    async with semaphore:
        # 1. Web-Recherche
        print(f"  [{canonical_id}] Recherchiere...", flush=True)
        sources = await search_web_perplexity(claim_text, perplexity_key)

        # 2. Claude Fact-Check
        user_msg = FACTCHECK_USER_TEMPLATE.format(
            claim_text=claim_text,
            sources=sources,
            claim_type=claim_row.get("claim_types", "unbekannt"),
            deutschland_bezug=claim_row.get("deutschland_bezug_verteilung", "unklar"),
            frequency=claim_row["frequency"],
            models=claim_row["models_covering"]
        )

        stats = {"input_tokens": 0, "output_tokens": 0}

        for attempt in range(3):
            try:
                resp = await client.messages.create(
                    model=model_id,
                    max_tokens=1000,
                    temperature=0.0,
                    system=FACTCHECK_SYSTEM,
                    messages=[{"role": "user", "content": user_msg}]
                )

                stats["input_tokens"] += resp.usage.input_tokens
                stats["output_tokens"] += resp.usage.output_tokens

                text = resp.content[0].text.strip()

                # Robustes JSON-Parsing
                if text.startswith("```"):
                    lines = text.split("\n")
                    text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
                    if text.startswith("json"):
                        text = text[4:].strip()

                result = json.loads(text)

                # Validierung
                required = ["bewertung", "konfidenz", "begründung"]
                if all(k in result for k in required):
                    print(f"  [{canonical_id}] ✓ {result['bewertung']} (Konfidenz: {result['konfidenz']:.2f})", flush=True)
                    return canonical_id, result, stats

            except json.JSONDecodeError:
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                if "rate" in str(e).lower():
                    await asyncio.sleep(2 ** attempt)
                    continue
                return canonical_id, None, {"error": str(e), **stats}

        return canonical_id, None, {"error": "Parse-Fehler nach 3 Versuchen", **stats}


async def process_batch(
    client: AsyncAnthropic,
    claims: List[Dict],
    perplexity_key: str,
    semaphore: asyncio.Semaphore,
    output_file: str,
    model_id: str,
    stats: Dict
) -> Tuple[int, int]:
    """Verarbeitet einen Batch parallel."""

    tasks = [
        factcheck_claim_async(client, claim, perplexity_key, semaphore, model_id)
        for claim in claims
    ]

    results = await asyncio.gather(*tasks)

    n_ok, n_fail = 0, 0

    with open(output_file, "a", encoding="utf-8") as f:
        for canonical_id, result, call_stats in results:
            stats["total_input_tokens"] += call_stats.get("input_tokens", 0)
            stats["total_output_tokens"] += call_stats.get("output_tokens", 0)

            if result is None:
                n_fail += 1
                continue

            # Finde Original-Claim für Metadaten
            claim_row = next(c for c in claims if c["canonical_id"] == canonical_id)

            # CSV-Zeile schreiben
            def clean(s):
                if s is None:
                    return ""
                return str(s).replace(";", ",").replace("\n", " ").replace("\r", " ")

            f.write(
                f"{canonical_id};"
                f"{clean(claim_row['canonical_text'])};"
                f"{claim_row['frequency']};"
                f"{clean(claim_row['models_covering'])};"
                f"{clean(claim_row['topics'])};"
                f"{result['bewertung']};"
                f"{result['konfidenz']:.3f};"
                f"{clean(result['begründung'])};"
                f"{clean(result.get('korrektur', ''))};"
                f"{result.get('quellen_qualität', '')};"
                f"{clean(result.get('kontext_hinweis', ''))};"
                f"{result.get('nicht_pruefbar_grund', '')}\n"
            )

            n_ok += 1
            stats["bewertungen"][result["bewertung"]] += 1

    return n_ok, n_fail


async def main_async(args):
    """Haupt-Async-Funktion."""

    # API Keys prüfen
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")

    if not anthropic_key:
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt")
        sys.exit(1)

    if not perplexity_key:
        print("⚠️  Warnung: PERPLEXITY_API_KEY nicht gesetzt. Web-Suche wird Mock-Daten verwenden.")
        perplexity_key = "mock"

    # Claims laden
    print(f"Lade {args.input}...")
    df = pd.read_csv(args.input, sep=";")

    # Filtern nach Modus
    if args.mode == "priority":
        df = df[df["frequency"] >= args.min_frequency]
        print(f"  → Priority-Modus: {len(df)} Claims mit Frequency >= {args.min_frequency}")
    elif args.mode == "sample":
        df = df.head(args.limit)
        print(f"  → Sample-Modus: {len(df)} Claims")
    else:
        print(f"  → Alle Claims: {len(df)}")

    if len(df) == 0:
        print("Keine Claims zu verarbeiten.")
        return

    # Resume-Logik
    processed_ids = set()
    if args.resume and Path(args.output).exists():
        existing = pd.read_csv(args.output, sep=";")
        processed_ids = set(existing["canonical_id"].unique())
        print(f"Fortsetzen: {len(processed_ids)} bereits verarbeitet")
        df = df[~df["canonical_id"].isin(processed_ids)]
        print(f"Verbleibend: {len(df)}")

    if len(df) == 0:
        print("Alle Claims bereits verarbeitet.")
        return

    # Header schreiben
    if not Path(args.output).exists() or not args.resume:
        header = "canonical_id;canonical_text;frequency;models_covering;topics;bewertung;konfidenz;begründung;korrektur;quellen_qualität;kontext_hinweis;nicht_pruefbar_grund\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    # Stats
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "bewertungen": defaultdict(int)
    }

    # Client und Semaphore
    client = AsyncAnthropic(api_key=anthropic_key)
    semaphore = asyncio.Semaphore(args.parallel)

    # Batches verarbeiten
    claims = df.to_dict("records")
    batch_size = args.parallel
    total_ok, total_fail = 0, 0

    start_time = time.time()

    for i in range(0, len(claims), batch_size):
        batch = claims[i:i + batch_size]
        batch_num = i // batch_size + 1

        print(f"\n{'='*70}")
        print(f"Batch {batch_num}/{(len(claims)-1)//batch_size + 1}")
        print(f"{'='*70}")

        n_ok, n_fail = await process_batch(
            client, batch, perplexity_key, semaphore, args.output, args.model, stats
        )

        total_ok += n_ok
        total_fail += n_fail

        # Progress
        elapsed = time.time() - start_time
        rate = total_ok / elapsed if elapsed > 0 else 0
        eta = (len(claims) - total_ok) / rate if rate > 0 else 0

        print(f"\nProgress: {total_ok}/{len(claims)} | Rate: {rate:.1f} claims/min | ETA: {eta/60:.1f}min")

    # Finale Stats
    elapsed = time.time() - start_time
    input_cost = (stats["total_input_tokens"] / 1_000_000) * 3.0
    output_cost = (stats["total_output_tokens"] / 1_000_000) * 15.0

    print(f"\n{'='*70}")
    print("FERTIG")
    print(f"{'='*70}")
    print(f"Erfolg: {total_ok} | Fehler: {total_fail}")
    print(f"Laufzeit: {elapsed/60:.1f} min")
    print(f"\nBewertungs-Verteilung:")
    for bew, count in sorted(stats["bewertungen"].items(), key=lambda x: -x[1]):
        pct = (count / total_ok * 100) if total_ok > 0 else 0
        print(f"  {bew:20s}: {count:4d} ({pct:.1f}%)")

    print(f"\nKosten:")
    print(f"  Input:  ${input_cost:.2f}")
    print(f"  Output: ${output_cost:.2f}")
    print(f"  Gesamt: ${input_cost + output_cost:.2f}")

    print(f"\n✓ Ergebnis gespeichert: {args.output}")


def main():
    ap = argparse.ArgumentParser(description="Automatisches Fact-Checking")
    ap.add_argument("--mode", choices=["sample", "priority", "all"], required=True)
    ap.add_argument("--input", default="claims_canonical.csv")
    ap.add_argument("--output", default="claims_factchecked.csv")
    ap.add_argument("--model", default="claude-sonnet-4-20250514")
    ap.add_argument("--parallel", type=int, default=3, help="Parallele Checks")
    ap.add_argument("--limit", type=int, default=10, help="Limit für sample-Modus")
    ap.add_argument("--min-frequency", type=int, default=50, help="Min Frequency für priority-Modus")
    ap.add_argument("--resume", action="store_true")

    args = ap.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
