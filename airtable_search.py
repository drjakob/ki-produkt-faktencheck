#!/usr/bin/env python3
"""
Airtable Semantic Search - Layer 5 für Hybrid Search

Sucht verifizierte Fakten in Airtable via Semantic Similarity.

Workflow:
1. Generiere Voyage-Embedding für eingehenden Claim
2. Lade alle Fact-Embeddings aus Airtable
3. Berechne Cosine-Similarity
4. Returniere Top-Match falls Similarity > threshold (0.85)

Performance-Optimierung:
- Embeddings werden lokal gecacht (JSON)
- Cache wird alle 24h invalidiert
- Bei Airtable-Updates: Cache manuell löschen
"""

import os
import json
import hashlib
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import voyageai
from pyairtable import Api


# ============================
# CONFIG
# ============================

SIMILARITY_THRESHOLD = 0.80  # Konservativ aber realistisch (berücksichtigt document vs. query embeddings)
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_TTL_HOURS = 24

VOYAGE_MODEL = "voyage-3"


# ============================
# EMBEDDING CACHE
# ============================

def get_cache_path(cache_type: str) -> Path:
    """Gibt Pfad zur Cache-Datei zurück."""

    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"airtable_{cache_type}.json"


def is_cache_valid(cache_path: Path) -> bool:
    """Prüft ob Cache noch gültig ist (< 24h alt)."""

    if not cache_path.exists():
        return False

    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    age = datetime.now() - mtime

    return age < timedelta(hours=CACHE_TTL_HOURS)


def load_cached_embeddings() -> Optional[Dict]:
    """
    Lädt gecachte Fact-Embeddings.

    Returns:
        Dict mit Structure:
        {
            "fact_id": {
                "embedding": [0.1, 0.2, ...],
                "canonical_text": "...",
                "bewertung": "...",
                "begründung": "...",
                ...
            }
        }
    """

    cache_path = get_cache_path("embeddings")

    if not is_cache_valid(cache_path):
        return None

    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cached_embeddings(embeddings: Dict) -> None:
    """Speichert Fact-Embeddings im Cache."""

    cache_path = get_cache_path("embeddings")

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, ensure_ascii=False)


# ============================
# EMBEDDING GENERATION
# ============================

def generate_embedding(text: str, voyage_key: str) -> List[float]:
    """
    Generiert Voyage-Embedding für Text.

    Args:
        text: Input-Text
        voyage_key: Voyage API Key

    Returns:
        Embedding als List[float]
    """

    client = voyageai.Client(api_key=voyage_key)

    response = client.embed(
        texts=[text],
        model=VOYAGE_MODEL,
        input_type="document"  # Für Fact-Texte
    )

    return response.embeddings[0]


def generate_query_embedding(text: str, voyage_key: str) -> List[float]:
    """
    Generiert Voyage-Embedding für Query (Claim).

    Args:
        text: Claim-Text
        voyage_key: Voyage API Key

    Returns:
        Embedding als List[float]
    """

    client = voyageai.Client(api_key=voyage_key)

    response = client.embed(
        texts=[text],
        model=VOYAGE_MODEL,
        input_type="query"  # Für eingehende Claims
    )

    return response.embeddings[0]


# ============================
# AIRTABLE FACT LOADING
# ============================

def load_facts_from_airtable() -> Dict:
    """
    Lädt alle verifizierten Facts aus Airtable und generiert Embeddings.

    Returns:
        Dict mit fact_id → {embedding, fields}
    """

    print("  → Lade Facts aus Airtable...", flush=True)

    # Airtable API
    api_token = os.environ.get("AIRTABLE_API_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME", "verified_facts")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not all([api_token, base_id, voyage_key]):
        raise ValueError("Missing environment variables: AIRTABLE_API_TOKEN, AIRTABLE_BASE_ID, VOYAGE_API_KEY")

    api = Api(api_token)
    table = api.table(base_id, table_name)

    # Lade alle Records
    records = table.all()

    print(f"  → {len(records)} Facts geladen", flush=True)
    print(f"  → Generiere Embeddings...", flush=True)

    # Generiere Embeddings
    facts_with_embeddings = {}

    for i, record in enumerate(records):
        fields = record["fields"]
        fact_id = fields.get("fact_id", f"UNKNOWN_{i}")
        canonical_text = fields.get("canonical_text", "")

        if not canonical_text:
            continue

        # Generiere Embedding
        embedding = generate_embedding(canonical_text, voyage_key)

        facts_with_embeddings[fact_id] = {
            "embedding": embedding,
            "canonical_text": canonical_text,
            "bewertung": fields.get("bewertung", ""),
            "konfidenz": fields.get("konfidenz", ""),
            "begründung": fields.get("begründung", ""),
            "korrektur": fields.get("korrektur"),
            "quellen": fields.get("quellen", ""),
            "quellen_qualität": fields.get("quellen_qualität", ""),
            "numerischer_wert": fields.get("numerischer_wert"),
            "kontext_hinweis": fields.get("kontext_hinweis")
        }

        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(records)}]", flush=True)

    print(f"  → {len(facts_with_embeddings)} Facts mit Embeddings", flush=True)

    return facts_with_embeddings


# ============================
# SEMANTIC SEARCH
# ============================

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Berechnet Cosine-Similarity zwischen zwei Vektoren."""

    a = np.array(vec1)
    b = np.array(vec2)

    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


async def search_airtable_facts(
    claim: str,
    voyage_key: str,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    force_refresh: bool = False
) -> Tuple[Optional[str], List[str]]:
    """
    Sucht verifizierte Fakten in Airtable via Semantic Search.

    Args:
        claim: Eingehender Claim
        voyage_key: Voyage API Key
        similarity_threshold: Minimum Similarity (default: 0.85)
        force_refresh: Falls True, ignoriere Cache

    Returns:
        (sources_text, urls_list) oder (None, []) falls kein Match
    """

    # Lade Facts (mit Cache)
    facts = load_cached_embeddings()

    if facts is None or force_refresh:
        facts = load_facts_from_airtable()
        save_cached_embeddings(facts)

    if not facts:
        return None, []

    # Generiere Query-Embedding
    query_embedding = generate_query_embedding(claim, voyage_key)

    # Berechne Similarities
    similarities = []

    for fact_id, fact_data in facts.items():
        fact_embedding = fact_data["embedding"]
        similarity = cosine_similarity(query_embedding, fact_embedding)

        similarities.append({
            "fact_id": fact_id,
            "similarity": similarity,
            "data": fact_data
        })

    # Sortiere nach Similarity
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    # Prüfe Top-Match
    top_match = similarities[0]

    if top_match["similarity"] < similarity_threshold:
        return None, []

    # Formatiere Sources-Text
    fact = top_match["data"]

    sources_text = f"""AIRTABLE VERIFIED FACT (Similarity: {top_match['similarity']:.3f}):

CLAIM: {fact['canonical_text']}

BEWERTUNG: {fact['bewertung']}
KONFIDENZ: {fact['konfidenz']}

BEGRÜNDUNG:
{fact['begründung']}
"""

    if fact['korrektur']:
        sources_text += f"\nKORREKTUR:\n{fact['korrektur']}\n"

    if fact['numerischer_wert']:
        sources_text += f"\nNUMERISCHER WERT: {fact['numerischer_wert']}\n"

    if fact['kontext_hinweis']:
        sources_text += f"\nKONTEXT:\n{fact['kontext_hinweis']}\n"

    sources_text += f"\nQUELLEN-QUALITÄT: {fact['quellen_qualität']}\n"

    # URLs extrahieren
    quellen_urls = []
    if fact['quellen']:
        quellen_urls = [
            url.strip()
            for url in fact['quellen'].split('|')
            if url.strip()
        ]

    return sources_text, quellen_urls


# ============================
# CLI (für Testing)
# ============================

async def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="Test Airtable Semantic Search"
    )
    parser.add_argument(
        "--claim",
        required=True,
        help="Claim zum Testen"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh Embeddings-Cache"
    )

    args = parser.parse_args()

    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if not voyage_key:
        print("ERROR: VOYAGE_API_KEY not set")
        return

    print(f"\nSUCHE: {args.claim}\n", flush=True)

    sources_text, urls = await search_airtable_facts(
        claim=args.claim,
        voyage_key=voyage_key,
        force_refresh=args.refresh
    )

    if sources_text:
        print(sources_text, flush=True)
        print(f"\nURLs: {urls}\n", flush=True)
    else:
        print("Kein Match gefunden (Similarity < 0.85)\n", flush=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
