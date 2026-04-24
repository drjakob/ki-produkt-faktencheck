"""
KI-Produkt-Faktencheck · Automatisches Fact-Checking V5 mit Airtable

VERBESSERUNGEN gegenüber V4:
✓ Layer 0: Airtable - Kuratierte verifizierte Fakten (Semantic Search, checked FIRST!)
✓ Voyage-Embeddings für schnelle Semantic Similarity (Threshold: 0.85)
✓ 24h-Cache für Airtable-Embeddings (Performance-Optimierung)

VERBESSERUNGEN gegenüber V2:
✓ Kategorische Konfidenz (hoch/mittel/niedrig) statt irreführender numerischer Werte
✓ Quellen-URLs werden extrahiert und gespeichert für manuelle Verifikation
✓ Konsistenz-Checks: source_type=none MUSS bewertung=NICHT_PRÜFBAR sein
✓ quellen_qualität wird vom LLM basierend auf tatsächlichen Quellen bewertet
✓ Deutsch→Englisch-Übersetzung für Semantic Scholar/OpenAlex Queries
✓ System-Prompt bereinigt (nur "gut|schwach", kein "mittel")

5-LAYER HYBRID-RECHERCHE:
- Layer 0: Airtable - Kuratierte Facts (Semantic Search, Opus Research) ← NEU!
- Layer 1: Perplexity - Schnelle Web-Suche + aktuelle Quellen
- Layer 2: USDA FoodData - Nährwertdaten (Protein, Fett, Vitamine etc.)
- Layer 3: Semantic Scholar - 200M wissenschaftliche Papers (stable API)
- Layer 4: OpenAlex - 250M+ wissenschaftliche Works (free, no API key)

Aufruf:
    python run_factcheck_v3_improved.py --mode sample --limit 10
    python run_factcheck_v3_improved.py --mode priority --min-frequency 50 --parallel 10
    python run_factcheck_v3_improved.py --mode all --parallel 15 --resume
"""

import os
import sys
import time
import json
import argparse
import asyncio
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

try:
    import pandas as pd
    from anthropic import AsyncAnthropic
except ImportError:
    print("Fehler: pip install anthropic pandas")
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
  "konfidenz": "hoch|mittel|niedrig",
  "begründung": "Kurze Erklärung (max 300 Zeichen)",
  "korrektur": "Falls falsch/teilweise: korrekte Version, sonst leer",
  "quellen_qualität": "gut|schwach",
  "kontext_hinweis": "Wichtiger Kontext falls IRREFÜHREND, sonst leer",
  "nicht_pruefbar_grund": "Falls NICHT_PRÜFBAR: technisch|zu_vage|keine_quellen|subjektiv|historisch, sonst leer"
}}

KONFIDENZ-BEWERTUNG:
- "hoch": Mehrere verlässliche, wissenschaftliche Quellen bestätigen Claim eindeutig
- "mittel": Quellen vorhanden, aber begrenzt, widersprüchlich, oder nur semi-wissenschaftlich
- "niedrig": Wenige/schwache Quellen, oder Claim ist schwer zu verifizieren

QUELLEN-QUALITÄT:
- "gut": Peer-reviewed Papers, offizielle Behörden (USDA, BfR, EFSA), Meta-Analysen
- "schwach": Blog-Posts, Marketing-Seiten, populärwissenschaftliche Magazine, keine wissenschaftlichen Quellen

PRINZIPIEN:
- Sei streng bei Zahlen (±5% Toleranz)
- Bevorzuge wissenschaftliche Quellen (Google Scholar, PubMed) über Web-Quellen
- Bei widersprüchlichen Quellen: "TEILWEISE_RICHTIG" + Erklärung + konfidenz="mittel"
- Bei fehlenden Quellen: "NICHT_PRÜFBAR" + Grund angeben + konfidenz="niedrig"
- Bewerte quellen_qualität basierend auf den TATSÄCHLICHEN Quellen, nicht auf der API
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


TRANSLATE_SYSTEM = """Du bist Übersetzungsassistent für wissenschaftliche Queries.

Übersetze deutsche Claims in präzise englische Suchbegriffe für Google Scholar.
Extrahiere die wichtigsten Fachbegriffe und konzentriere dich auf messbare/überprüfbare Aspekte.

Beispiele:
- "Käse enthält 25g Protein pro 100g" → "cheese protein content per 100g"
- "Milch in Deutschland wird hauptsächlich von Kühen produziert" → "dairy milk production Germany cattle"
- "Bio-Milch hat höheren Omega-3-Gehalt" → "organic milk omega-3 fatty acids content"

Gib NUR die englische Query zurück, keine Erklärung."""


async def translate_to_english(claim: str, client: AsyncAnthropic) -> str:
    """Übersetzt deutschen Claim in englische Scholar-Query."""
    try:
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            temperature=0.0,
            system=TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": claim}]
        )

        query = resp.content[0].text.strip()
        return query if query else claim[:100]

    except Exception:
        # Fallback: Erste 100 Zeichen
        return claim[:100]


async def search_web_perplexity(claim: str, api_key: str) -> Tuple[Optional[str], List[str]]:
    """
    Sucht Web-Quellen via Perplexity API.

    Returns:
        (sources_text, urls_list)
    """
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

                    return result, citations[:5]
                else:
                    return None, []
    except Exception:
        return None, []


async def search_usda_fooddata(claim: str, api_key: str) -> Tuple[Optional[str], List[str]]:
    """
    Sucht Nährwertdaten via USDA FoodData Central API.

    Besonders nützlich für Claims über Protein, Fett, Kalorien, Vitamine etc.

    Returns:
        (sources_text, urls_list)
    """
    import aiohttp

    # Extrahiere Nahrungsmittel-Keywords aus Claim (sehr simpel)
    # Bessere Lösung: LLM-basierte Keyword-Extraktion
    keywords_map = {
        "käse": "cheese",
        "milch": "milk",
        "joghurt": "yogurt",
        "butter": "butter",
        "quark": "quark",
        "sahne": "cream",
        "protein": "protein",
        "fett": "fat",
        "kalorien": "calories"
    }

    query = claim.lower()
    search_term = None
    for german, english in keywords_map.items():
        if german in query:
            search_term = english
            break

    if not search_term:
        return None, []

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": search_term,
        "pageSize": 5,
        "api_key": api_key
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    foods = data.get("foods", [])

                    if not foods:
                        return None, []

                    results = ["USDA FOODDATA CENTRAL ERGEBNISSE:\n"]
                    urls = []

                    for i, food in enumerate(foods[:3]):
                        fdc_id = food.get("fdcId")
                        description = food.get("description", "Keine Beschreibung")

                        # URL zum Food Detail
                        food_url = f"https://fdc.nal.usda.gov/fdc-app.html#/food-details/{fdc_id}/nutrients"
                        urls.append(food_url)

                        results.append(f"[{i+1}] {description}")
                        results.append(f"    FDC ID: {fdc_id}")

                        # Nährwerte extrahieren
                        nutrients = food.get("foodNutrients", [])
                        for nutrient in nutrients[:5]:  # Top 5 Nährwerte
                            name = nutrient.get("nutrientName", "")
                            value = nutrient.get("value", 0)
                            unit = nutrient.get("unitName", "")

                            results.append(f"    - {name}: {value} {unit}")

                        results.append(f"    URL: {food_url}\n")

                    return "\n".join(results), urls
                else:
                    return None, []
    except Exception:
        return None, []


async def search_semantic_scholar(claim: str, client: AsyncAnthropic, max_results: int = 5) -> Tuple[Optional[str], List[str]]:
    """
    Sucht wissenschaftliche Papers via Semantic Scholar API mit Deutsch→Englisch-Übersetzung.

    Vorteile gegenüber Google Scholar:
    - Keine Selenium-Instabilität
    - Bessere API mit strukturierten Daten
    - Gleiche Datenbasis wie Consensus (200M Papers)
    - Rate Limit: 100 requests/5min (ausreichend)

    Returns:
        (sources_text, urls_list)
    """
    import aiohttp

    try:
        # 1. Übersetze Claim ins Englische
        english_query = await translate_to_english(claim, client)

        # 2. Semantic Scholar Paper Search API
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": english_query,
            "limit": max_results,
            "fields": "title,authors,year,abstract,url,citationCount,openAccessPdf"
        }

        headers = {
            "User-Agent": "KI-Produkt-Faktencheck/1.0 (mailto:research@example.com)"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    papers = data.get("data", [])

                    if not papers:
                        return None, []

                    results = [f"SEMANTIC SCHOLAR ERGEBNISSE (Query: '{english_query}'):\n"]
                    urls = []

                    for i, paper in enumerate(papers):
                        title = paper.get("title", "Kein Titel")
                        authors = paper.get("authors", [])
                        author_names = ", ".join([a.get("name", "") for a in authors[:3]])
                        year = paper.get("year", "o.J.")
                        abstract = paper.get("abstract", "")[:200]
                        citation_count = paper.get("citationCount", 0)

                        # URL: Bevorzuge Open Access PDF, sonst Semantic Scholar Page
                        paper_url = None
                        if paper.get("openAccessPdf"):
                            paper_url = paper["openAccessPdf"].get("url")
                        if not paper_url and paper.get("url"):
                            paper_url = paper["url"]

                        results.append(f"\n[{i+1}] {title}")
                        results.append(f"    Autoren: {author_names}")
                        results.append(f"    Jahr: {year} | Zitationen: {citation_count}")

                        if abstract:
                            results.append(f"    Abstract: {abstract}...")

                        if paper_url:
                            results.append(f"    URL: {paper_url}")
                            urls.append(paper_url)

                    return "\n".join(results), urls
                else:
                    return None, []

    except Exception:
        return None, []


async def search_openalex(claim: str, client: AsyncAnthropic, max_results: int = 5) -> Tuple[Optional[str], List[str]]:
    """
    Sucht wissenschaftliche Papers via OpenAlex API (250M+ works, free, no API key).

    OpenAlex ist eine offene Alternative zu Scopus/WoS mit >250M wissenschaftlichen Werken.
    Kein API Key erforderlich, keine strikten Rate Limits.
    """
    import aiohttp

    try:
        # 1. Übersetze Claim ins Englische
        english_query = await translate_to_english(claim, client)

        # 2. OpenAlex Works Search API
        url = "https://api.openalex.org/works"
        params = {
            "search": english_query,
            "per_page": max_results,
            "sort": "cited_by_count:desc",  # Sortiere nach Zitationen
            "filter": "type:article"  # Nur Artikel (keine Books, etc.)
        }

        headers = {
            "User-Agent": "KI-Produkt-Faktencheck/1.0 (mailto:research@example.com)"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    works = data.get("results", [])

                    if not works:
                        return None, []

                    results = [f"OPENALEX ERGEBNISSE (Query: '{english_query}'):\n"]
                    urls = []

                    for i, work in enumerate(works):
                        title = work.get("title", "Kein Titel")

                        # Autoren extrahieren
                        authorships = work.get("authorships", [])
                        author_names = ", ".join([
                            a.get("author", {}).get("display_name", "")
                            for a in authorships[:3]
                        ])

                        # Jahr
                        year = work.get("publication_year", "o.J.")

                        # Abstract (falls verfügbar)
                        abstract = work.get("abstract_inverted_index", {})
                        abstract_text = ""
                        if abstract:
                            # Rekonstruiere Abstract aus inverted index (nimm erste 200 chars)
                            words = []
                            for word, positions in list(abstract.items())[:50]:
                                words.append(word)
                            abstract_text = " ".join(words)[:200]

                        # Zitationen
                        cited_by_count = work.get("cited_by_count", 0)

                        # URL: Primäre OpenAlex-Seite
                        work_url = work.get("id", "")  # OpenAlex ID (URL)

                        # Optional: Open Access PDF URL
                        open_access = work.get("open_access", {})
                        oa_url = open_access.get("oa_url")

                        results.append(f"\n[{i+1}] {title}")
                        results.append(f"    Autoren: {author_names}")
                        results.append(f"    Jahr: {year} | Zitationen: {cited_by_count}")

                        if abstract_text:
                            results.append(f"    Abstract: {abstract_text}...")

                        # Bevorzuge OA PDF, sonst OpenAlex-Seite
                        if oa_url:
                            results.append(f"    URL: {oa_url}")
                            urls.append(oa_url)
                        elif work_url:
                            results.append(f"    URL: {work_url}")
                            urls.append(work_url)

                    return "\n".join(results), urls
                else:
                    return None, []

    except Exception:
        return None, []


async def hybrid_search(
    claim: str,
    perplexity_key: str,
    usda_key: str,
    client: AsyncAnthropic,
    voyage_key: Optional[str] = None
) -> Tuple[str, str, List[str]]:
    """
    5-Layer Hybrid-Suche:
    0. Airtable (Kuratierte verifizierte Facts, Semantic Search) ← Checked FIRST!
    1. Perplexity (schnell, aktuelle Web-Quellen)
    2. USDA FoodData (für Nährwert-Claims)
    3. Semantic Scholar (200M wissenschaftliche Papers, stable API)
    4. OpenAlex (250M+ works, free, keine API-Key erforderlich)

    Returns:
        (sources_text, source_type, urls_list)
        source_type: "airtable", "perplexity", "usda", "semantic_scholar", "openalex",
                     "perplexity+usda", "semantic_scholar+usda", "openalex+usda", "none"
    """

    # Layer 0: Versuche Airtable zuerst (cached, ultra-schnell, hochwertige Quellen)
    if voyage_key and os.environ.get("AIRTABLE_API_TOKEN") and os.environ.get("AIRTABLE_BASE_ID"):
        try:
            from airtable_search import search_airtable_facts

            airtable_result, airtable_urls = await search_airtable_facts(
                claim=claim,
                voyage_key=voyage_key
            )

            if airtable_result:
                print(f"      ✓ Airtable Match gefunden (Similarity > 0.85)", flush=True)
                return airtable_result, "airtable", airtable_urls

        except ImportError:
            pass  # airtable_search.py nicht vorhanden, skip Layer 0
        except Exception as e:
            print(f"      → Airtable failed: {e}", flush=True)

    # Layer 1: Versuche Perplexity zuerst (schneller)
    perplexity_result, perplexity_urls = await search_web_perplexity(claim, perplexity_key)

    # Layer 2: USDA FoodData für Nährwert-Claims (parallel zu Perplexity-Fallback)
    usda_result, usda_urls = await search_usda_fooddata(claim, usda_key)

    # Kombiniere Ergebnisse
    if perplexity_result and usda_result:
        combined = f"{perplexity_result}\n\n{'='*70}\n\n{usda_result}"
        return combined, "perplexity+usda", perplexity_urls + usda_urls

    if perplexity_result:
        return perplexity_result, "perplexity", perplexity_urls

    if usda_result:
        return usda_result, "usda", usda_urls

    # Layer 3: Fallback auf Semantic Scholar
    print(f"      → Perplexity+USDA failed, trying Semantic Scholar...", flush=True)
    scholar_result, scholar_urls = await search_semantic_scholar(claim, client, max_results=3)

    if scholar_result and usda_result:
        combined = f"{scholar_result}\n\n{'='*70}\n\n{usda_result}"
        return combined, "semantic_scholar+usda", scholar_urls + usda_urls

    if scholar_result:
        return scholar_result, "semantic_scholar", scholar_urls

    # Layer 4: Fallback auf OpenAlex (250M+ works, free)
    print(f"      → Semantic Scholar failed, trying OpenAlex...", flush=True)
    openalex_result, openalex_urls = await search_openalex(claim, client, max_results=3)

    if openalex_result and usda_result:
        combined = f"{openalex_result}\n\n{'='*70}\n\n{usda_result}"
        return combined, "openalex+usda", openalex_urls + usda_urls

    if openalex_result:
        return openalex_result, "openalex", openalex_urls

    # Layer 5: Keine Quellen gefunden
    return "Keine Quellen verfügbar (weder Perplexity noch USDA noch Semantic Scholar noch OpenAlex).", "none", []


async def factcheck_claim_async(
    client: AsyncAnthropic,
    claim_row: Dict,
    perplexity_key: str,
    usda_key: str,
    semaphore: asyncio.Semaphore,
    model_id: str = "claude-sonnet-4-20250514"
) -> Tuple[str, Dict, Dict]:
    """Fact-checkt einen einzelnen Claim mit verbesserter Hybrid-Recherche."""

    canonical_id = claim_row["canonical_id"]
    claim_text = claim_row["canonical_text"]

    async with semaphore:
        # 1. Hybrid-Recherche mit URL-Extraktion
        print(f"  [{canonical_id}] Recherchiere...", flush=True)
        voyage_key = os.environ.get("VOYAGE_API_KEY")  # Optional für Airtable Layer 0
        sources, source_type, urls = await hybrid_search(claim_text, perplexity_key, usda_key, client, voyage_key)

        # 2. Claude Fact-Check
        user_msg = FACTCHECK_USER_TEMPLATE.format(
            claim_text=claim_text,
            sources=sources,
            claim_type=claim_row.get("claim_types", "unbekannt"),
            deutschland_bezug=claim_row.get("deutschland_bezug_verteilung", "unklar"),
            frequency=claim_row["frequency"],
            models=claim_row["models_covering"]
        )

        stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "source_type": source_type,
            "urls": urls
        }

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

                    # KONSISTENZ-CHECK 1: source_type=none MUSS NICHT_PRÜFBAR sein
                    if source_type == "none" and result["bewertung"] != "NICHT_PRÜFBAR":
                        result["bewertung"] = "NICHT_PRÜFBAR"
                        result["nicht_pruefbar_grund"] = "technisch"
                        result["konfidenz"] = "niedrig"
                        result["begründung"] = "Keine Quellen verfügbar (technischer Fehler)"

                    # KONSISTENZ-CHECK 2: NICHT_PRÜFBAR braucht Grund
                    if result["bewertung"] == "NICHT_PRÜFBAR" and not result.get("nicht_pruefbar_grund"):
                        if source_type == "none":
                            result["nicht_pruefbar_grund"] = "technisch"
                        else:
                            result["nicht_pruefbar_grund"] = "keine_quellen"

                    # KONSISTENZ-CHECK 3: Konfidenz muss kategorisch sein
                    if result["konfidenz"] not in ["hoch", "mittel", "niedrig"]:
                        # Fallback: numerischen Wert zu kategorisch mappen
                        try:
                            numeric = float(result["konfidenz"])
                            if numeric >= 0.8:
                                result["konfidenz"] = "hoch"
                            elif numeric >= 0.5:
                                result["konfidenz"] = "mittel"
                            else:
                                result["konfidenz"] = "niedrig"
                        except:
                            result["konfidenz"] = "mittel"

                    # KONSISTENZ-CHECK 4: quellen_qualität nur gut|schwach
                    if result.get("quellen_qualität") not in ["gut", "schwach"]:
                        # "mittel" → "schwach" mappen
                        if result.get("quellen_qualität") == "mittel":
                            result["quellen_qualität"] = "schwach"
                        else:
                            result["quellen_qualität"] = "schwach"

                    print(f"  [{canonical_id}] ✓ {result['bewertung']} (Konfidenz: {result['konfidenz']}, Quellen: {source_type})", flush=True)
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
    usda_key: str,
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

            # URLs sammeln
            urls = call_stats.get("urls", [])
            urls_str = "|".join(urls) if urls else ""

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
                f"{result['konfidenz']};"
                f"{clean(result['begründung'])};"
                f"{clean(result.get('korrektur', ''))};"
                f"{result.get('quellen_qualität', '')};"
                f"{clean(result.get('kontext_hinweis', ''))};"
                f"{result.get('nicht_pruefbar_grund', '')};"
                f"{source_type};"
                f"{urls_str}\n"
            )

            n_ok += 1
            stats["bewertungen"][result["bewertung"]] += 1
            stats["konfidenz"][result["konfidenz"]] += 1

    return n_ok, n_fail


async def main_async(args):
    """Haupt-Async-Funktion."""

    # API Keys prüfen
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    usda_key = os.getenv("USDA_API_KEY")

    if not anthropic_key:
        print("Fehler: ANTHROPIC_API_KEY nicht gesetzt")
        sys.exit(1)

    if not perplexity_key:
        print("⚠️  Warnung: PERPLEXITY_API_KEY nicht gesetzt. Nur USDA+Scholar wird verwendet.")
        perplexity_key = "mock"

    if not usda_key:
        print("⚠️  Warnung: USDA_API_KEY nicht gesetzt. USDA FoodData wird übersprungen.")
        usda_key = "mock"

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
        header = "canonical_id;canonical_text;frequency;models_covering;topics;bewertung;konfidenz;begründung;korrektur;quellen_qualität;kontext_hinweis;nicht_pruefbar_grund;source_type;quellen_urls\n"
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(header)

    # Stats
    stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "bewertungen": defaultdict(int),
        "source_types": defaultdict(int),
        "konfidenz": defaultdict(int)
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

    print(f"\nKonfidenz-Verteilung:")
    for konf, count in sorted(stats["konfidenz"].items(), key=lambda x: -x[1]):
        pct = (count / total_ok * 100) if total_ok > 0 else 0
        print(f"  {konf:15s}: {count:4d} ({pct:.1f}%)")

    print(f"\nKosten:")
    print(f"  Input:  ${input_cost:.2f}")
    print(f"  Output: ${output_cost:.2f}")
    print(f"  Gesamt: ${input_cost + output_cost:.2f}")

    print(f"\n✓ Ergebnis gespeichert: {args.output}")


def main():
    ap = argparse.ArgumentParser(description="Automatisches Fact-Checking V3 IMPROVED")
    ap.add_argument("--mode", choices=["sample", "priority", "all"], required=True)
    ap.add_argument("--input", default="claims_canonical.csv")
    ap.add_argument("--output", default="claims_factchecked_v3_improved.csv")
    ap.add_argument("--model", default="claude-sonnet-4-20250514")
    ap.add_argument("--parallel", type=int, default=3, help="Parallele Checks")
    ap.add_argument("--limit", type=int, default=10, help="Limit für sample-Modus")
    ap.add_argument("--min-frequency", type=int, default=50, help="Min Frequency für priority-Modus")
    ap.add_argument("--resume", action="store_true")

    args = ap.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
