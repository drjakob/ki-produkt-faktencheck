# Airtable Base Setup - Kuratierte Fakten-Datenbank

## Übersicht

Die Airtable-Integration nutzt deine **bestehende Base "KI-Milch-Monitor"** und fügt dort eine neue Tabelle hinzu. Diese dient als **Layer 0** im Hybrid-Search-System und wird **als erstes** durchsucht, bevor Perplexity/USDA/Semantic Scholar/OpenAlex verwendet werden.

**Konzept:** Manuell kuratierte, verifizierte Fakten aus Opus 4.7 Deep Research, die mit semantischer Suche gegen eingehende Claims abgeglichen werden.

**Setup:** Neue Tabelle `verified_facts` in bestehender Base "KI-Milch-Monitor" erstellen.

## Base-Struktur

### Table: `verified_facts`

| Feldname | Typ | Beschreibung | Beispiel |
|----------|-----|--------------|----------|
| `fact_id` | Text (Primary) | Eindeutige ID | `FACT_0001` |
| `canonical_text` | Long text | Normalisierter Fakt-Text | "Methan aus Kühen macht ca. 70% der Emissionen in der Milchproduktion aus" |
| `category` | Single select | Themen-Kategorie | Emissionen / Nährstoffe / Wirtschaft / Tierwohl |
| `bewertung` | Single select | Verifizierter Status | RICHTIG / WEITGEHEND_RICHTIG / TEILWEISE_RICHTIG / IRREFÜHREND / FALSCH |
| `konfidenz` | Single select | Vertrauenswürdigkeit | hoch / mittel / niedrig |
| `numerischer_wert` | Text | Exakter Wert (falls numerisch) | "70%" / "3.3 g/100ml" |
| `einheit` | Text | Maßeinheit | "%" / "g/100ml" / "kg CO2e" |
| `begründung` | Long text | Wissenschaftliche Begründung | "Mehrere Studien bestätigen..." |
| `korrektur` | Long text | Korrigierte Version (falls FALSCH) | "Tatsächlich sind es 3-6%, nicht 20-30%" |
| `quellen` | Long text | Pipe-separated URLs | `https://thuenen.de/...\|https://bmel.de/...` |
| `quellen_qualität` | Single select | Quellen-Rating | gut / schwach |
| `erstellt_am` | Date | Erstellungsdatum | 2026-04-24 |
| `opus_claim_id` | Text | Original Claim ID (falls aus Opus) | `CC0767` |
| `keywords` | Long text | Comma-separated Keywords für Suche | "methan, emissionen, milchproduktion, kühe, treibhausgas" |
| `verified_by` | Single select | Quelle der Verifikation | Opus Research / Manual Review / Scientific Study |

### Single Select Options

**category:**
- Emissionen
- Nährstoffe
- Wirtschaft
- Tierwohl
- Herkunft
- Verarbeitung
- Gesundheit
- Ethik
- andere

**bewertung:**
- RICHTIG
- WEITGEHEND_RICHTIG
- TEILWEISE_RICHTIG
- IRREFÜHREND
- FALSCH

**konfidenz:**
- hoch
- mittel
- niedrig

**quellen_qualität:**
- gut
- schwach

**verified_by:**
- Opus Research
- Manual Review
- Scientific Study
- Government Report

## Workflow: Opus Research → Airtable

### 1. Opus Research ausführen

```bash
python opus_research_batch.py \
  --input claims_nicht_pruefbar_top100.csv \
  --output opus_research_results.jsonl \
  --resume
```

### 2. JSON → Airtable Import

Script: `airtable_import.py` (siehe unten)

```bash
python airtable_import.py \
  --input opus_research_results.jsonl \
  --mode import
```

### 3. Manuelle Review (optional)

- Öffne Airtable Base
- Filtere nach `verified_by = "Opus Research"` + `konfidenz = "niedrig"`
- Verifiziere Quellen und aktualisiere `verified_by = "Manual Review"`

## Airtable API Setup

### 1. Bestehende Base "KI-Milch-Monitor" verwenden

1. Öffne deine bestehende Airtable Base **"KI-Milch-Monitor"**
2. Erstelle eine **neue Tabelle** namens `verified_facts`
3. Konfiguriere die Felder gemäß Schema oben (siehe "Base-Struktur")

### 2. API Token erstellen

1. Gehe zu https://airtable.com/create/tokens
2. Erstelle Personal Access Token mit Scopes:
   - `data.records:read`
   - `data.records:write`
   - `schema.bases:read`
3. Notiere Token (wird nur einmal angezeigt!)

### 3. Base ID finden

1. Öffne deine Base "KI-Milch-Monitor" in Airtable
2. URL hat Format: `https://airtable.com/appXXXXXXXXXXXXXX/...`
3. `appXXXXXXXXXXXXXX` ist deine Base ID (die Base ID ist für ALLE Tabellen in der Base gleich!)

### 4. Environment Variables

Füge zu `.env` hinzu (oder exportiere):

```bash
export AIRTABLE_API_TOKEN="patXXXXXXXXXXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
export AIRTABLE_BASE_ID="appXXXXXXXXXXXXXX"
export AIRTABLE_TABLE_NAME="verified_facts"
```

## Python API Integration

### Dependencies

```bash
pip install pyairtable voyageai
```

### Beispiel-Code

```python
from pyairtable import Api

api = Api(os.environ["AIRTABLE_API_TOKEN"])
table = api.table(os.environ["AIRTABLE_BASE_ID"], "verified_facts")

# Create Record
record = table.create({
    "fact_id": "FACT_0001",
    "canonical_text": "Methan aus Kühen macht ca. 70% der Emissionen aus",
    "category": "Emissionen",
    "bewertung": "WEITGEHEND_RICHTIG",
    "konfidenz": "hoch",
    "numerischer_wert": "70%",
    "quellen": "https://thuenen.de/...",
    "quellen_qualität": "gut"
})

# Query Records
records = table.all(formula="{category} = 'Emissionen'")

# Search with Semantic Similarity (implemented in airtable_search.py)
```

## Semantic Search Integration

### Konzept

1. **Embedding-Generierung:**
   - Bei Airtable-Import: Generiere Voyage-Embedding für `canonical_text`
   - Speichere Embedding in separater Tabelle `fact_embeddings` (wegen Airtable Field-Limits)

2. **Claim-Matching:**
   - Generiere Embedding für eingehenden Claim
   - Berechne Cosine-Similarity zu allen `fact_embeddings`
   - Threshold: 0.85 (sehr konservativ, nur hochrelevante Matches)

3. **Fallback:**
   - Falls kein Match > 0.85: Weiter zu Perplexity (Layer 1)

### Implementation

Siehe `airtable_search.py` (unten)

## Kosten-Kalkulation

### Airtable

- **Free Tier:** 1.200 records/base, 2 GB attachments, 1.000 API calls/month
- **Plus Plan ($20/month):** 5.000 records/base, 5 GB attachments, 5.000 API calls/month
- **Pro Plan ($50/month):** 50.000 records/base, 20 GB attachments, 10.000 API calls/month

### Voyage AI (Embeddings)

- **Voyage-3:** $0.06 / 1M tokens
- 100 Facts × ~100 tokens = 10k tokens = **$0.0006**
- Negligible costs

### Empfehlung

Start mit **Free Tier** (1.200 records ausreichend für Top-100 + manuelle Erweiterungen)

## Maintenance Workflow

### Wöchentlich

1. Prüfe neue NICHT_PRÜFBAR Claims aus Production
2. Falls häufige Claims (frequency > 50): Opus Research starten
3. Import in Airtable

### Monatlich

1. Review "niedrig" Konfidenz-Einträge
2. Aktualisiere veraltete Quellen
3. Ergänze Keywords für besseres Matching

## Next Steps

1. **Airtable Base erstellen** (manuell via Web UI)
2. **`airtable_import.py` implementieren** (Opus JSON → Airtable)
3. **`airtable_search.py` implementieren** (Semantic Search Layer)
4. **Layer 5 in `run_factcheck_v3_improved.py` integrieren**

---

**Status:** Setup-Dokumentation erstellt
**Next:** Python Scripts für Airtable-Integration implementieren
