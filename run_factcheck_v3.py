"""
KI-Produkt-Faktencheck · Automatisches Fact-Checking V3

MULTI-LAYER-RECHERCHE:
- Layer 1: Perplexity (schnell, aktuell)
- Layer 2: Google Scholar (wissenschaftlich)
- Layer 3: PubMed (medizinisch/Nährwerte) - NEU
- Layer 4: USDA FoodData Central (exakte Nährwerte) - NEU

Ziel: NICHT_PRÜFBAR-Rate von 33% auf <25% reduzieren.
"""

import os
import sys
import time
import json
import argparse
import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

try:
    import pandas as pd
    from anthropic import AsyncAnthropic
    from scholarly import scholarly
    import aiohttp
except ImportError:
    print("Fehler: pip install anthropic pandas scholarly aiohttp")
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
- Bevorzuge PubMed/USDA > Google Scholar > Web-Quellen
- Bei widersprüchlichen Quellen: "TEILWEISE_RICHTIG" + Erklärung
- Bei fehlenden Quellen: "NICHT_PRÜFBAR" + Grund angeben
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


async def search_web_perplexity(claim: str, api_key: str) -> Optional[str]:
    """Layer 1: Perplexity Web-Suche."""
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
    except Exception:
        pass

    return None


async def search_google_scholar(claim: str, max_results: int = 5) -> Optional[str]:
    """Layer 2: Google Scholar Papers."""
    try:
        loop = asyncio.get_event_loop()

        def _search():
            keywords = claim[:100]
            search_query = scholarly.search_pubs(keywords)
            results = []

            for i, pub in enumerate(search_query):
                if i >= max_results:
                    break

                try:
                    title = pub.get('bib', {}).get('title', 'Kein Titel')
                    author = pub.get('bib', {}).get('author', [''])[0] if pub.get('bib', {}).get('author') else 'Unbekannt'
                    year = pub.get('bib', {}).get('pub_year', 'o.J.')
                    abstract = pub.get('bib', {}).get('abstract', '')[:200]

                    results.append(f"[{i+1}] {title} ({author}, {year})")
                    if abstract:
                        results.append(f"    Abstract: {abstract}...")
                except Exception:
                    continue

            if not results:
                return None

            return "GOOGLE SCHOLAR:\n\n" + "\n".join(results)

        result = await loop.run_in_executor(None, _search)
        return result
    except Exception:
        return None


async def search_pubmed(claim: str, max_results: int = 5) -> Optional[str]:
    """Layer 3: PubMed medizinische/Nährwert-Studien."""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Suche nach Paper-IDs
            search_url = f"{base_url}esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": claim[:200],
                "retmax": max_results,
                "retmode": "json"
            }

            async with session.get(search_url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                ids = data.get("esearchresult", {}).get("idlist", [])

            if not ids:
                return None

            # 2. Hole Paper-Details
            fetch_url = f"{base_url}efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(ids[:max_results]),
                "retmode": "xml"
            }

            async with session.get(fetch_url, params=params) as resp:
                if resp.status != 200:
                    return None
                xml_text = await resp.text()

            # 3. Parse XML
            root = ET.fromstring(xml_text)
            results = []

            for i, article in enumerate(root.findall(".//PubmedArticle"), 1):
                try:
                    title_elem = article.find(".//ArticleTitle")
                    title = title_elem.text if title_elem is not None else "Kein Titel"

                    year_elem = article.find(".//PubDate/Year")
                    year = year_elem.text if year_elem is not None else "o.J."

                    abstract_elem = article.find(".//AbstractText")
                    abstract = abstract_elem.text if abstract_elem is not None else ""

                    results.append(f"[{i}] {title} ({year})")
                    if abstract:
                        results.append(f"    Abstract: {abstract[:200]}...")
                except Exception:
                    continue

            if not results:
                return None

            return "PUBMED:\n\n" + "\n".join(results)

    except Exception:
        return None


async def search_usda_fooddata(claim: str, api_key: Optional[str] = None) -> Optional[str]:
    """Layer 4: USDA FoodData Central für exakte Nährwerte."""
    if not api_key or api_key == "mock":
        return None

    # Extrahiere Lebensmittel-Name aus Claim (sehr simpel)
    food_keywords = ["Produkt", "Käse", "Joghurt", "Butter", "Quark", "Grünkohl", "Spinat"]
    food_name = None

    for keyword in food_keywords:
        if keyword.lower() in claim.lower():
            food_name = keyword
            break

    if not food_name:
        return None

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": food_name,
        "api_key": api_key,
        "pageSize": 3
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

                foods = data.get("foods", [])
                if not foods:
                    return None

                results = []
                for i, food in enumerate(foods[:3], 1):
                    desc = food.get("description", "Unbekannt")
                    nutrients = food.get("foodNutrients", [])

                    # Wichtige Nährstoffe extrahieren
                    nutrient_strs = []
                    for n in nutrients[:5]:  # Top 5
                        name = n.get("nutrientName", "")
                        value = n.get("value", 0)
                        unit = n.get("unitName", "")
                        nutrient_strs.append(f"{name}: {value}{unit}")

                    results.append(f"[{i}] {desc}")
                    if nutrient_strs:
                        results.append(f"    {', '.join(nutrient_strs)}")

                return "USDA FOODDATA CENTRAL:\n\n" + "\n".join(results)

    except Exception:
        return None


async def multi_layer_search(
    claim: str,
    claim_topics: List[str],
    perplexity_key: str,
    usda_key: Optional[str] = None
) -> Tuple[str, str]:
    """
    Multi-Layer-Fallback-Suche.

    Returns:
        (sources_text, source_type)
    """

    # Layer 1: Perplexity (immer zuerst versuchen)
    result = await search_web_perplexity(claim, perplexity_key)
    if result:
        return result, "perplexity"

    # Layer 2: Google Scholar (allgemein wissenschaftlich)
    print(f"      → Perplexity failed, trying Google Scholar...", flush=True)
    result = await search_google_scholar(claim)
    if result:
        return result, "scholar"

    # Layer 3: PubMed (für Gesundheit/Nährwert-Claims)
    if any(topic in claim_topics for topic in ["Gesundheit", "Naehrstoff"]):
        print(f"      → Scholar failed, trying PubMed (health/nutrition)...", flush=True)
        result = await search_pubmed(claim)
        if result:
            return result, "pubmed"

    # Layer 4: USDA FoodData (für exakte Nährwert-Claims)
    if "Naehrstoff" in claim_topics and any(unit in claim for unit in ["µg", "mg", "g/", "mg/"]):
        if usda_key:
            print(f"      → PubMed failed, trying USDA FoodData (exact nutrients)...", flush=True)
            result = await search_usda_fooddata(claim, usda_key)
            if result:
                return result, "usda"

    # Keine Quellen gefunden
    return "Keine Quellen verfügbar (alle Suchquellen erschöpft).", "none"


async def factcheck_claim_async(
    client: AsyncAnthropic,
    claim_row: Dict,
    perplexity_key: str,
    usda_key: Optional[str],
    semaphore: asyncio.Semaphore,
    model_id: str = "claude-sonnet-4-20250514"
) -> Tuple[str, Dict, Dict]:
    """Fact-checkt einen einzelnen Claim mit Multi-Layer-Recherche."""

    canonical_id = claim_row["canonical_id"]
    claim_text = claim_row["canonical_text"]
    claim_topics = claim_row.get("topics", "").split(",")

    async with semaphore:
        # 1. Multi-Layer-Recherche
        print(f"  [{canonical_id}] Recherchiere...", flush=True)
        sources, source_type = await multi_layer_search(
            claim_text,
            claim_topics,
            perplexity_key,
            usda_key
        )

        # 2. Claude Fact-Check
        user_msg = FACTCHECK_USER_TEMPLATE.format(
            claim_text=claim_text,
            sources=sources,
            claim_type=claim_row.get("claim_types", "unbekannt"),
            deutschland_bezug=claim_row.get("deutschland_bezug_verteilung", "unklar"),
            frequency=claim_row["frequency"],
            models=claim_row["models_covering"]
        )

        stats = {"input_tokens": 0, "output_tokens": 0, "source_type": source_type}

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
                    # Auto-Grund bei NICHT_PRÜFBAR ohne Grund
                    if result["bewertung"] == "NICHT_PRÜFBAR" and not result.get("nicht_pruefbar_grund"):
                        if source_type == "none":
                            result["nicht_pruefbar_grund"] = "technisch"

                    print(f"  [{canonical_id}] ✓ {result['bewertung']} (Konfidenz: {result['konfidenz']:.2f}, Quellen: {source_type})", flush=True)
                    return canonical_id, result, stats

            except json.JSONDecodeError:
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                if "rate" in str(e).lower():
                    await asyncio.sleep(2 ** attempt)
                    continue
                return canonical_id, None, {**stats, "error": str(e)}

        return canonical_id, None, {**stats, "error": "Parse-Fehler nach 3 Versuchen"}


async def process_batch(
    client: AsyncAnthropic,
    claims: List[Dict],
    perplexity_key: str,
    usda_key: Optional[str],
    semaphore: asyncio.Semaphore,
    output_file: str,
    model_id: str,
    stats: Dict
) -> Tuple[int, int]:
    """Verarbeitet einen Batch parallel."""

    tasks = [
        factcheck_claim_async(client, claim, perplexity_key, usda_key, semaphore, model_id)
        for claim in claims
    ]

    results = await asyncio.gather(*tasks)

    n_ok, n_fail = 0, 0

    with open(output_file, "a", encoding="utf-8") as f:
        for canonical_id, result, call_stats in results:
            stats["total_input_tokens"] += call_stats.get("input_tokens", 0)
            stats["total_output_tokens"] += call_stats.get("output_tokens", 0)

            # Quellen-Typ tracking
            source_type = call_stats.get("source_type", "unknown")
            stats["source_types"][source_type] += 1

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
                f"{result.get('nicht_pruefbar_grund', '')};"
                f"{source_type}\n"
            )

            n_ok += 1
            stats["bewertungen"][result["bewertung"]] += 1

    return n_ok, n_fail


async def main_async(args):
    """Haupt-Async-Funktion."""

    # API Keys prüfen
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    usda_key = os.getenv("USDA_API_KEY")  # Optional

    if not anthropic_key:
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt")
        sys.exit(1)

    if not perplexity_key:
        print("⚠️  Warnung: PERPLEXITY_API_KEY nicht gesetzt. Nur Scholar/PubMed/USDA werden verwendet.")
        perplexity_key = "mock"

    if not usda_key:
        print("⚠️  Info: USDA_API_KEY nicht gesetzt. USDA FoodData Layer wird übersprungen.")

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
        header = "canonical_id;canonical_text;frequency;models_covering;topics;bewertung;konfidenz;begründung;korrektur;quellen_qualität;kontext_hinweis;nicht_pruefbar_grund;source_type\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    # Stats
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "bewertungen": defaultdict(int),
        "source_types": defaultdict(int)
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
            client, batch, perplexity_key, usda_key, semaphore, args.output, args.model, stats
        )

        total_ok += n_ok
        total_fail += n_fail

        # Progress
        elapsed = time.time() - start_time
        rate = total_ok / (elapsed / 60) if elapsed > 0 else 0
        eta = (len(claims) - total_ok) / rate if rate > 0 else 0

        print(f"\nProgress: {total_ok}/{len(claims)} | Rate: {rate:.1f} claims/min | ETA: {eta:.1f}min")

    # Finale Stats
    elapsed = time.time() - start_time
    input_cost = (stats["total_input_tokens"] / 1_000_000) * 3.0
    output_cost = (stats["total_output_tokens"] / 1_000_000) * 15.0

    print(f"\n{'='*70}")
    print("FERTIG")
    print(f"{'='*70}")
    print(f"Erfolg: {total_ok} | Fehler: {total_fail}")
    print(f"Laufzeit: {elapsed/60:.1f} min")

    print(f"\nQuellen-Verteilung:")
    for source, count in sorted(stats["source_types"].items(), key=lambda x: -x[1]):
        pct = (count / total_ok * 100) if total_ok > 0 else 0
        print(f"  {source:15s}: {count:4d} ({pct:.1f}%)")

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
    ap = argparse.ArgumentParser(description="Automatisches Fact-Checking V3 (Multi-Layer)")
    ap.add_argument("--mode", choices=["sample", "priority", "all"], required=True)
    ap.add_argument("--input", default="claims_canonical.csv")
    ap.add_argument("--output", default="claims_factchecked_v3.csv")
    ap.add_argument("--model", default="claude-sonnet-4-20250514")
    ap.add_argument("--parallel", type=int, default=3, help="Parallele Checks")
    ap.add_argument("--limit", type=int, default=10, help="Limit für sample-Modus")
    ap.add_argument("--min-frequency", type=int, default=50, help="Min Frequency für priority-Modus")
    ap.add_argument("--resume", action="store_true")

    args = ap.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
