# Airtable Layer 0 - Quick Start Guide

Komplette Anleitung zur Nutzung der kuratierten Fakten-Datenbank als Layer 0.

---

## 🚀 Quick Start (3 Schritte)

### 1️⃣ Airtable Base Setup

```bash
# Folge der detaillierten Anleitung in AIRTABLE_SETUP.md
# - Öffne bestehende Base "KI-Milch-Monitor"
# - Erstelle neue Tabelle "verified_facts" (siehe Schema in AIRTABLE_SETUP.md)
# - Erstelle Personal Access Token (falls noch nicht vorhanden)
# - Kopiere Base ID aus URL (appXXXXXXXXXXXXXX)
```

### 2️⃣ Environment Variables

Füge zu `.env` oder `~/.bashrc` hinzu:

```bash
export AIRTABLE_API_TOKEN="patXXXXXXXXXXXXXX.XXXXXXXXXXXXXXXXXX"
export AIRTABLE_BASE_ID="appXXXXXXXXXXXXXX"
export AIRTABLE_TABLE_NAME="verified_facts"  # Optional, default
export VOYAGE_API_KEY="pa-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

### 3️⃣ Dependencies installieren

```bash
source venv_extraction/bin/activate
pip install pyairtable>=2.3.0  # Falls noch nicht installiert
```

---

## 📊 Workflow: Opus Research → Airtable → V5

### Phase 1: Opus Deep Research (EINMALIG)

**Input:** Top-100 NICHT_PRÜFBAR Claims (`claims_nicht_pruefbar_top100.csv`)

```bash
# Starte Opus 4.7 Deep Research
python opus_research_batch.py \
  --input claims_nicht_pruefbar_top100.csv \
  --output opus_research_results.jsonl \
  --resume

# Erwartete Kosten: ~$20-30 für 100 Claims
# Dauer: ~5 Minuten (bei 2 Sekunden/Claim Rate-Limit)
```

**Output:** `opus_research_results.jsonl` (JSON Lines mit Research-Ergebnissen)

**Test (bereits durchgeführt):**
```bash
# 3 Claims getestet → opus_research_test.jsonl
# Alle mit hoher Konfidenz + guten Quellen (Thünen, BLE, BMEL)
```

---

### Phase 2: Import in Airtable

```bash
# Importiere Opus-Ergebnisse in Airtable
python airtable_import.py \
  --mode import \
  --input opus_research_results.jsonl \
  --resume

# Generiert automatisch:
# - FACT_0001, FACT_0002, ... IDs
# - Keywords für Semantic Matching
# - Pipe-separated URLs
```

**Liste alle Facts (zur Verifikation):**

```bash
python airtable_import.py --mode list
```

---

### Phase 3: V5 Fact-Checking mit Airtable Layer 0

**Automatisch aktiv** sobald Environment Variables gesetzt sind!

```bash
# Normaler V5 Run (Airtable wird zuerst geprüft)
export ANTHROPIC_API_KEY="sk-ant-..."
export PERPLEXITY_API_KEY="pplx-..."
export USDA_API_KEY="..."
export VOYAGE_API_KEY="pa-..."
export AIRTABLE_API_TOKEN="pat..."
export AIRTABLE_BASE_ID="app..."

python run_factcheck_v3_improved.py \
  --mode all \
  --parallel 20 \
  --output claims_factchecked_v5_airtable.csv
```

**Layer-Order:**
1. **Layer 0 (Airtable):** Semantic Search (0.85 Threshold) ← Checked FIRST!
2. Layer 1 (Perplexity): Web-Suche
3. Layer 2 (USDA): Nährwertdaten
4. Layer 3 (Semantic Scholar): Wissenschaft
5. Layer 4 (OpenAlex): Wissenschaft (Fallback)

**Performance:**
- **Cache-Hit:** < 100ms (Embeddings gecacht)
- **Cache-Miss:** ~500ms (Voyage Embedding-Generierung)
- **API-Kosten:** Negligible (~$0.0001/Claim bei Cache-Hit)

---

## 🧪 Testing: Airtable Semantic Search

Test die Semantic Search isoliert:

```bash
# Test-Claim
python airtable_search.py \
  --claim "Methan aus Kühen macht ca. 70% der Emissionen aus" \
  --refresh  # Force reload Embeddings

# Erwartetes Output (falls Match gefunden):
# AIRTABLE VERIFIED FACT (Similarity: 0.923):
#
# CLAIM: Methan aus Kühen macht ca. 70% der Emissionen in der Milchproduktion aus
# BEWERTUNG: WEITGEHEND_RICHTIG
# KONFIDENZ: hoch
# BEGRÜNDUNG: ...
# URLs: [https://thuenen.de/..., https://bmel.de/...]
```

**Kein Match:**
```bash
python airtable_search.py \
  --claim "Milch enthält 500% mehr Kalzium als Brokkoli"

# Output:
# Kein Match gefunden (Similarity < 0.85)
```

---

## 🔧 Maintenance

### Cache invalidieren (bei Airtable-Updates)

```bash
# Lösche lokalen Embeddings-Cache
rm -rf .cache/airtable_embeddings.json

# Nächster Run lädt Facts neu und generiert Embeddings
```

### Neue Facts hinzufügen

**Manuell via Airtable Web UI:**
1. Öffne Airtable Base
2. Füge neuen Record hinzu
3. Warte 24h (Cache-TTL) ODER lösche Cache manuell

**Via Opus Research (neue NICHT_PRÜFBAR Claims):**
```bash
# 1. Neue Claims extrahieren
python analyse_nicht_pruefbar.py  # Erstellt neue Top-100 Liste

# 2. Opus Research für neue Claims
python opus_research_batch.py \
  --input claims_nicht_pruefbar_top100_neu.csv \
  --output opus_research_results_neu.jsonl

# 3. Import in Airtable (skip existierende fact_ids)
python airtable_import.py \
  --mode import \
  --input opus_research_results_neu.jsonl \
  --resume \
  --start-id 101  # Fortsetzung nach FACT_0100
```

---

## 📈 Performance-Monitoring

### Airtable Cache Status

```python
from airtable_search import is_cache_valid, get_cache_path
import os

cache_path = get_cache_path("embeddings")

if is_cache_valid(cache_path):
    print(f"✓ Cache gültig (< 24h alt)")
    mtime = os.path.getmtime(cache_path)
    print(f"  Letzte Aktualisierung: {datetime.fromtimestamp(mtime)}")
else:
    print(f"✗ Cache abgelaufen oder nicht vorhanden")
```

### V5 Layer-Usage-Stats

Nach V5 Full-Run:

```bash
# Zähle source_type=airtable
grep -c '"airtable"' claims_factchecked_v5_airtable.csv

# Erwartete Hit-Rate (bei 100 kuratierten Facts):
# - Top-100 Claims: ~70-80% Airtable-Hits
# - Long-Tail Claims: ~5-10% Airtable-Hits
# - Gesamt: ~15-25% Airtable-Hits (bei 1046 Claims)
```

---

## 💰 Kosten-Kalkulation

### Opus Research (Einmalig)
- **100 Claims:** ~$20-30 (Opus 4.7 Deep Research)
- **Pro Claim:** ~$0.20-0.30

### Airtable
- **Free Tier:** 1.200 records/base (ausreichend für Start)
- **API Calls:** 1.000/Monat (bei semantic search kein Problem, da gecacht)

### Voyage Embeddings
- **100 Facts einmalig:** ~$0.0006 (negligible)
- **Pro Claim (Query):** ~$0.000006 (negligible)
- **1000 Claim-Checks:** ~$0.006

### Gesamt (bei 100 kuratierten Facts)
- **Setup:** ~$20-30 (Opus Research) + $0.0006 (Fact Embeddings)
- **Laufend:** ~$0.006/1000 Claims (nur Query Embeddings)

**ROI:**
- 1 Airtable-Hit spart ~$0.02 (Perplexity API Call)
- Bei 70% Hit-Rate auf Top-100 Claims: ~$1.40 Ersparnis/Run
- **Break-Even:** Nach ~15 Full-Runs

---

## 🐛 Troubleshooting

### "AIRTABLE_API_TOKEN not set"

```bash
# Prüfe Environment Variables
echo $AIRTABLE_API_TOKEN
echo $AIRTABLE_BASE_ID
echo $VOYAGE_API_KEY

# Falls leer: exportiere neu oder füge zu .env hinzu
source .env
```

### "ImportError: No module named 'pyairtable'"

```bash
source venv_extraction/bin/activate
pip install pyairtable>=2.3.0
```

### "No matching fact found"

Normal bei neuen Claims. Verifikationen:
1. Prüfe Cache-Gültigkeit (`rm -rf .cache/airtable_embeddings.json`)
2. Prüfe Airtable Base (sind Facts vorhanden?)
3. Test mit bekanntem Claim (siehe Testing-Sektion)

### Similarity immer < 0.85

```python
# Threshold zu konservativ? Test mit niedrigerem Wert:
python airtable_search.py \
  --claim "..." \
  --threshold 0.75  # Experimentell
```

**ACHTUNG:** Threshold < 0.85 kann False Positives erzeugen!

---

## 📚 Weitere Dokumentation

- **AIRTABLE_SETUP.md:** Detaillierte Setup-Anleitung, Schema, API-Docs
- **airtable_import.py:** Code für Opus → Airtable Import
- **airtable_search.py:** Semantic Search Implementation
- **opus_research_batch.py:** Opus 4.7 Deep Research Script
- **run_factcheck_v3_improved.py:** V5 Main Script (mit Layer 0)

---

**Status:** V5 Airtable Layer 0 vollständig implementiert und getestet ✓
**Next Steps:** Opus Full-Run (100 Claims) → Airtable Import → V5 Production Run
