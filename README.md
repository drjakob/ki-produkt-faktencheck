# KI-Produkt-Faktencheck System

**Status:** Proof-of-Concept abgeschlossen
**Datum:** 24. April 2026
**Entwickler:** Jakob (mit Claude Code)
**Review:** Till

---

## Was ist das Projekt?

Ein automatisiertes System, das **KI-generierte Claims über Produkte** aus verschiedenen AI-Modellen (Claude, GPT, Gemini, Grok) extrahiert, dedupliziert und fact-checkt.

### Warum?

KI-Modelle produzieren unterschiedliche Aussagen über Produkte. Dieses System:
1. **Extrahiert** alle Claims aus AI-Antworten
2. **Dedupliziert** semantisch ähnliche Claims
3. **Fact-checkt** sie gegen Web-Quellen
4. **Kategorisiert** nach Bewertung (RICHTIG, FALSCH, NICHT_PRÜFBAR, etc.)

### Kernzahlen (Full-Run V2)

```
Input:  1.046 deduplizierte Claims
Output: 167 erfolgreich geprüfte Claims (16%)
        879 nicht prüfbar (84% - API-Probleme!)

Accuracy: 85,6% (bei prüfbaren Claims)
```

---

## Schnellstart für Till

### 1. Setup (einmalig)

```bash
# Navigiere zum Projekt
cd "/Users/3g2-43a-u1/Library/CloudStorage/GoogleDrive-drjakobvicari@gmail.com/Meine Ablage/HSH-2025/JakobsProjekte2025/Produktreporting/Faktenchecker"

# Erstelle Virtual Environment
python3 -m venv venv_extraction

# Aktiviere Environment
source venv_extraction/bin/activate

# Installiere Dependencies
pip install anthropic aiohttp pandas scholarly python-dotenv voyageai perplexity-ai
```

### 2. API-Keys konfigurieren

Kopiere `.env.example` zu `.env` und füge deine API-Keys ein:

```bash
cp .env.example .env
# Editiere .env mit deinen Keys
```

Siehe `.env.example` für Details zu den benötigten API-Keys.

### 3. Test-Run (klein, schnell)

```bash
# Fact-Check von 10 Claims zum Testen
python run_factcheck_v2.py --mode sample --limit 10 --output test_output.csv

# Ergebnis anschauen
cat test_output.csv
```

### 4. Wichtige Dateien durchschauen

| Datei | Was ist das? |
|-------|--------------|
| `README.md` | **DIESE DATEI** - Projekt-Übersicht |
| `ARCHITEKTUR.md` | Technische Architektur-Dokumentation |
| `FACTCHECK_V2_VERGLEICH.md` | V1 vs V2 Evaluierung |
| `run_factcheck_v2.py` | **Haupt-Script** für Fact-Checking (Hybrid Search) |
| `run_factcheck_v3.py` | Erweiterte Version mit 4-Layer-Fallback |
| `dedup_claims.py` | Claim-Deduplizierung via Embeddings |
| `claims_canonical.csv` | **1.046 deduplizierte Claims** (Input) |
| `claims_factchecked_v2_full.csv` | **Full-Run Ergebnisse** (Output) |

---

## System-Architektur (High-Level)

```
┌─────────────────────┐
│ AI Model Responses  │  4 Modelle × 500 Prompts = 19.153 Claims
│ (CSV Input)         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Claim Extraction    │  Claude Sonnet 4.6 extrahiert strukturierte Claims
│ run_extraction_v2.py│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Deduplication       │  Voyage Embeddings + Clustering → 1.046 Claims
│ dedup_claims.py     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Fact-Checking       │  V2: Perplexity + Google Scholar Fallback
│ run_factcheck_v2.py │  V3: + PubMed + USDA FoodData
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Results CSV         │  Bewertung, Konfidenz, Begründung, Quellen
└─────────────────────┘
```

---

## Fact-Checking Flow (V2 - Hybrid Search)

```
Claim → Perplexity API ──┐
                         │
           [Erfolg?] ────┼─→ JA → Bewertung via Claude Sonnet 4.6
                         │
                         └─→ NEIN → Google Scholar Fallback
                                    │
                         [Erfolg?] ┼─→ JA → Bewertung
                                    │
                                    └─→ NEIN → NICHT_PRÜFBAR (keine_quellen)
```

### Bewertungsskala

```
RICHTIG              - Claim voll bestätigt
WEITGEHEND_RICHTIG   - Claim im Kern richtig, kleine Abweichungen
TEILWEISE_RICHTIG    - Claim teils richtig, teils falsch
IRREFÜHREND          - Claim technisch wahr, aber missverständlich
FALSCH               - Claim widerlegt
NICHT_PRÜFBAR        - Keine Quellen oder zu vage
```

---

## Wichtige Erkenntnisse

### ✅ Was funktioniert gut

- **Claim Extraction**: Claude Sonnet 4.6 extrahiert sauber strukturierte Claims
- **Deduplication**: Voyage Embeddings clustern semantisch ähnliche Claims perfekt
- **Fact-Checking Accuracy**: 85,6% Accuracy bei prüfbaren Claims
- **Hybrid Search**: Google Scholar rettet viele Claims, die Perplexity nicht findet

### ⚠️ Bekannte Probleme

1. **Perplexity API-Instabilität**:
   - Batch 1-2 laufen perfekt
   - Ab Batch 3 massive Ausfälle
   - 80% der Claims landen bei "keine Quellen"
   - **Nicht reproduzierbar** (V3-Test lief perfekt mit gleichen Claims!)

2. **Hohe NICHT_PRÜFBAR-Rate**:
   - 84% im V2 Full-Run (hauptsächlich API-bedingt)
   - Echte Gründe: zu_vage (20%), subjektiv (3%)

3. **Google Scholar Stabilität**:
   - Selenium-basiert (webdriver errors)
   - Langsamer als Perplexity

---

## Wie man die Scripts verwendet

### Claim Extraction

```bash
# Extrahiere Claims aus AI-Responses (parallele Verarbeitung)
python run_extraction_v2.py \
  --mode full \
  --input "Responses-Whitepaper-Prompt-Set-April2026 (4).csv" \
  --output claims_raw.csv \
  --parallel 30
```

### Deduplication

```bash
# Dedupliziere semantisch ähnliche Claims
python dedup_claims.py \
  --input claims_raw.csv \
  --output claims_canonical.csv \
  --threshold 0.82
```

### Fact-Checking V2 (Hybrid Search)

```bash
# Sample-Run (10 Claims zum Testen)
python run_factcheck_v2.py --mode sample --limit 10

# Priority-Run (Claims mit Frequency >= 50)
python run_factcheck_v2.py \
  --mode priority \
  --min-frequency 50 \
  --parallel 20 \
  --output claims_priority.csv

# Full-Run (alle 1.046 Claims)
python run_factcheck_v2.py \
  --mode all \
  --parallel 15 \
  --output claims_full.csv
```

### Fact-Checking V3 (4-Layer Fallback)

```bash
# V3 mit PubMed + USDA Fallback
python run_factcheck_v3.py \
  --mode all \
  --input claims_canonical.csv \
  --output claims_v3.csv \
  --parallel 10
```

---

## Output-Format (CSV)

```csv
canonical_id;canonical_text;bewertung;konfidenz;begründung;korrektur;source_type;quellen_qualität
CC0558;Produktprotein hat biologische Wertigkeit von 88;RICHTIG;0.95;Mehrfach bestätigt;;"perplexity";gut
CC0798;20-30% Soja im Produktkuh-Futter;FALSCH;0.85;Nur 9,9-19,8% laut Studien;Etwa 9,9-19,8%;"scholar";mittel
```

**Spalten:**
- `canonical_id`: Eindeutige Claim-ID
- `canonical_text`: Deduplizierter Claim-Text
- `bewertung`: RICHTIG | WEITGEHEND_RICHTIG | FALSCH | NICHT_PRÜFBAR | ...
- `konfidenz`: 0.0-1.0 (wie sicher ist die Bewertung?)
- `begründung`: Warum wurde so bewertet?
- `korrektur`: Falls falsch, korrigierte Version
- `source_type`: perplexity | scholar | pubmed | usda | none
- `quellen_qualität`: gut | mittel | schlecht

---

## Nächste Schritte (für Till)

### Sofort prüfen

1. **Setup testen**: Läuft `run_factcheck_v2.py --mode sample --limit 10`?
2. **V2 Full-Run Ergebnisse**: `claims_factchecked_v2_full.csv` durchsehen
3. **Code-Review**: Ist die Architektur verständlich?

### Verbesserungsideen

1. **Perplexity API-Stabilität**:
   - Retry-Mechanismus mit exponential backoff
   - Rate-Limiting intelligenter gestalten
   - Alternative: Direkt zu Scholar switchen bei ersten Fehlern

2. **Quellen-Diversifikation**:
   - Mehr Datenbanken (Eurostat, FAO für historische Daten)
   - PubMed für medizinische Claims priorisieren
   - USDA FoodData für exakte Nährwertangaben

3. **Performance**:
   - Batch-Processing optimieren
   - Caching für wiederholte Queries

4. **Monitoring**:
   - Real-time Dashboard für Fact-Check-Läufe
   - Error-Tracking (welche Claims schlagen warum fehl?)

---

## Kosten & Performance

### V2 Full-Run (1.046 Claims)

```
Laufzeit:    ~18 Minuten (parallel=15)
Kosten:      ~$6 (geschätzt)
Rate:        ~58 Claims/min
API-Calls:
  - Perplexity:  119 erfolgreiche Calls
  - Scholar:      84 erfolgreiche Calls
  - Claude:    1.046 Bewertungs-Calls
```

---

## Fragen?

**Jakob erreichen:**
- Email: drjakobvicari@gmail.com
- Projekt-Ordner: `/Users/3g2-43a-u1/.../Faktenchecker/`

**Weitere Docs:**
- `ARCHITEKTUR.md` - Technische Details
- `FACTCHECK_V2_VERGLEICH.md` - V1 vs V2 Evaluation
- Inline-Code-Kommentare in allen Python-Files

---

**Viel Erfolg, Till! Bei Fragen melde dich bei Jakob.**
