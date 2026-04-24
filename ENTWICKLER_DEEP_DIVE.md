# Entwickler Deep Dive: Claim-Aufbereitung & Deduplication

**Für:** Till (Entwickler)
**Komplexität:** Advanced
**Fokus:** Technische Implementation Details der Pre-Processing Pipeline

---

## Übersicht: 3-Phasen-Pipeline

```
Phase 1: Extraction          Phase 2: Deduplication        Phase 3: Fact-Checking
═══════════════════          ══════════════════════        ══════════════════════
19.153 AI-Responses          19.153 Claims                 1.046 Claims
        ↓                            ↓                              ↓
Claude Sonnet 4.6            Voyage-3-large                Perplexity + Scholar
Async (30 parallel)          Embeddings (1024 dim)         + Claude
        ↓                            ↓                              ↓
19.153 structured            Cosine Similarity             167 verified
Claims (JSON)                + Clustering                  879 NICHT_PRÜFBAR
                                     ↓
                             1.046 kanonische Claims
                             (95% Reduktion!)
```

---

## Phase 1: Claim Extraction (run_extraction_v2.py)

### Problem

**Input:** KI-Antworten sind unstrukturiert, enthalten Mix aus:
- Harte Facts ("Produkt enthält 3,5% Fett")
- Soft Claims ("Produkt ist lecker")
- Persona-Bezüge ("Für dich als Erzieherin...")
- Grußformeln, Smalltalk

**Challenge:** Nur **harte, prüfbare Claims** extrahieren, strukturiert als JSON

### Architektur

#### 1. Async Parallelisierung

```python
async def extract_claims_async(
    client: AsyncAnthropic,
    row: Dict,
    semaphore: asyncio.Semaphore,  # Rate-Limiting
    model_id: str,
    stats: Dict
) -> Tuple[str, Optional[List[Dict]], Optional[str], Dict]:
    """
    Extrahiert Claims für eine Antwort (async, mit Retry-Logik).

    Args:
        client: Async Anthropic Client
        row: CSV-Zeile mit AI-Response
        semaphore: Begrenzt parallele Calls (z.B. 30)
        model_id: "claude-sonnet-4-20250514"
        stats: Token-Counter, Durations, Retries

    Returns:
        (response_id, claims_list, error, call_stats)
    """

    async with semaphore:  # Max 30 parallele Calls
        for attempt in range(4):  # Retry-Loop
            try:
                resp = await client.messages.create(
                    model=model_id,
                    max_tokens=4000,
                    system=EXTRACTION_SYSTEM,
                    messages=[{"role": "user", "content": user_msg}]
                )

                # Token-Tracking
                call_stats["input_tokens"] += resp.usage.input_tokens
                call_stats["output_tokens"] += resp.usage.output_tokens

                # Parse JSON (robust, mit Retry bei Fehler)
                claims = json.loads(resp.content[0].text.strip())

                # Validierung
                for c in claims:
                    validate_claim(c)  # Pflichtfelder, Fingerprint
                    c["muster_hints"] = detect_muster_flags(c["claim_text"])

                return response_id, claims, None, call_stats

            except json.JSONDecodeError:
                # Retry mit verschärftem Prompt
                user_msg += RETRY_PROMPT
                continue

            except Exception as e:
                if "rate" in str(e).lower():
                    wait = 2 ** attempt  # Exponential Backoff
                    await asyncio.sleep(wait)
                    continue
```

**Key-Features:**
- **Semaphore:** Limitiert parallele API-Calls (sonst Rate-Limit-Errors)
- **Retry-Logik:** 4 Versuche mit exponential backoff
- **Robustes Parsing:** Entfernt Markdown-Backticks, die Claude manchmal hinzufügt
- **Token-Tracking:** Für Kostenschätzung

#### 2. Structured JSON-Schema

```json
{
  "claim_text": "Produkt enthält ca. 120 mg Calcium pro 100 ml",
  "claim_fingerprint": "milch enthalt ca 120 mg calcium pro 100 ml",
  "original_wording": "Wusstest du, dass Produkt etwa 120 mg Calcium...",
  "kontext_modifikator": "ca.",
  "claim_type": "Zahl",
  "deutschland_bezug": "unklar",
  "themen_tag": "Naehrstoff"
}
```

**Felder-Erklärung:**
- `claim_text`: Normalisierte Aussage (ohne Persona-Bezüge, Floskeln)
- `claim_fingerprint`: Lowercase, normalisiert (ä→a), max 60 Zeichen (für Dedup)
- `kontext_modifikator`: Abschwächungen ("ca.", "laut WHO", "etwa")
- `claim_type`: Kategorisierung (Zahl | Definition | Studienlage | Ursache-Wirkung | Vergleich | qualitativ)

#### 3. Normalisierungs-Logik

```python
def normalize_fingerprint(text: str) -> str:
    """
    Normalisiert Text für Claim-Fingerprint.

    Beispiel:
        "Produkt enthält ca. 3,5% Fett (durchschnittlich)"
        → "milch enthalt ca 35 fett durchschnittlich"
    """
    # Umlaute ersetzen
    replacements = {
        "ä": "a", "ö": "o", "ü": "u", "ß": "ss",
        "Ä": "a", "Ö": "o", "Ü": "u"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # NFD-Normalisierung (diakritische Zeichen entfernen)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    # Kleinbuchstaben, nur alphanumerisch + Leerzeichen
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)

    # Mehrfache Leerzeichen reduzieren, max 60 Zeichen
    text = re.sub(r"\s+", " ", text).strip()[:60]

    return text
```

**Warum wichtig?**
- Ermöglicht String-basierte Pre-Deduplication
- Macht Embeddings robuster gegen Schreibvarianten

#### 4. Muster-Erkennung (Pattern Flags)

```python
def detect_muster_flags(claim_text: str) -> List[str]:
    """
    Erkennt bekannte problematische Muster im Claim.

    Flags:
        - vitamin_d_cluster: "Vitamin D in Produkt" (oft falsch)
        - us_referenz_verdacht: "Glas/Tasse mit >200ml" (US-Portionen)
        - superlativ_verdacht: "beste Quelle", "am meisten" (oft nicht prüfbar)
        - dge_empfehlung: "DGE empfiehlt" (spezifische Quelle)
    """
    flags = []
    text_lower = claim_text.lower()

    # Vitamin D Cluster (oft fehlerhafte Claims)
    if ("vitamin d" in text_lower or "vitamin-d" in text_lower) and "milch" in text_lower:
        flags.append("vitamin_d_cluster")

    # US-Referenz-Verdacht (Tasse/Glas mit ml > 200)
    if ("tasse" in text_lower or "glas" in text_lower):
        ml_matches = re.findall(r"(\d+)\s*ml", text_lower)
        if any(int(m) > 200 for m in ml_matches):
            flags.append("us_referenz_verdacht")

    # Superlativ-Verdacht (oft nicht objektiv prüfbar)
    if any(phrase in text_lower for phrase in [
        "am besten", "beste quelle", "führende", "am meisten"
    ]):
        flags.append("superlativ_verdacht")

    return flags
```

**Use Case:**
- Priorisierung im Fact-Checking (bekannte Problemfelder zuerst)
- Filtern von problematischen Claims

### Performance & Kosten

```
Input:  19.153 AI-Responses (Scope Full)
Output: 19.153 strukturierte Claims

Laufzeit:   ~45 Minuten (parallel=30)
API-Calls:  19.153 × Claude Sonnet 4.6
Tokens:     ~550k Input, ~450k Output
Kosten:     ~$8.40 ($3/M Input, $15/M Output)

Fehlerrate: <1% (JSON-Parse-Fehler nach Retry)
```

### Code-Referenzen

- `run_extraction_v2.py:192-303` - Haupt-Async-Funktion
- `run_extraction_v2.py:112-131` - Fingerprint-Normalisierung
- `run_extraction_v2.py:134-174` - Muster-Flags
- `run_extraction_v2.py:38-98` - Extraction-Prompt (System + User)

---

## Phase 2: Deduplication (dedup_claims.py)

### Problem

**Input:** 19.153 Claims mit vielen semantischen Duplikaten:
- "Produkt enthält 3,5% Fett"
- "Vollmilch hat einen Fettgehalt von 3,5%"
- "In Produkt sind etwa 3,5% Fett enthalten"

**Challenge:** Semantisch ähnliche Claims clustern → 1 kanonischer Claim pro Cluster

### Architektur

#### 1. Embedding-Generation

```python
def get_embeddings(
    texts: List[str],
    api_key: str,
    model: str = "voyage-3-large",  # 1024 dim
    batch_size: int = 128,
    cache_file: str = "embeddings_cache.pkl"
) -> np.ndarray:
    """
    Berechnet oder lädt Voyage AI Embeddings mit Caching.

    Voyage-3-large:
        - 1024 Dimensionen
        - State-of-the-art für semantische Ähnlichkeit
        - Besser als OpenAI text-embedding-3-large
        - $0.18 per 1M Tokens
    """

    # Cache laden (spart API-Calls bei Re-Runs)
    cache = {}
    if Path(cache_file).exists():
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)

    # Nur neue Texte berechnen
    texts_to_compute = [t for t in texts if t not in cache]

    if texts_to_compute:
        client = voyageai.Client(api_key=api_key)

        # Batch-Processing (max 128 pro Call)
        for i in range(0, len(texts_to_compute), batch_size):
            batch = texts_to_compute[i:i + batch_size]

            result = client.embed(
                batch,
                model=model,
                input_type="document"  # vs. "query"
            )

            # Cache aktualisieren
            for text, embedding in zip(batch, result.embeddings):
                cache[text] = embedding

        # Cache speichern
        with open(cache_file, "wb") as f:
            pickle.dump(cache, f)

    # Alle Embeddings zusammenstellen
    return np.array([cache[text] for text in texts])
```

**Key-Features:**
- **Persistent Caching:** Spart API-Calls bei Re-Runs ($0.10 → $0)
- **Batch-Processing:** 128 Claims pro API-Call
- **input_type="document":** Optimiert für lange Texte (vs. "query" für Suchen)

#### 2. Hierarchisches Clustering

```python
def cluster_embeddings(
    embeddings: np.ndarray,
    threshold: float = 0.87,  # Cosine Similarity
    method: str = "average"   # Linkage-Methode
) -> np.ndarray:
    """
    Clustert Embeddings via Agglomerative Hierarchical Clustering.

    Algorithm:
        1. Berechne Cosine Similarity Matrix (N×N)
        2. Konvertiere zu Distance Matrix (1 - similarity)
        3. Hierarchisches Clustering (average linkage)
        4. Cut Dendrogram bei distance_threshold = 1 - 0.87

    Returns:
        cluster_labels: Array[int] mit Cluster-ID pro Claim
    """

    # 1. Cosine Similarity Matrix
    similarities = cosine_similarity(embeddings)  # (N, N)
    distances = 1 - similarities

    # Fix: Negative Werte auf 0 clipping (Rundungsfehler)
    distances = np.clip(distances, 0, None)

    # 2. Condensed Distance Matrix (für scipy linkage)
    from scipy.spatial.distance import squareform
    condensed_dist = squareform(distances, checks=False)

    # 3. Hierarchisches Clustering
    Z = linkage(condensed_dist, method="average")

    # 4. Cluster extrahieren
    distance_threshold = 1 - threshold  # 0.87 → 0.13
    cluster_labels = fcluster(Z, distance_threshold, criterion='distance')

    return cluster_labels
```

**Warum Hierarchical Clustering?**
- **Keine feste Cluster-Anzahl:** Algorithmus bestimmt automatisch
- **Dendrogram-Struktur:** Ermöglicht Post-hoc Threshold-Anpassung
- **Average Linkage:** Balance zwischen Single (zu wenig Cluster) und Complete (zu viele)

**Threshold-Tuning:**
```
threshold=0.82 → ~1.600 Cluster (zu granular)
threshold=0.85 → ~1.200 Cluster (gut)
threshold=0.87 → ~1.046 Cluster (optimal!) ← verwendet
threshold=0.90 → ~800 Cluster (zu aggressiv)
```

#### 3. Medoid-Selection

```python
def find_medoid(cluster_indices: List[int], similarities: np.ndarray) -> int:
    """
    Findet Medoid (Claim mit geringster mittlerer Distanz zu allen anderen).

    Algorithmus:
        1. Für jeden Claim im Cluster:
           - Berechne durchschnittliche Similarity zu allen anderen
        2. Wähle Claim mit höchster Ø-Similarity

    Warum nicht einfach häufigster Claim?
        - Häufigkeit ≠ Qualität
        - Medoid ist repräsentativster Claim im Embedding-Space
    """
    if len(cluster_indices) == 1:
        return cluster_indices[0]

    # Durchschnittliche Similarity zu anderen im Cluster
    avg_similarities = []
    for idx in cluster_indices:
        sim_to_others = [
            similarities[idx, other_idx]
            for other_idx in cluster_indices
            if other_idx != idx
        ]
        avg_similarities.append(np.mean(sim_to_others))

    # Medoid = höchste Ø-Similarity
    medoid_pos = np.argmax(avg_similarities)
    return cluster_indices[medoid_pos]
```

**Beispiel:**

Cluster mit 3 Claims:
```
A: "Produkt enthält 3,5% Fett"
B: "Vollmilch hat Fettgehalt von 3,5 Prozent"
C: "Kuhmilch: ca. 3-4% Fettanteil"

Similarity Matrix:
    A    B    C
A  1.0  0.95 0.82
B  0.95 1.0  0.78
C  0.82 0.78 1.0

Ø-Similarity:
A: (0.95 + 0.82) / 2 = 0.885
B: (0.95 + 0.78) / 2 = 0.865
C: (0.82 + 0.78) / 2 = 0.800

→ Medoid: A (höchste Ø-Similarity)
```

#### 4. Metadaten-Aggregation

```python
def aggregate_metadata(cluster_df: pd.DataFrame) -> Dict:
    """
    Aggregiert Metadaten für kanonischen Claim.

    Output:
        {
            "frequency": 119,  # Anzahl Original-Claims im Cluster
            "models_covering": "Grok(46),Claude(35),Gemini(31),GPT(7)",
            "topics": "Naehrstoff(119)",
            "deutschland_bezug_verteilung": "ja:15%,nein:70%,unklar:15%"
        }
    """

    # Models (welche AI-Modelle diesen Claim produziert haben)
    models = cluster_df["model_short"].value_counts().to_dict()
    models_str = ",".join([f"{m}({c})" for m, c in models.items()])

    # Topics (Top 3 Themen-Tags)
    topics = cluster_df["themen_tag"].value_counts().head(3).to_dict()
    topics_str = ",".join([f"{t}({c})" for t, c in topics.items()])

    # Deutschland-Bezug (Prozent-Verteilung)
    de_bezug = cluster_df["deutschland_bezug"].value_counts()
    total = len(cluster_df)
    de_bezug_pct = {k: f"{(v/total)*100:.0f}%" for k, v in de_bezug.items()}

    return {
        "frequency": len(cluster_df),
        "models_covering": models_str,
        "topics": topics_str,
        "deutschland_bezug_verteilung": ",".join([f"{k}:{v}" for k, v in de_bezug_pct.items()])
    }
```

**Warum wichtig?**
- **Frequency:** Priorisierung im Fact-Checking (häufige Claims zuerst)
- **Models:** Diversität-Check (alle 4 Modelle?)
- **Topics:** Thematische Filterung möglich

### Output-Struktur

#### claims_canonical.csv

```csv
canonical_id;canonical_text;frequency;models_covering;topics
CC0558;Produktprotein hat biologische Wertigkeit von 88;119;Grok(46),Claude(35),Gemini(31),GPT(7);Naehrstoff(119)
CC0469;Casein versorgt Muskeln über längere Zeit;136;Gemini(51),Claude(41),GPT(30),Grok(14);Naehrstoff(86),Gesundheit(49)
```

#### claim_clusters.csv (Detail-Mapping)

```csv
cluster_id;canonical_text;original_claim_id;original_claim_text;similarity_score
CC0558;Produktprotein hat biologische Wertigkeit von 88;R00123:1;Produkt-Eiweiß hat BW von ca. 88;0.923
CC0558;Produktprotein hat biologische Wertigkeit von 88;R00456:2;Proteine in Produkt: biologische Wertigkeit ~88;0.891
```

### Performance & Kosten

```
Input:  19.153 Claims
Output: 1.046 kanonische Claims

Reduktion:     95% ✅
Laufzeit:      ~8 Minuten
Embedding API: ~500k Tokens × $0.18/M = $0.10
Clustering:    ~2 Minuten (CPU, lokal)

Cluster-Größen:
  Min:     1 (Singleton-Claims)
  Max:     192 (sehr häufiger Claim)
  Median:  8
  Mean:    18.3
```

### Qualitäts-Checks

```python
# 1. Cluster-Größen-Distribution
df_canonical['frequency'].describe()

# 2. Zufällige Cluster inspizieren
sample_clusters = random.sample(df_canonical['canonical_id'].tolist(), 5)
for cid in sample_clusters:
    members = df_clusters[df_clusters['cluster_id'] == cid]
    print(f"\n{cid}: {canonical_text}")
    for _, m in members.head(5).iterrows():
        print(f"  [{m['model_short']}] {m['original_claim_text'][:80]}... (sim: {m['similarity_score']})")

# 3. Low-Similarity-Warnung (potenzielle Fehler-Cluster)
low_sim = df_clusters[df_clusters['similarity_score'].astype(float) < 0.75]
if len(low_sim) > 0:
    print(f"⚠️  {len(low_sim)} Claims mit Similarity < 0.75")
```

### Code-Referenzen

- `dedup_claims.py:68-160` - Embedding-Generation mit Caching
- `dedup_claims.py:162-201` - Hierarchisches Clustering
- `dedup_claims.py:204-217` - Medoid-Selection
- `dedup_claims.py:220-247` - Metadaten-Aggregation

---

## Integration: Pipeline End-to-End

### Workflow

```bash
# 1. Claim Extraction (Phase 1)
python run_extraction_v2.py \
  --mode full \
  --parallel 30 \
  --input "Responses-Whitepaper-Prompt-Set-April2026 (4).csv" \
  --output claims_raw.csv

# Output: 19.153 Claims in claims_raw.csv

# 2. Deduplication (Phase 2)
python dedup_claims.py \
  --input claims_raw.csv \
  --threshold 0.87

# Output:
#   - claims_canonical.csv (1.046 kanonische Claims)
#   - claim_clusters.csv (19.153 → 1.046 Mappings)

# 3. Fact-Checking (Phase 3)
python run_factcheck_v2.py \
  --mode all \
  --input claims_canonical.csv \
  --parallel 15 \
  --output claims_factchecked.csv

# Output: 1.046 Claims mit Bewertung
```

### Resume-Capability

**Problem:** Lange Runs können abbrechen (API-Errors, Network)

**Lösung:** Resume-Flag prüft bereits verarbeitete IDs

```python
# Extraction Resume
if args.resume and Path(args.output).exists():
    existing = pd.read_csv(args.output, sep=";")
    processed_ids = set(existing["response_id"].unique())
    df = df[~df["response_id"].isin(processed_ids)]
    print(f"Resume: {len(processed_ids)} bereits verarbeitet")

# Deduplication Resume
# → Embeddings-Cache automatisch via pickle
if Path("embeddings_cache.pkl").exists():
    cache = pickle.load(...)  # Nur neue Texte berechnen

# Fact-Checking Resume
if args.resume and Path(args.output).exists():
    existing = pd.read_csv(args.output, sep=";")
    processed_ids = set(existing["canonical_id"].unique())
    df = df[~df["canonical_id"].isin(processed_ids)]
```

---

## Best Practices & Lessons Learned

### 1. Embedding-Caching ist kritisch

**Ohne Cache:**
- Jeder Re-Run: ~$0.10 API-Kosten
- 8 Minuten Laufzeit

**Mit Cache:**
- Re-Run: $0 (instant)
- Nur neue Claims werden berechnet

**Implementation:**
```python
cache_file = "embeddings_cache.pkl"  # Persistenter Cache
cache = pickle.load(cache_file) if exists(cache_file) else {}
```

### 2. Threshold-Tuning ist empirisch

**Vorgehen:**
1. Sample-Run mit 1.000 Claims
2. Threshold-Sweep: 0.80, 0.82, 0.85, 0.87, 0.90
3. Qualitäts-Check: 5 zufällige Cluster inspizieren
4. Optimalen Wert wählen

**Ergebnis:**
- 0.87 = Sweet-Spot (1.046 Cluster, hohe Qualität)

### 3. Medoid > Frequency für Canonical

**Warum nicht einfach häufigster Claim als Canonical?**

Beispiel-Cluster:
```
Claim A (100×): "Produkt: ca. 3-4% Fett"  (vage)
Claim B (19×):  "Produkt enthält 3,5% Fett"  (präzise)

Medoid-Logik wählt B (repräsentativer im Embedding-Space)
Frequency-Logik würde A wählen (häufiger, aber schlechter)
```

### 4. Async ist 10× schneller als Sequential

**Sequential (19k Claims):**
- 1 Call = 2s → 19.153 × 2s = ~10 Stunden ❌

**Async (parallel=30):**
- 30 Calls parallel = ~45 Minuten ✅

**Code:**
```python
semaphore = asyncio.Semaphore(30)  # Max 30 parallel
tasks = [extract_claims_async(..., semaphore) for row in rows]
results = await asyncio.gather(*tasks)
```

---

## Debugging & Troubleshooting

### Problem: Embeddings dauern zu lange

**Symptom:** 19k Claims × 1s = 5 Stunden

**Ursache:** Einzelne API-Calls statt Batching

**Fix:**
```python
batch_size = 128  # Max 128 pro Call
for i in range(0, len(texts), batch_size):
    batch = texts[i:i + batch_size]
    result = client.embed(batch, model="voyage-3-large")
```

### Problem: Clustering erzeugt zu viele Singleton-Cluster

**Symptom:** 15.000 Cluster bei 19.000 Claims

**Ursache:** Threshold zu hoch (0.95)

**Fix:**
```python
threshold = 0.87  # Senken auf 0.85-0.87
```

### Problem: JSON-Parse-Fehler bei Extraction

**Symptom:** Claude gibt Markdown-Blöcke zurück statt pures JSON

```
```json
[{"claim_text": "..."}]
```
```

**Fix:**
```python
text = resp.content[0].text.strip()

# Entferne Markdown-Backticks
if text.startswith("```"):
    lines = text.split("\n")
    text = "\n".join(lines[1:-1])  # Erste/letzte Zeile entfernen
    if text.startswith("json"):
        text = text[4:].strip()

claims = json.loads(text)
```

### Problem: Rate-Limit-Errors

**Symptom:** 429 Too Many Requests

**Fix:**
```python
# 1. Semaphore reduzieren
semaphore = asyncio.Semaphore(15)  # statt 30

# 2. Exponential Backoff
for attempt in range(4):
    try:
        result = await api_call()
        break
    except RateLimitError:
        wait = 2 ** attempt  # 1s, 2s, 4s, 8s
        await asyncio.sleep(wait)
```

---

## Performance-Optimierung: Vor/Nach

### Extraction V1 (Sequential)

```python
for row in df.iterrows():
    claims = extract_claims(row)  # Sync
    save(claims)

# 19.153 Claims = ~10 Stunden ❌
```

### Extraction V2 (Async + Batching)

```python
async def main():
    tasks = [extract_claims_async(row, semaphore) for row in rows]
    results = await asyncio.gather(*tasks)

    # Batch-Write (nicht 1 pro Claim)
    for batch in chunks(results, 100):
        append_to_csv(batch)

# 19.153 Claims = ~45 Minuten ✅ (13× schneller)
```

### Deduplication V1 (No Cache)

```python
embeddings = client.embed(texts)  # Immer neu berechnen
cluster_labels = cluster(embeddings)

# Jeder Run: $0.10 + 8 Min ❌
```

### Deduplication V2 (Persistent Cache)

```python
cache = load_cache()
new_texts = [t for t in texts if t not in cache]
new_embeddings = client.embed(new_texts) if new_texts else []
cache.update(zip(new_texts, new_embeddings))
save_cache(cache)

# Erster Run: $0.10 + 8 Min
# Re-Run: $0 + 5 Sek ✅ (100× schneller)
```

---

## Testing & Validation

### Unit-Tests (Empfohlen)

```python
# test_extraction.py
def test_normalize_fingerprint():
    assert normalize_fingerprint("Produkt enthält 3,5% Fett") == \
           "milch enthalt 35 fett"

    assert normalize_fingerprint("Äpfel über Österreich") == \
           "apfel uber osterreich"

def test_detect_muster_flags():
    claim = "Vitamin D in Produkt: 0,1 µg pro 100ml"
    flags = detect_muster_flags(claim)
    assert "vitamin_d_cluster" in flags

# test_dedup.py
def test_find_medoid():
    similarities = np.array([
        [1.0, 0.9, 0.8],
        [0.9, 1.0, 0.7],
        [0.8, 0.7, 1.0]
    ])
    medoid = find_medoid([0, 1, 2], similarities)
    assert medoid == 0  # Höchste Ø-Similarity
```

### Integration-Tests

```bash
# Test mit Sample (100 Claims)
python run_extraction_v2.py --mode pilot --limit 100
python dedup_claims.py --sample 100
python run_factcheck_v2.py --mode sample --limit 10

# Erwartete Outputs
test -f claims_raw.csv && echo "✓ Extraction OK"
test -f claims_canonical.csv && echo "✓ Dedup OK"
test -f claims_factchecked.csv && echo "✓ Fact-Check OK"
```

---

## Fragen für Code-Review

### Architecture

1. **Async-Pattern:** Ist die Semaphore-Logik klar?
2. **Error-Handling:** Sind die Retry-Mechanismen ausreichend?
3. **Caching:** Sollten wir Embeddings in DB statt Pickle speichern?

### Data Quality

4. **Normalisierung:** Fehlen wichtige Preprocessing-Schritte?
5. **Clustering:** Ist threshold=0.87 reproduzierbar optimal?
6. **Medoid-Selection:** Gibt es bessere Algorithmen?

### Performance

7. **Parallelität:** Können wir parallel>30 ohne Rate-Limits?
8. **Batching:** Sollten wir größere Batches (>128) für Embeddings?
9. **Resume:** Brauchen wir robusteres Resume (z.B. Checkpoints alle 100 Claims)?

### Production-Readiness

10. **Monitoring:** Wo würdest du Logging/Metrics einbauen?
11. **Error-Recovery:** Was passiert bei hartem Crash (Stromaustausfall)?
12. **Skalierung:** Wie würde das mit 100k Claims skalieren?

---

## Nächste Schritte für Till

### Sofort

1. ✅ Code lesen: `run_extraction_v2.py` + `dedup_claims.py`
2. ✅ Test-Run durchführen (siehe QUICK_START_TILL.md)
3. ✅ Ergebnisse inspizieren:
   ```bash
   # Top-10 Cluster
   head -11 claims_canonical.csv

   # Zufälliger Cluster-Detail
   grep "CC0558" claim_clusters.csv | head -10
   ```

### Diese Woche

4. **Code-Review:** Feedback zu Architektur, Performance, Code-Qualität
5. **Verbesserungsvorschläge:**
   - Retry-Mechanismus optimieren?
   - Alternative Embedding-Modelle testen?
   - Threshold-Tuning automatisieren?

### Nächste 2 Wochen

6. **Unit-Tests schreiben** (test_extraction.py, test_dedup.py)
7. **Produktionisierung:**
   - Structured Logging (nicht print())
   - Monitoring-Dashboard
   - DB statt CSV für große Datensätze?

---

**Kontakt bei Fragen:** drjakobvicari@gmail.com

**Relevante Dateien:**
- `run_extraction_v2.py` - Claim Extraction
- `dedup_claims.py` - Semantic Deduplication
- `ARCHITEKTUR.md` - Gesamt-Architektur (inkl. Phase 3)
- `claims_canonical.csv` - Output (1.046 Claims)
- `claim_clusters.csv` - Cluster-Mappings (19k → 1k)
