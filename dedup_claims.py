"""
KI-Produkt-Faktencheck · Semantische Claim-Deduplication

Verwendet Voyage AI Embeddings zur semantischen Cluster-Bildung.
Reduziert ~19k Claims auf ~800-1.500 kanonische Claims.

Voraussetzungen:
    pip install voyageai pandas scikit-learn scipy
    export VOYAGE_API_KEY=pa-...

Aufruf:
    python dedup_claims.py
    python dedup_claims.py --sample 1000
    python dedup_claims.py --reset
    python dedup_claims.py --threshold 0.85

Kosten (Voyage-3-large):
    ~19k Claims x ~25 Tokens = ~500k Tokens
    $0.18/M = ca. $0.10
"""

import os
import sys
import re
import time
import pickle
import argparse
import random
from pathlib import Path
from typing import List, Dict, Tuple
from collections import Counter, defaultdict

try:
    import pandas as pd
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    from scipy.cluster.hierarchy import linkage, fcluster
    import voyageai
except ImportError as e:
    print(f"Fehler: Abhängigkeit fehlt. pip install voyageai pandas scikit-learn scipy")
    print(f"Details: {e}")
    sys.exit(1)


def preprocess_claim(text: str) -> str:
    """Bereinigt Claim-Text vor Embedding."""
    if not text or pd.isna(text):
        return ""

    # Kleinbuchstaben
    text = text.lower()

    # Persona-Bezüge entfernen
    # "Für dich als [Rolle]", "In deinem Alter", "Liebe [Name]"
    text = re.sub(r"für dich als \w+", "", text)
    text = re.sub(r"in deinem alter", "", text)
    text = re.sub(r"liebe[rn]? \w+", "", text)
    text = re.sub(r"hallo \w+", "", text)
    text = re.sub(r"moin \w+", "", text)

    # Mehrfache Leerzeichen normalisieren
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_embeddings(
    texts: List[str],
    api_key: str,
    model: str = "voyage-3-large",
    batch_size: int = 128,
    cache_file: str = "embeddings_cache.pkl"
) -> np.ndarray:
    """Berechnet oder lädt Voyage AI Embeddings."""

    cache_path = Path(cache_file)
    cache = {}

    # Cache laden
    if cache_path.exists():
        print(f"Lade Embeddings-Cache von {cache_file}...")
        with open(cache_path, "rb") as f:
            cache = pickle.load(f)
        print(f"  → {len(cache)} Embeddings im Cache")

    # Texte identifizieren, die neu berechnet werden müssen
    texts_to_compute = []
    indices_to_compute = []

    for i, text in enumerate(texts):
        if text not in cache:
            texts_to_compute.append(text)
            indices_to_compute.append(i)

    print(f"\nEmbeddings:")
    print(f"  Total: {len(texts)}")
    print(f"  Cached: {len(texts) - len(texts_to_compute)}")
    print(f"  Neu zu berechnen: {len(texts_to_compute)}")

    # Neue Embeddings berechnen
    if texts_to_compute:
        client = voyageai.Client(api_key=api_key)
        new_embeddings = []
        total_tokens = 0

        print(f"\nBerechne {len(texts_to_compute)} neue Embeddings mit {model}...")
        start_time = time.time()

        for i in range(0, len(texts_to_compute), batch_size):
            batch = texts_to_compute[i:i + batch_size]

            try:
                result = client.embed(
                    batch,
                    model=model,
                    input_type="document"
                )

                new_embeddings.extend(result.embeddings)
                total_tokens += result.total_tokens

                # Progress
                if (i + batch_size) % 500 == 0 or i + batch_size >= len(texts_to_compute):
                    elapsed = time.time() - start_time
                    processed = min(i + batch_size, len(texts_to_compute))
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (len(texts_to_compute) - processed) / rate if rate > 0 else 0

                    print(f"  [{processed}/{len(texts_to_compute)}] "
                          f"{rate:.1f} claims/s | "
                          f"ETA: {eta/60:.1f}min | "
                          f"Tokens: {total_tokens:,}")

                time.sleep(0.1)  # Leichtes Throttling

            except Exception as e:
                print(f"  FEHLER bei Batch {i}: {e}")
                # Mit Nullen füllen als Fallback
                dim = 1024  # voyage-3-large Dimension
                new_embeddings.extend([np.zeros(dim) for _ in batch])

        elapsed = time.time() - start_time
        cost = (total_tokens / 1_000_000) * 0.18

        print(f"\n✓ Embedding abgeschlossen:")
        print(f"  Laufzeit: {elapsed/60:.1f} min")
        print(f"  Tokens: {total_tokens:,}")
        print(f"  Kosten: ${cost:.3f}")

        # Cache aktualisieren
        for text, embedding in zip(texts_to_compute, new_embeddings):
            cache[text] = embedding

        with open(cache_path, "wb") as f:
            pickle.dump(cache, f)
        print(f"  Cache gespeichert: {cache_file}")

    # Alle Embeddings zusammenstellen
    embeddings = np.array([cache[text] for text in texts])
    return embeddings


def cluster_embeddings(
    embeddings: np.ndarray,
    threshold: float = 0.87,
    method: str = "average"
) -> np.ndarray:
    """Clustert Embeddings via Agglomerative Clustering."""

    print(f"\nClustering mit Schwellwert {threshold}...")
    start_time = time.time()

    # Cosine Distance Matrix
    similarities = cosine_similarity(embeddings)
    distances = 1 - similarities

    # Fix: negative Werte auf 0 clipping (Rundungsfehler)
    distances = np.clip(distances, 0, None)

    # Hierarchical Clustering
    # linkage erwartet condensed distance matrix
    from scipy.spatial.distance import squareform
    condensed_dist = squareform(distances, checks=False)

    Z = linkage(condensed_dist, method=method)

    # Cluster extrahieren
    distance_threshold = 1 - threshold
    cluster_labels = fcluster(Z, distance_threshold, criterion='distance')

    n_clusters = len(np.unique(cluster_labels))
    elapsed = time.time() - start_time

    print(f"✓ Clustering abgeschlossen:")
    print(f"  Laufzeit: {elapsed:.1f}s")
    print(f"  Anzahl Cluster: {n_clusters:,}")
    print(f"  Cluster-Größen: min={np.min(np.bincount(cluster_labels))}, "
          f"max={np.max(np.bincount(cluster_labels))}, "
          f"median={np.median(np.bincount(cluster_labels)):.1f}")

    return cluster_labels


def find_medoid(cluster_indices: List[int], similarities: np.ndarray) -> int:
    """Findet Medoid (Claim mit geringster mittlerer Distanz zu anderen)."""
    if len(cluster_indices) == 1:
        return cluster_indices[0]

    # Durchschnittliche Ähnlichkeit jedes Claims zu allen anderen im Cluster
    avg_similarities = []
    for idx in cluster_indices:
        sim_to_others = [similarities[idx, other_idx] for other_idx in cluster_indices if other_idx != idx]
        avg_similarities.append(np.mean(sim_to_others) if sim_to_others else 0)

    # Medoid = höchste durchschnittliche Ähnlichkeit
    medoid_pos = np.argmax(avg_similarities)
    return cluster_indices[medoid_pos]


def aggregate_metadata(cluster_df: pd.DataFrame) -> Dict:
    """Aggregiert Metadaten eines Clusters."""

    # Models
    models = cluster_df["model_short"].value_counts().to_dict()
    models_str = ",".join([f"{m}({c})" for m, c in models.items()])

    # Topics (Top 3)
    topics = cluster_df["themen_tag"].value_counts().head(3).to_dict()
    topics_str = ",".join([f"{t}({c})" for t, c in topics.items()])

    # Claim Types (Top 3)
    types = cluster_df["claim_type"].value_counts().head(3).to_dict()
    types_str = ",".join([f"{t}({c})" for t, c in types.items()])

    # Deutschland-Bezug Verteilung
    de_bezug = cluster_df["deutschland_bezug"].value_counts()
    total = len(cluster_df)
    de_bezug_pct = {k: f"{(v/total)*100:.0f}%" for k, v in de_bezug.items()}
    de_bezug_str = ",".join([f"{k}:{v}" for k, v in de_bezug_pct.items()])

    return {
        "frequency": len(cluster_df),
        "models_covering": models_str,
        "topics": topics_str,
        "claim_types": types_str,
        "deutschland_bezug_verteilung": de_bezug_str
    }


def main():
    ap = argparse.ArgumentParser(description="Claim Deduplication mit Voyage AI")
    ap.add_argument("--input", default="claims_raw.csv", help="Input CSV")
    ap.add_argument("--sample", type=int, default=None, help="Nur erste N Claims (Test)")
    ap.add_argument("--threshold", type=float, default=0.87, help="Clustering-Schwellwert")
    ap.add_argument("--reset", action="store_true", help="Cache löschen")
    args = ap.parse_args()

    # API Key prüfen
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        print("Fehler: VOYAGE_API_KEY nicht gesetzt.")
        print("Setzen mit: export VOYAGE_API_KEY='pa-...'")
        sys.exit(1)

    # Cache löschen
    if args.reset and Path("embeddings_cache.pkl").exists():
        Path("embeddings_cache.pkl").unlink()
        print("✓ Cache gelöscht")

    # CSV laden
    print(f"Lade {args.input}...")
    df = pd.read_csv(args.input, sep=";")

    # Filtern
    df = df[df["claim_text"].notna()]
    df = df[df["claim_text"] != ""]
    df = df[df["claim_text"] != "NO_CLAIMS"]

    if args.sample:
        df = df.head(args.sample)
        print(f"  → Sample-Modus: {len(df)} Claims")
    else:
        print(f"  → {len(df)} Claims geladen")

    # Original-ID erstellen
    df["original_claim_id"] = df["response_id"] + ":" + df["claim_num"].astype(str)

    # Preprocessing
    print("\nPreprocessing...")
    df["claim_preprocessed"] = df["claim_text"].apply(preprocess_claim)

    # Embeddings berechnen
    embeddings = get_embeddings(
        df["claim_preprocessed"].tolist(),
        api_key=api_key,
        cache_file="embeddings_cache.pkl"
    )

    # Clustering
    cluster_labels = cluster_embeddings(embeddings, threshold=args.threshold)
    df["cluster_id"] = cluster_labels

    # Similarity Matrix für Medoid-Berechnung
    print("\nBerechne Similarity Matrix...")
    similarities = cosine_similarity(embeddings)

    # Kanonische Claims erstellen
    print("\nErstelle kanonische Claims...")
    canonical_data = []
    cluster_detail_data = []

    for cluster_id in sorted(df["cluster_id"].unique()):
        cluster_df = df[df["cluster_id"] == cluster_id]
        cluster_indices = cluster_df.index.tolist()

        # Medoid finden
        medoid_idx = find_medoid(cluster_indices, similarities)
        canonical_text = df.loc[medoid_idx, "claim_text"]

        # Metadaten aggregieren
        meta = aggregate_metadata(cluster_df)

        # Canonical ID
        canonical_id = f"CC{cluster_id:04d}"

        canonical_data.append({
            "canonical_id": canonical_id,
            "canonical_text": canonical_text,
            **meta
        })

        # Cluster-Details
        for _, row in cluster_df.iterrows():
            sim_to_canonical = similarities[medoid_idx, row.name]

            cluster_detail_data.append({
                "cluster_id": canonical_id,
                "canonical_text": canonical_text,
                "original_claim_id": row["original_claim_id"],
                "original_claim_text": row["claim_text"],
                "response_id": row["response_id"],
                "prompt_id": row["prompt_id"],
                "model_short": row["model_short"],
                "persona_label": row.get("persona_label", ""),
                "similarity_score": f"{sim_to_canonical:.3f}"
            })

    # DataFrames erstellen
    df_canonical = pd.DataFrame(canonical_data)
    df_clusters = pd.DataFrame(cluster_detail_data)

    # Sortieren nach Frequency
    df_canonical = df_canonical.sort_values("frequency", ascending=False).reset_index(drop=True)

    # Speichern
    output_canonical = "claims_canonical.csv"
    output_clusters = "claim_clusters.csv"

    df_canonical.to_csv(output_canonical, sep=";", index=False, encoding="utf-8")
    df_clusters.to_csv(output_clusters, sep=";", index=False, encoding="utf-8")

    print(f"\n✓ Gespeichert:")
    print(f"  {output_canonical} ({len(df_canonical)} kanonische Claims)")
    print(f"  {output_clusters} ({len(df_clusters)} Cluster-Zuordnungen)")

    # Statistiken
    print(f"\n{'='*70}")
    print("STATISTIKEN")
    print(f"{'='*70}")
    print(f"Original Claims: {len(df):,}")
    print(f"Kanonische Claims: {len(df_canonical):,}")
    print(f"Reduktion: {(1 - len(df_canonical)/len(df))*100:.1f}%")

    # Top-10 nach Frequency
    print(f"\n{'='*70}")
    print("TOP-10 HÄUFIGSTE CLAIMS")
    print(f"{'='*70}")
    for i, row in df_canonical.head(10).iterrows():
        print(f"\n#{i+1}: {row['canonical_text'][:100]}...")
        print(f"  Frequency: {row['frequency']}")
        print(f"  Models: {row['models_covering']}")
        print(f"  Topics: {row['topics']}")

    # 5 zufällige Cluster
    print(f"\n{'='*70}")
    print("5 ZUFÄLLIGE CLUSTER (Qualitätscheck)")
    print(f"{'='*70}")

    sample_clusters = random.sample(df_canonical["canonical_id"].tolist(), min(5, len(df_canonical)))

    for cid in sample_clusters:
        canonical_row = df_canonical[df_canonical["canonical_id"] == cid].iloc[0]
        members = df_clusters[df_clusters["cluster_id"] == cid]

        print(f"\n{cid}: {canonical_row['canonical_text']}")
        print(f"  Frequency: {canonical_row['frequency']} | Models: {canonical_row['models_covering']}")
        print(f"  Mitglieder:")

        for _, m in members.head(5).iterrows():
            print(f"    [{m['model_short']}] {m['original_claim_text'][:80]}... (sim: {m['similarity_score']})")

        if len(members) > 5:
            print(f"    ... und {len(members) - 5} weitere")

    # Log schreiben
    with open("dedup_log.txt", "w", encoding="utf-8") as f:
        f.write(f"Claim Deduplication Log\n")
        f.write(f"{'='*70}\n\n")
        f.write(f"Input: {args.input}\n")
        f.write(f"Threshold: {args.threshold}\n")
        f.write(f"Original Claims: {len(df):,}\n")
        f.write(f"Kanonische Claims: {len(df_canonical):,}\n")
        f.write(f"Reduktion: {(1 - len(df_canonical)/len(df))*100:.1f}%\n\n")
        f.write(f"Cluster-Größen:\n")
        f.write(f"  Min: {df_canonical['frequency'].min()}\n")
        f.write(f"  Max: {df_canonical['frequency'].max()}\n")
        f.write(f"  Median: {df_canonical['frequency'].median():.1f}\n")
        f.write(f"  Mean: {df_canonical['frequency'].mean():.1f}\n")

    print(f"\n✓ Log gespeichert: dedup_log.txt")

    # Sanity Check
    n_canonical = len(df_canonical)
    if n_canonical < 600 or n_canonical > 2000:
        print(f"\n⚠️  WARNUNG: Anzahl Cluster ({n_canonical}) außerhalb 600-2000.")
        print(f"   Erwäge Threshold-Anpassung (aktuell: {args.threshold})")


if __name__ == "__main__":
    main()
