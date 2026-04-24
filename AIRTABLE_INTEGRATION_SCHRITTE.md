# Airtable Integration in "KI-Milch-Monitor" - Schritt-für-Schritt

Kurzanleitung zur Integration der `verified_facts` Tabelle in deine bestehende Airtable Base.

---

## Schritt 1: Neue Tabelle in KI-Milch-Monitor erstellen

1. **Öffne Airtable** und navigiere zu deiner Base **"KI-Milch-Monitor"**

2. **Erstelle neue Tabelle:**
   - Klicke auf "+" oder "Add a table"
   - Name: `verified_facts`

3. **Lösche Standard-Felder** (Name, Notes, etc.)

---

## Schritt 2: Felder konfigurieren (copy-paste freundlich!)

**Primary Field:**
- Name: `fact_id`
- Typ: Single line text

**Weitere Felder hinzufügen** (klicke auf "+", dann folgende Felder):

### Text-Felder (Single line text)
- `numerischer_wert`
- `einheit`
- `verified_by` → Ändere zu **Single select**, Optionen:
  - Opus Research
  - Manual Review
  - Scientific Study
  - Government Report

### Long Text-Felder
- `canonical_text`
- `begründung`
- `korrektur`
- `quellen` (pipe-separated URLs)
- `keywords`
- `kontext_hinweis`

### Single Select-Felder

**category** (Single select):
- Emissionen
- Nährstoffe
- Wirtschaft
- Tierwohl
- Herkunft
- Verarbeitung
- Gesundheit
- Ethik
- andere

**bewertung** (Single select):
- RICHTIG
- WEITGEHEND_RICHTIG
- TEILWEISE_RICHTIG
- IRREFÜHREND
- FALSCH

**konfidenz** (Single select):
- hoch
- mittel
- niedrig

**quellen_qualität** (Single select):
- gut
- schwach

### Date-Feld
- `erstellt_am` (Date)

### Link-Feld (Optional)
- `opus_claim_id` (Single line text)

---

## Schritt 3: API-Zugriff konfigurieren

### 3.1 Personal Access Token erstellen (falls noch nicht vorhanden)

1. Gehe zu https://airtable.com/create/tokens
2. "Create new token"
3. Name: "KI-Milch-Monitor-API"
4. Scopes auswählen:
   - ✅ `data.records:read`
   - ✅ `data.records:write`
   - ✅ `schema.bases:read`
5. Add a base: Wähle "KI-Milch-Monitor"
6. **Create token** → Token kopieren und sicher speichern!

### 3.2 Base ID finden

1. Öffne "KI-Milch-Monitor" in Airtable
2. URL sieht aus wie: `https://airtable.com/appXXXXXXXXXXXXXX/...`
3. Kopiere `appXXXXXXXXXXXXXX` (das ist deine Base ID)

---

## Schritt 4: Environment Variables setzen

**Option A: .env Datei** (empfohlen)

Erstelle/ergänze `.env` in deinem Projektordner:

```bash
# Airtable Layer 0
AIRTABLE_API_TOKEN="patXXXXXXXXXXXXXX.XXXXXXXXXXXXXXXXXX"
AIRTABLE_BASE_ID="appXXXXXXXXXXXXXX"
AIRTABLE_TABLE_NAME="verified_facts"

# Voyage AI (für Semantic Search)
VOYAGE_API_KEY="pa-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

**Option B: Shell Export**

```bash
export AIRTABLE_API_TOKEN="patXXXXXXXXXXXXXX.XXXXXXXXXXXXXXXXXX"
export AIRTABLE_BASE_ID="appXXXXXXXXXXXXXX"
export AIRTABLE_TABLE_NAME="verified_facts"
export VOYAGE_API_KEY="pa-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

---

## Schritt 5: Dependencies installieren

```bash
cd "/Users/3g2-43a-u1/Library/CloudStorage/GoogleDrive-drjakobvicari@gmail.com/Meine Ablage/HSH-2025/JakobsProjekte2025/Milchreporting/Faktenchecker"

source venv_extraction/bin/activate

pip install pyairtable>=2.3.0
```

---

## Schritt 6: Test-Import (3 Test-Facts aus Opus Research)

```bash
# Lade Environment Variables
source .env  # Falls du .env verwendest

# Test-Import mit bereits vorhandenen Opus-Test-Daten
python airtable_import.py \
  --mode import \
  --input opus_research_test.jsonl

# Erwartetes Output:
# AIRTABLE IMPORT
# ======================================================================
#
# Lade existierende fact_ids aus Airtable...
#   0 existierende Facts gefunden
#
# Lade Opus Results aus opus_research_test.jsonl...
#   3 Results geladen
#
# Konvertiere zu Airtable Records...
#   3 neue Records
#   0 übersprungen (bereits vorhanden)
#
# Importiere in Airtable...
#   [3/3] Batch importiert
#
# ======================================================================
# IMPORT ABGESCHLOSSEN
#   3 Records importiert
```

---

## Schritt 7: Verifikation in Airtable

1. Öffne "KI-Milch-Monitor" → Tabelle "verified_facts"
2. Du solltest 3 neue Records sehen:
   - FACT_0001: Methan aus Kühen...
   - FACT_0002: Etwa 20-30% des Futters...
   - FACT_0003: Hafermilch enthält kaum Protein...
3. Prüfe die Felder (bewertung, konfidenz, quellen, etc.)

---

## Schritt 8: Test Semantic Search

```bash
# Test mit bekanntem Claim
python airtable_search.py \
  --claim "Methan aus Kühen macht ca. 70% der Emissionen aus"

# Erwartetes Output:
# AIRTABLE VERIFIED FACT (Similarity: 0.9XX):
#
# CLAIM: Methan aus Kühen macht ca. 70% der Emissionen in der Milchproduktion aus
# BEWERTUNG: WEITGEHEND_RICHTIG
# KONFIDENZ: hoch
# BEGRÜNDUNG: ...
# QUELLEN-QUALITÄT: gut
#
# URLs: [https://thuenen.de/..., ...]
```

---

## Schritt 9: V5 Fact-Checking testen

```bash
# Kleiner Test-Run mit V5 (Airtable Layer 0 aktiv)
python run_factcheck_v3_improved.py \
  --mode sample \
  --limit 5 \
  --parallel 1 \
  --output test_v5_airtable.csv

# Prüfe Output:
# - Falls ein Claim matched: source_type sollte "airtable" sein
# - Check Console-Output für "✓ Airtable Match gefunden"
```

---

## Nächste Schritte (Optional)

### Opus Full-Run (100 Claims)

```bash
# 1. Opus Deep Research für Top-100 NICHT_PRÜFBAR Claims
python opus_research_batch.py \
  --input claims_nicht_pruefbar_top100.csv \
  --output opus_research_results.jsonl \
  --resume

# Kosten: ~$20-30
# Dauer: ~5-10 Minuten

# 2. Import in Airtable
python airtable_import.py \
  --mode import \
  --input opus_research_results.jsonl \
  --resume

# 3. V5 Production Run
python run_factcheck_v3_improved.py \
  --mode all \
  --parallel 20 \
  --output claims_factchecked_v5_full.csv
```

---

## Troubleshooting

### "pyairtable not found"
```bash
source venv_extraction/bin/activate
pip install pyairtable>=2.3.0
```

### "Invalid API token"
- Prüfe Token in https://airtable.com/create/tokens
- Stelle sicher, dass Scopes korrekt sind (`data.records:read`, `data.records:write`)
- Prüfe, dass Base "KI-Milch-Monitor" hinzugefügt ist

### "Table not found: verified_facts"
- Prüfe Tabellennamen in Airtable (exakte Schreibweise!)
- Falls anders benannt: `export AIRTABLE_TABLE_NAME="dein_tabellenname"`

### "No matching fact found" (bei Test)
- Normal bei neuen Claims
- Cache refresh: `rm -rf .cache/airtable_embeddings.json`
- Dann erneut testen

---

## Zusammenfassung

✅ Neue Tabelle `verified_facts` in "KI-Milch-Monitor" erstellt
✅ API Token erstellt und konfiguriert
✅ Environment Variables gesetzt
✅ Test-Import erfolgreich (3 Facts)
✅ Semantic Search funktioniert
✅ V5 mit Airtable Layer 0 bereit!

**Deine Airtable Base ist jetzt ready für das KI-Fact-Checking System!**

Bei Fragen siehe:
- **AIRTABLE_SETUP.md** - Detaillierte Dokumentation
- **AIRTABLE_QUICKSTART.md** - Workflow-Übersicht
- **airtable_search.py** - Semantic Search Code
- **airtable_import.py** - Import-Logic
