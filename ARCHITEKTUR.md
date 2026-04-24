# Technische Architektur: KI-Produkt-Faktencheck

**Für:** Till (Code-Review & Weiterentwicklung)
**Von:** Jakob
**Datum:** 24. April 2026

---

## System-Überblick

```
┌──────────────────────────────────────────────────────────────────┐
│                    KI-Produkt-Faktencheck Pipeline                  │
└──────────────────────────────────────────────────────────────────┘

Phase 1: Claim Extraction
──────────────────────────
Input:   Responses-Whitepaper-Prompt-Set-April2026.csv (4 AI-Modelle × ~500 Prompts)
Tool:    run_extraction_v2.py
API:     Claude Sonnet 4.6 (Anthropic)
Output:  claims_raw.csv (19.153 Claims)

Phase 2: Deduplication
──────────────────────────
Input:   claims_raw.csv
Tool:    dedup_claims.py
API:     Voyage-3-large Embeddings (1024 dim)
Output:  claims_canonical.csv (1.046 Claims)

Phase 3: Fact-Checking
──────────────────────────
Input:   claims_canonical.csv
Tool:    run_factcheck_v2.py (Hybrid Search)
         run_factcheck_v3.py (4-Layer Fallback)
APIs:    • Perplexity sonar-pro
         • Google Scholar (scholarly + Selenium)
         • PubMed NIH E-Utilities
         • USDA FoodData Central
         • Claude Sonnet 4.6 (Bewertung)
Output:  claims_factchecked_*.csv
```

---

## Phase 1: Claim Extraction

### Script: `run_extraction_v2.py`

**Zweck:** Extrahiert strukturierte Claims aus unstrukturierten AI-Antworten

### Tech-Stack

```python
- asyncio: Parallele Verarbeitung mit Semaphore (Rate-Limiting)
- anthropic: Claude Sonnet 4.6 API
- pandas: CSV-Handling
- aiohttp: Async HTTP-Requests
```

### Key-Function: `extract_claims_from_response()`

```python
async def extract_claims_from_response(
    response_text: str,
    prompt_id: str,
    model_name: str,
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore
) -> List[Dict]:
    """
    Extrahiert Claims aus AI-Response via Claude Sonnet 4.6.

    Input:  Unstrukturierter Text (AI-Antwort auf Produkt-Frage)
    Output: Strukturierte Liste von Claims

    Beispiel Output:
    [
        {
            "claim_text": "Produkt enthält Calcium",
            "topic": "Naehrstoff",
            "claim_type": "qualitativ",
            "deutschland_bezug": "nein"
        }
    ]
    """
```

**Extraction-Prompt (an Claude Sonnet 4.6):**

```
Extrahiere alle faktischen Behauptungen über Produkt aus dem Text.

Kategorisiere jeden Claim:
- topic: Naehrstoff | Gesundheit | Herkunft | Wirtschaft | Verarbeitung | ...
- claim_type: Zahl | qualitativ | Vergleich | Ursache-Wirkung | Studienlage
- deutschland_bezug: ja | nein | unklar

Format: JSON-Array
```

### Parallelisierung

```python
# Semaphore für Rate-Limiting (max 30 parallele Requests)
semaphore = asyncio.Semaphore(parallel)

# Batch-Processing
for batch in batches(rows, size=parallel):
    tasks = [extract_claims_from_response(...) for row in batch]
    results = await asyncio.gather(*tasks)
```

**Performance:**
- ~75 Responses/min bei parallel=30
- ~250.000 Tokens/Lauf (Extraction für 500 Responses)

---

## Phase 2: Deduplication

### Script: `dedup_claims.py`

**Zweck:** Clustert semantisch ähnliche Claims via Embeddings

### Tech-Stack

```python
- voyageai: Voyage-3-large Embeddings (1024 Dimensionen)
- scikit-learn: Cosine Distance
- pandas: DataFrame-Operations
```

### Key-Function: `deduplicate_claims()`

```python
def deduplicate_claims(
    claims_df: pd.DataFrame,
    threshold: float = 0.82
) -> pd.DataFrame:
    """
    Semantic Deduplication via Voyage Embeddings.

    Algorithmus:
    1. Erzeuge Embeddings für alle Claims
    2. Berechne Cosine-Distanz-Matrix
    3. Clustere Claims mit Distance < threshold
    4. Wähle repräsentativen Claim pro Cluster (höchste Frequency)

    threshold: 0.82 = optimal (empirisch getestet)
               Höher: Mehr Duplikate bleiben
               Niedriger: Zu viel Merging
    """
```

### Embedding-Erzeugung

```python
import voyageai

client = voyageai.Client(api_key=VOYAGE_API_KEY)

# Batch-Embedding (max 128 Claims/Request)
embeddings = client.embed(
    texts=claim_texts,
    model="voyage-3-large",  # 1024 Dimensionen
    input_type="document"
)
```

### Clustering-Logik

```python
from sklearn.metrics.pairwise import cosine_similarity

# Similarity-Matrix (1046 x 1046)
similarity_matrix = cosine_similarity(embeddings)

# Finde Cluster (Claims mit Similarity > threshold)
clusters = []
for i, claim in enumerate(claims):
    similar_claims = [j for j in range(len(claims))
                      if similarity_matrix[i][j] > threshold and j != i]
    if similar_claims:
        clusters.append([i] + similar_claims)

# Merge Overlapping-Cluster
merged_clusters = merge_overlapping(clusters)

# Wähle Canonical Claim (höchste Frequency)
for cluster in merged_clusters:
    canonical_claim = max(cluster, key=lambda x: claims[x].frequency)
    # Merge frequencies
    canonical_claim.frequency = sum(c.frequency for c in cluster)
```

**Ergebnis:**
- Input: 19.153 Claims
- Output: 1.046 Canonical Claims (95% Reduktion!)
- Durchschnittlich 18 Varianten pro Canonical Claim

---

## Phase 3: Fact-Checking

### Version 2 (Hybrid Search): `run_factcheck_v2.py`

**Architektur:** 2-Layer Fallback (Perplexity → Google Scholar)

```python
async def hybrid_search(claim: str, perplexity_key: str) -> Tuple[str, str]:
    """
    Hybrid-Suche: Perplexity ODER Google Scholar.

    Returns:
        (sources_text, source_type)
    """

    # Layer 1: Perplexity (schnell, aktuelle Web-Quellen)
    result = await search_web_perplexity(claim, perplexity_key)
    if result:
        return result, "perplexity"

    # Layer 2: Google Scholar (wissenschaftliche Papers)
    print(f"      → Perplexity failed, trying Google Scholar...")
    result = await search_google_scholar(claim, max_results=3)
    if result:
        return result, "scholar"

    # Keine Quellen gefunden
    return "Keine Quellen verfügbar.", "none"
```

### Version 3 (4-Layer Fallback): `run_factcheck_v3.py`

**Architektur:** Topic-basierte Layer-Auswahl

```python
async def multi_layer_search(
    claim: str,
    claim_topics: List[str],
    perplexity_key: str,
    usda_key: Optional[str] = None
) -> Tuple[str, str]:
    """
    Multi-Layer-Fallback mit Topic-Routing.
    """

    # Layer 1: Perplexity (immer zuerst)
    result = await search_web_perplexity(claim, perplexity_key)
    if result:
        return result, "perplexity"

    # Layer 2: Google Scholar (allgemein wissenschaftlich)
    result = await search_google_scholar(claim)
    if result:
        return result, "scholar"

    # Layer 3: PubMed (für Gesundheit/Nährwert-Claims)
    if any(topic in claim_topics for topic in ["Gesundheit", "Naehrstoff"]):
        result = await search_pubmed(claim)
        if result:
            return result, "pubmed"

    # Layer 4: USDA FoodData (für exakte Nährwert-Claims mit µg/mg)
    if "Naehrstoff" in claim_topics and any(unit in claim for unit in ["µg", "mg", "g/"]):
        if usda_key:
            result = await search_usda_fooddata(claim, usda_key)
            if result:
                return result, "usda"

    return "Keine Quellen verfügbar (alle Suchquellen erschöpft).", "none"
```

---

## Such-Layer im Detail

### Layer 1: Perplexity API

```python
async def search_web_perplexity(
    claim: str,
    api_key: str,
    model: str = "sonar-pro"
) -> Optional[str]:
    """
    Sucht Web-Quellen via Perplexity sonar-pro.

    Vorteile:
    - Schnell (~2s/Query)
    - Aktuelle Web-Quellen (2024/2025)
    - Zitiert Quellen direkt

    Nachteile:
    - API-Instabilität (Rate-Limits?)
    - Schwach bei wissenschaftlichen Claims
    """

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "sonar-pro",
        "messages": [{
            "role": "user",
            "content": f"Finde Quellen für: {claim}"
        }],
        "temperature": 0.0,  # Deterministisch
        "max_tokens": 1000
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                print(f"Perplexity error: {resp.status}")
                return None
```

### Layer 2: Google Scholar (Scholarly Library)

```python
async def search_google_scholar(
    claim: str,
    max_results: int = 3
) -> Optional[str]:
    """
    Sucht wissenschaftliche Papers via scholarly + Selenium.

    Vorteile:
    - Hochwertige wissenschaftliche Quellen
    - Kostenlos (keine API-Key nötig)

    Nachteile:
    - Langsam (~10s/Query wegen Selenium)
    - Webdriver-Errors (Connection reset)
    - Google blockiert manchmal bei zu vielen Requests
    """

    from scholarly import scholarly

    try:
        search_results = scholarly.search_pubs(claim)
        papers = []

        for i, paper in enumerate(search_results):
            if i >= max_results:
                break

            title = paper.get('bib', {}).get('title', 'Unbekannt')
            year = paper.get('bib', {}).get('pub_year', 'o.J.')
            author = paper.get('bib', {}).get('author', ['Unbekannt'])[0]

            papers.append(f"[{i+1}] {author} ({year}): {title}")

        if papers:
            return "GOOGLE SCHOLAR:\n\n" + "\n".join(papers)
        else:
            return None

    except Exception as e:
        print(f"Scholar error: {e}")
        return None
```

**Selenium-Problem:**

```
Could not close webdriver cleanly: [Errno 54] Connection reset by peer
```

→ Google Scholar nutzt Selenium im Hintergrund, was zu Verbindungsabbrüchen führen kann

### Layer 3: PubMed NIH E-Utilities

```python
async def search_pubmed(claim: str, max_results: int = 5) -> Optional[str]:
    """
    Sucht medizinische/Ernährungs-Studien via PubMed API.

    Vorteile:
    - Kostenlos, stabil
    - Hochwertige medizinische Quellen (NIH)
    - XML-API (strukturiert)

    Nachteile:
    - Nur für medizinische/Nährwert-Claims relevant
    - Englischsprachig
    """

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    # 1. Suche nach Paper-IDs (esearch)
    search_url = f"{base_url}esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": claim[:200],
        "retmax": max_results,
        "retmode": "json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(search_url, params=params) as resp:
            data = await resp.json()
            ids = data.get("esearchresult", {}).get("idlist", [])

        if not ids:
            return None

        # 2. Hole Paper-Details (efetch)
        fetch_url = f"{base_url}efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml"
        }

        async with session.get(fetch_url, params=params) as resp:
            xml_text = await resp.text()

    # 3. Parse XML (ElementTree)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)

    results = []
    for article in root.findall(".//PubmedArticle"):
        title = article.find(".//ArticleTitle").text
        year = article.find(".//PubDate/Year").text
        abstract = article.find(".//AbstractText").text[:200]

        results.append(f"{title} ({year})\n{abstract}...")

    return "PUBMED:\n\n" + "\n".join(results) if results else None
```

### Layer 4: USDA FoodData Central

```python
async def search_usda_fooddata(
    claim: str,
    api_key: str
) -> Optional[str]:
    """
    Sucht exakte Nährwertangaben via USDA API.

    Vorteile:
    - Offizielle US-Datenbank (USDA)
    - Exakte Nährwerte (µg-Bereich)
    - JSON-API

    Nachteile:
    - Nur für Nährwert-Claims mit konkreten Zahlen
    - US-zentriert (nicht alle deutschen Produkte)
    - Keyword-Matching notwendig
    """

    # Extrahiere Lebensmittel-Name aus Claim (simpel)
    food_keywords = ["Produkt", "Käse", "Joghurt", "Quark", "Grünkohl"]
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

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            foods = data.get("foods", [])

    if not foods:
        return None

    # Formatiere Ergebnisse
    results = []
    for food in foods[:3]:
        desc = food.get("description", "Unbekannt")
        nutrients = food.get("foodNutrients", [])

        nutrient_strs = []
        for n in nutrients[:5]:
            name = n.get("nutrientName")
            value = n.get("value")
            unit = n.get("unitName")
            nutrient_strs.append(f"{name}: {value}{unit}")

        results.append(f"{desc}\n  {', '.join(nutrient_strs)}")

    return "USDA FOODDATA:\n\n" + "\n".join(results)
```

---

## Bewertungs-Engine (Claude Sonnet 4.6)

```python
async def fact_check_claim(
    claim: str,
    sources: str,
    client: anthropic.AsyncAnthropic
) -> Dict:
    """
    Bewertet Claim basierend auf Quellen via Claude Sonnet 4.6.

    Output-Schema:
    {
        "bewertung": "RICHTIG" | "WEITGEHEND_RICHTIG" | "TEILWEISE_RICHTIG" |
                     "IRREFÜHREND" | "FALSCH" | "NICHT_PRÜFBAR",
        "konfidenz": 0.0-1.0,
        "begründung": "...",
        "korrektur": "..." (nur bei FALSCH),
        "quellen_qualität": "gut" | "mittel" | "schlecht",
        "kontext_hinweis": "..." (optional),
        "nicht_pruefbar_grund": "keine_quellen" | "zu_vage" | "subjektiv" | ... (nur bei NICHT_PRÜFBAR)
    }
    """

    prompt = f"""
Bewerte folgenden Claim über Produkt anhand der Quellen:

CLAIM:
{claim}

QUELLEN:
{sources}

Bewerte nach:
1. RICHTIG - Claim vollständig bestätigt
2. WEITGEHEND_RICHTIG - Kern richtig, kleine Abweichungen
3. TEILWEISE_RICHTIG - Teils richtig, teils falsch
4. IRREFÜHREND - Technisch wahr, aber missverständlich
5. FALSCH - Claim widerlegt
6. NICHT_PRÜFBAR - Keine Quellen oder zu vage

Gib zurück als JSON mit:
- bewertung
- konfidenz (0.0-1.0)
- begründung
- korrektur (falls FALSCH)
- quellen_qualität (gut/mittel/schlecht)
- nicht_pruefbar_grund (falls NICHT_PRÜFBAR)
"""

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0.0,  # Deterministisch
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse JSON aus Response
    import json
    result = json.loads(response.content[0].text)

    return result
```

**Bewertungs-Beispiele:**

```json
{
    "claim": "Produktprotein hat biologische Wertigkeit von 88",
    "bewertung": "RICHTIG",
    "konfidenz": 0.95,
    "begründung": "Mehrere wissenschaftliche Quellen bestätigen Werte zwischen 82-91, 88 liegt im bestätigten Bereich.",
    "quellen_qualität": "gut"
}

{
    "claim": "20-30% Soja im Produktkuh-Futter",
    "bewertung": "FALSCH",
    "konfidenz": 0.85,
    "begründung": "Quellen zeigen nur 9,9-19,8% des Sojaschrotaufkommens geht an Produktvieh, nicht 20-30% des Gesamtfutters.",
    "korrektur": "Etwa 9,9-19,8% des in Deutschland verfütterten Sojaschrotaufkommens geht an Produktvieh.",
    "quellen_qualität": "gut"
}

{
    "claim": "Casein versorgt Muskeln über längere Zeit",
    "bewertung": "NICHT_PRÜFBAR",
    "konfidenz": 0.80,
    "begründung": "Keine wissenschaftlichen Quellen gefunden.",
    "nicht_pruefbar_grund": "keine_quellen",
    "quellen_qualität": "schlecht"
}
```

---

## Parallelisierung & Rate-Limiting

```python
# Semaphore für max parallele Requests
semaphore = asyncio.Semaphore(parallel)  # z.B. parallel=15

async def process_batch(batch: List[Dict], semaphore):
    """
    Verarbeitet Batch von Claims parallel mit Rate-Limiting.
    """

    tasks = []
    for claim in batch:
        # Semaphore begrenzt parallele Execution
        task = process_claim_with_semaphore(claim, semaphore)
        tasks.append(task)

    # Warte auf alle Tasks im Batch
    results = await asyncio.gather(*tasks)
    return results


async def process_claim_with_semaphore(claim, semaphore):
    """
    Wrapper mit Semaphore-Locking.
    """
    async with semaphore:  # Blockiert wenn Limit erreicht
        # 1. Suche Quellen (hybrid_search oder multi_layer_search)
        sources, source_type = await hybrid_search(claim, perplexity_key)

        # 2. Bewerte Claim
        result = await fact_check_claim(claim, sources, claude_client)

        return result
```

**Performance-Tuning:**

```python
# Zu hoch → API-Errors (429 Too Many Requests)
parallel=30  # ❌ Perplexity schlägt oft fehl

# Optimal für Stability
parallel=15  # ✅ Balance zwischen Speed & Stability

# Zu niedrig → Langsam
parallel=5   # ⏱️ Dauert ewig
```

---

## Datenfluss & CSV-Schema

### Input: `claims_canonical.csv`

```csv
canonical_id;canonical_text;frequency;models_covering;topics;claim_types;deutschland_bezug_verteilung
CC0558;Produktprotein hat biologische Wertigkeit von ca. 88.;119;Grok(46),Claude(35),Gemini(31),GPT(7);Naehrstoff(119);Zahl(97),Definition(18);nein:97%,unklar:3%
```

**Spalten:**
- `canonical_id`: Eindeutige ID (CC + Nummer)
- `canonical_text`: Deduplizierter Claim-Text
- `frequency`: Wie oft kam dieser Claim vor (über alle Varianten)?
- `models_covering`: Welche AI-Modelle haben diesen Claim erwähnt?
- `topics`: Kategorien (Naehrstoff, Gesundheit, Wirtschaft, ...)
- `claim_types`: Typ (Zahl, qualitativ, Vergleich, ...)
- `deutschland_bezug_verteilung`: Verteilung ja/nein/unklar

### Output: `claims_factchecked_v2_full.csv`

```csv
canonical_id;canonical_text;frequency;...;bewertung;konfidenz;begründung;korrektur;source_type;quellen_qualität;kontext_hinweis;nicht_pruefbar_grund
CC0558;Produktprotein hat...;119;...;RICHTIG;0.95;Claim wird durch mehrere...;;perplexity;gut;;
```

**Neue Spalten:**
- `bewertung`: RICHTIG | WEITGEHEND_RICHTIG | ... | NICHT_PRÜFBAR
- `konfidenz`: 0.0-1.0
- `begründung`: Warum wurde so bewertet?
- `korrektur`: Falls FALSCH, korrigierte Version
- `source_type`: perplexity | scholar | pubmed | usda | none
- `quellen_qualität`: gut | mittel | schlecht
- `kontext_hinweis`: Zusätzlicher Kontext (optional)
- `nicht_pruefbar_grund`: keine_quellen | zu_vage | subjektiv | technisch | historisch

---

## Bekannte Probleme & Lösungsansätze

### Problem 1: Perplexity API-Instabilität

**Symptom:**
```
Batch 1-2: Perplexity funktioniert (30/30 erfolgreiche Calls)
Batch 3+:  Massenweise "Perplexity failed, trying Google Scholar..."
           → 80% der Claims landen bei "keine Quellen"
```

**Root Cause:**
- Unklar! Nicht reproduzierbar (V3-Test lief perfekt mit gleichen Claims)
- Mögliche Ursachen:
  - Rate-Limiting (429 Too Many Requests)
  - Temporäre API-Ausfälle
  - Zeitliche Muster (mehr Load zu bestimmten Zeiten?)

**Lösungsansätze:**

```python
# Option A: Retry-Mechanismus mit Exponential Backoff
async def search_web_perplexity_with_retry(claim, api_key, max_retries=3):
    for retry in range(max_retries):
        result = await search_web_perplexity(claim, api_key)
        if result:
            return result

        # Exponential Backoff
        wait_time = 2 ** retry  # 1s, 2s, 4s
        print(f"Retry {retry+1}/{max_retries} after {wait_time}s...")
        await asyncio.sleep(wait_time)

    return None

# Option B: Adaptive Rate-Limiting
class AdaptiveRateLimiter:
    def __init__(self, initial_parallel=15):
        self.parallel = initial_parallel
        self.failures = 0

    async def adjust(self, success: bool):
        if success:
            self.failures = 0
            # Erhöhe Parallelität bei Erfolg
            self.parallel = min(self.parallel + 1, 30)
        else:
            self.failures += 1
            # Senke Parallelität bei Fehler
            if self.failures > 3:
                self.parallel = max(self.parallel - 2, 5)
                print(f"Reduced parallel to {self.parallel}")

# Option C: Circuit Breaker Pattern
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failures = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN

    async def call(self, func, *args):
        if self.state == "OPEN":
            # Check if timeout expired
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                print("Circuit OPEN - skipping Perplexity, using fallback")
                return None

        try:
            result = await func(*args)
            if result:
                self.failures = 0
                self.state = "CLOSED"
                return result
            else:
                self.failures += 1
        except Exception:
            self.failures += 1

        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            self.last_failure_time = time.time()
            print(f"Circuit opened after {self.failures} failures")

        return None
```

### Problem 2: Google Scholar Selenium-Errors

**Symptom:**
```
Could not close webdriver cleanly: [Errno 54] Connection reset by peer
```

**Root Cause:**
- `scholarly` Library nutzt Selenium im Hintergrund
- Google blockiert manchmal automatisierte Requests
- Verbindungsabbrüche bei vielen parallelen Requests

**Lösungsansätze:**

```python
# Option A: Retry-Mechanismus
async def search_google_scholar_with_retry(claim, max_retries=2):
    for retry in range(max_retries):
        try:
            result = await search_google_scholar(claim)
            return result
        except Exception as e:
            print(f"Scholar error (retry {retry+1}): {e}")
            await asyncio.sleep(5)
    return None

# Option B: Alternative Scholar-API (SerperDev, CrossRef)
async def search_crossref(claim):
    """
    Alternative zu Google Scholar via CrossRef API.
    Kostenlos, stabil, kein Selenium.
    """
    url = "https://api.crossref.org/works"
    params = {
        "query": claim,
        "rows": 3,
        "select": "title,author,published-print"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            items = data.get("message", {}).get("items", [])

    results = []
    for item in items:
        title = item.get("title", [""])[0]
        year = item.get("published-print", {}).get("date-parts", [[None]])[0][0]
        authors = item.get("author", [])
        author_name = authors[0].get("family", "Unbekannt") if authors else "Unbekannt"

        results.append(f"{author_name} ({year}): {title}")

    return "\n".join(results) if results else None
```

### Problem 3: Hohe NICHT_PRÜFBAR-Rate (84%)

**Ursachen (V2 Full-Run):**
- 77% keine_quellen (hauptsächlich Perplexity API-Probleme!)
- 20% zu_vage (echtes Problem: "sehr gut", "oft", "viel")
- 3% subjektiv (Geschmack, Meinungen)

**Lösungsansätze:**

```python
# Für "zu_vage" Claims: Claim-Refinement vor Fact-Check
async def refine_vague_claim(claim: str, claude_client) -> str:
    """
    Macht vage Claims konkreter via Claude.

    Beispiel:
    Input:  "Produkt ist sehr gesund"
    Output: "Produkt enthält wichtige Nährstoffe wie Calcium und Protein"
    """

    prompt = f"""
Formuliere diesen vagen Claim konkreter und prüfbarer:

CLAIM: {claim}

Mache daraus einen konkreten, fact-checkbaren Claim.
Falls nicht möglich, gib zurück: "NICHT_REFINABLE"
"""

    response = await claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    refined = response.content[0].text.strip()

    if "NICHT_REFINABLE" in refined:
        return None
    else:
        return refined
```

---

## Performance-Metriken

### V2 Full-Run (1.046 Claims)

```
Laufzeit:        ~18 Minuten (parallel=15)
Claims/min:      ~58
Total API-Calls:
  - Perplexity:  1.046 Versuche, 119 erfolgreich (11,4%)
  - Scholar:     927 Fallback-Versuche, 84 erfolgreich (9,1%)
  - Claude:      1.046 Bewertungs-Calls

Kosten (geschätzt):
  - Perplexity:  119 Calls × $0.001 = $0.12
  - Claude:      1.046 Calls × (2000 Tokens × $0.003/1k) = $6.28
  Total:         ~$6.40
```

### V3 Test-Run (27 Claims)

```
Laufzeit:        0,9 Minuten (parallel=10)
Claims/min:      ~30
Erfolgsrate:     92,6% (25/27 erfolgreich geprüft)
Perplexity:      27/27 erfolgreich (!!)
Scholar/PubMed:  0 Calls (Perplexity reichte aus)
```

---

## Empfehlungen für Till

### Sofort prüfen

1. **Setup-Test**: Läuft `run_factcheck_v2.py --mode sample --limit 10`?
2. **Code-Review**:
   - `run_factcheck_v2.py:hybrid_search()` → Fallback-Logik klar?
   - `dedup_claims.py:deduplicate_claims()` → Clustering-Algorithmus verstanden?
3. **Ergebnisse**: `claims_factchecked_v2_full.csv` durchsehen
   - Sind Bewertungen nachvollziehbar?
   - Sind Begründungen sinnvoll?

### Verbesserungen (Priorität)

**P0 - Kritisch:**
1. **Perplexity-Stabilität**:
   - Retry-Mechanismus implementieren (exponential backoff)
   - Circuit Breaker Pattern für automatisches Fallback
   - Monitoring: Log Erfolgsrate pro Batch

**P1 - Wichtig:**
2. **Alternative Quellen**:
   - CrossRef statt Google Scholar (kein Selenium!)
   - PubMed priorisieren für Nährwert-Claims
   - Eurostat/FAO für historische Wirtschaftsdaten

**P2 - Nice-to-Have:**
3. **Claim-Refinement**:
   - Vage Claims vor Fact-Check konkretisieren
   - Topic-basiertes Query-Refinement
4. **Caching**:
   - Quellen-Suche cachen (gleicher Claim = gleiche Quellen)
   - Redis für distributed caching

### Code-Qualität

- **Type Hints**: Alle Functions haben Type-Hints (PEP 484)
- **Docstrings**: Alle Major-Functions dokumentiert
- **Error-Handling**: Try-Except in allen async-Functions
- **Logging**: print() statements → Ersetzen durch logging-Module

### Tests

```python
# Unit-Tests für einzelne Layer
pytest tests/test_perplexity_search.py
pytest tests/test_scholar_search.py
pytest tests/test_dedup.py

# Integration-Test
pytest tests/test_full_pipeline.py
```

---

## Technologie-Entscheidungen

| Entscheidung | Begründung |
|--------------|------------|
| **Claude Sonnet 4.6** | Best-in-class für Claim-Extraction & Bewertung |
| **Voyage-3-large** | State-of-the-art Embeddings (1024 dim, besser als OpenAI) |
| **Perplexity sonar-pro** | Schnell, aktuelle Web-Quellen, zitiert Quellen |
| **Google Scholar** | Wissenschaftliche Papers (kostenlos, aber Selenium-basiert) |
| **PubMed** | NIH-Datenbank (kostenlos, stabil, medizinisch) |
| **USDA FoodData** | Offizielle US-Nährwertdaten (exakt, kostenlos) |
| **asyncio + aiohttp** | Async I/O für parallele API-Calls |
| **Pandas** | CSV-Handling (Standard für Data Science) |
| **Semaphore** | Rate-Limiting ohne externe Dependencies |

---

**Bei Fragen: Jakob erreichen unter drjakobvicari@gmail.com**
