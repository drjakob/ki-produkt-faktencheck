# Quick Start für Till

**Willkommen!** Dieses Dokument bringt dich in 15 Minuten auf Betriebstemperatur.

---

## Was du brauchst

- macOS (das ist Jakobs Setup)
- Python 3.9+ (sollte schon installiert sein)
- Zugang zu diesem Ordner (Google Drive)
- API-Keys (sind schon im Code hinterlegt, siehe unten)

---

## 5-Minuten-Setup

### 1. Terminal öffnen und ins Projekt navigieren

```bash
cd "/Users/3g2-43a-u1/Library/CloudStorage/GoogleDrive-drjakobvicari@gmail.com/Meine Ablage/HSH-2025/JakobsProjekte2025/Produktreporting/Faktenchecker"
```

### 2. Virtual Environment erstellen

```bash
python3 -m venv venv_extraction
source venv_extraction/bin/activate  # Du solltest jetzt (venv_extraction) im Prompt sehen
```

### 3. Dependencies installieren

```bash
pip install anthropic aiohttp pandas scholarly python-dotenv voyageai
```

**Hinweis:** Die Perplexity-Library ist nicht über PyPI verfügbar, wird aber direkt via aiohttp angesprochen.

---

## Erster Test-Run (2 Minuten)

```bash
# 1. Environment aktivieren (falls noch nicht aktiv)
source venv_extraction/bin/activate

# 2. API-Keys konfigurieren
# Erstelle .env Datei aus Template:
cp .env.example .env

# Füge deine API-Keys in .env ein (siehe .env.example für Details)
# export ANTHROPIC_API_KEY="sk-ant-api03-..."
# export PERPLEXITY_API_KEY="pplx-..."
source .env  # oder manuell exportieren

# 3. Test-Run mit 5 Claims
python run_factcheck_v2.py --mode sample --limit 5 --output test_till.csv
```

**Erwartetes Ergebnis:**

```
Lade claims_canonical.csv...
  → Alle Claims: 1046

Batch 1/1 wird verarbeitet...
  [CC0777] Recherchiere...
  [CC0777] ✓ RICHTIG (Konfidenz: 0.85, Quellen: perplexity)
  [CC0767] Recherchiere...
  [CC0767] ✓ FALSCH (Konfidenz: 0.90, Quellen: perplexity)
  ...

Ergebnisse gespeichert: test_till.csv
```

Schau dir dann `test_till.csv` an:

```bash
cat test_till.csv | head -20
```

oder

```bash
open test_till.csv  # Öffnet in Numbers/Excel
```

---

## Wichtige Dateien (Überblick in 5 Minuten)

### Lies als Erstes (in dieser Reihenfolge):

1. **README.md** (du bist hier) - Projekt-Übersicht
2. **Diese Datei** (QUICK_START_TILL.md) - Schnelleinstieg
3. **ARCHITEKTUR.md** - Technische Details (nur wenn du tiefer einsteigen willst)

### Haupt-Scripts:

| Datei | Was macht es? | Wann brauchst du es? |
|-------|---------------|----------------------|
| `run_factcheck_v2.py` | **Fact-Checking** (Perplexity + Scholar) | **START HIER** für Fact-Checks |
| `run_factcheck_v3.py` | Fact-Checking mit 4-Layer-Fallback | Nur wenn V2 zu viele Fehler hat |
| `dedup_claims.py` | Claim-Deduplizierung | Nur wenn neue Claims extrahiert wurden |
| `run_extraction_v2.py` | Claim-Extraction aus AI-Antworten | Nur wenn neue AI-Responses reinkommen |

### Daten-Dateien:

| Datei | Was ist drin? | Wichtigkeit |
|-------|---------------|-------------|
| `claims_canonical.csv` | **1.046 deduplizierte Claims** | **INPUT** für Fact-Checking |
| `claims_factchecked_v2_full.csv` | **Full-Run Ergebnisse** (V2) | **OUTPUT** - Haupt-Ergebnis |
| `claims_factchecked_v3_test.csv` | V3 Test-Ergebnisse (27 Claims) | Vergleich V2 vs V3 |
| `FACTCHECK_V2_VERGLEICH.md` | V1 vs V2 Evaluierung | Analyse der Verbesserungen |

---

## Schnell-Kommandos (Copy & Paste)

### Test-Run (5 Claims)

```bash
python run_factcheck_v2.py --mode sample --limit 5 --output test.csv
```

### Prio-Run (Claims mit hoher Frequency)

```bash
python run_factcheck_v2.py \
  --mode priority \
  --min-frequency 50 \
  --parallel 15 \
  --output claims_priority.csv
```

### Full-Run (alle 1.046 Claims, ~20 Min)

```bash
python run_factcheck_v2.py \
  --mode all \
  --parallel 15 \
  --output claims_full.csv
```

**Hinweis:** `parallel=15` ist der Sweet-Spot (Balance zwischen Speed & API-Stabilität).

---

## Ergebnisse Anschauen

### Im Terminal (schnell)

```bash
# Erste 20 Zeilen
head -20 test_till.csv

# Nur Bewertungs-Spalten
cut -d';' -f2,7,8,9 test_till.csv | head -20

# Zähle Bewertungen
cut -d';' -f7 test_till.csv | sort | uniq -c
```

### In Python (analytisch)

```python
import pandas as pd

df = pd.read_csv('test_till.csv', sep=';')

# Bewertungs-Verteilung
print(df['bewertung'].value_counts())

# Quellen-Verteilung
print(df['source_type'].value_counts())

# Nur RICHTIG-Claims
richtig = df[df['bewertung'] == 'RICHTIG']
print(richtig[['canonical_text', 'begründung']])
```

---

## Häufige Fragen

### Q: Warum gibt's so viele NICHT_PRÜFBAR?

**A:** Im V2 Full-Run: 84% NICHT_PRÜFBAR, hauptsächlich wegen Perplexity API-Instabilität. Im V3-Test lief es perfekt → API-Problem, kein System-Problem.

**Gründe (echt):**
- `keine_quellen`: 77% - Perplexity + Scholar finden nichts
- `zu_vage`: 20% - Claim zu unspezifisch ("sehr gut", "oft")
- `subjektiv`: 3% - Meinungen, Geschmack

### Q: Welches Script soll ich verwenden?

**A:** Für normale Fact-Checks: **run_factcheck_v2.py** (Hybrid Search)

**Nur wenn V2 zu viele Fehler produziert:** run_factcheck_v3.py (4-Layer Fallback)

### Q: Wie lange dauert ein Full-Run?

**A:**
- **Sample (10 Claims)**: ~20 Sekunden
- **Priority (81 Claims)**: ~2 Minuten
- **Full (1.046 Claims)**: ~18-20 Minuten

### Q: Was kosten die API-Calls?

**A:** Full-Run (1.046 Claims):
- **Perplexity**: ~119 Calls × $0.001 = $0.12
- **Claude**: ~1.046 Calls × $0.006 = $6.28
- **Total**: ~$6.40

### Q: Kann ich einen Run abbrechen?

**A:** Ja! **Ctrl+C** stoppt den Run. Du kannst mit `--resume` weitermachen (aber nicht implementiert in V2, TODO).

---

## Typische Workflows

### Workflow 1: Quick-Test (neue Changes testen)

```bash
# 1. Code ändern
nano run_factcheck_v2.py

# 2. Test mit 5 Claims
python run_factcheck_v2.py --mode sample --limit 5

# 3. Ergebnis anschauen
cat test_output.csv
```

### Workflow 2: Neue Claims fact-checken

```bash
# 1. Claims extrahieren (falls neue AI-Responses)
python run_extraction_v2.py \
  --input "neue_responses.csv" \
  --output claims_raw.csv

# 2. Deduplizieren
python dedup_claims.py \
  --input claims_raw.csv \
  --output claims_canonical_neu.csv

# 3. Fact-checken
python run_factcheck_v2.py \
  --mode all \
  --input claims_canonical_neu.csv \
  --output claims_factchecked_neu.csv
```

### Workflow 3: Ergebnisse analysieren

```python
import pandas as pd

# Lade Ergebnisse
df = pd.read_csv('claims_factchecked_v2_full.csv', sep=';')

# Top 10 häufigste RICHTIG-Claims
richtig = df[df['bewertung'] == 'RICHTIG']
top_richtig = richtig.nlargest(10, 'frequency')
print(top_richtig[['canonical_text', 'frequency', 'begründung']])

# Top 10 häufigste FALSCH-Claims
falsch = df[df['bewertung'] == 'FALSCH']
top_falsch = falsch.nlargest(10, 'frequency')
print(top_falsch[['canonical_text', 'frequency', 'korrektur']])

# Accuracy
pruefbar = df[df['bewertung'] != 'NICHT_PRÜFBAR']
richtig_oder_weitgehend = pruefbar[pruefbar['bewertung'].isin(['RICHTIG', 'WEITGEHEND_RICHTIG'])]
accuracy = len(richtig_oder_weitgehend) / len(pruefbar) * 100
print(f"Accuracy: {accuracy:.1f}%")
```

---

## Debugging

### Problem: "command not found: python"

**Lösung:**

```bash
python3 run_factcheck_v2.py --mode sample --limit 5
```

(macOS hat manchmal `python3` statt `python`)

### Problem: "ModuleNotFoundError: No module named 'anthropic'"

**Lösung:**

```bash
# Aktiviere Virtual Environment
source venv_extraction/bin/activate

# Installiere Dependencies
pip install anthropic aiohttp pandas scholarly
```

### Problem: "PermissionError: [Errno 13] Permission denied"

**Lösung:**

```bash
# Setze Permissions
chmod +x run_factcheck_v2.py
```

### Problem: Perplexity gibt nur Fehler zurück

**Lösung:**

```bash
# Checke API-Key
echo $PERPLEXITY_API_KEY

# Falls leer: setze via .env oder manuell
export PERPLEXITY_API_KEY="pplx-YOUR_KEY_HERE"

# Teste mit kleinerer Parallelität
python run_factcheck_v2.py --mode sample --limit 5 --parallel 5
```

---

## Nächste Schritte

### Sofort:

1. ✅ Setup testen (oben)
2. ✅ Test-Run durchführen (5 Claims)
3. ✅ Ergebnisse anschauen (`test_till.csv`)
4. ✅ README.md durchlesen

### Danach:

1. **Code-Review**: Schau dir `run_factcheck_v2.py` an
   - Ist die Hybrid-Search-Logik klar?
   - Verstehst du den Fact-Checking-Flow?

2. **Full-Run anschauen**: `claims_factchecked_v2_full.csv`
   - Sind Bewertungen nachvollziehbar?
   - Welche Claims sind RICHTIG/FALSCH?

3. **Verbesserungen**:
   - Perplexity-Stabilität (Retry-Mechanismus?)
   - Alternative Quellen (CrossRef statt Scholar?)
   - Claim-Refinement (vage Claims konkreter machen?)

### Optional (nur wenn du tiefer einsteigen willst):

- **ARCHITEKTUR.md** lesen (technische Details)
- **FACTCHECK_V2_VERGLEICH.md** lesen (V1 vs V2 Evaluierung)
- Code-Kommentare durchgehen (alle Funktionen sind dokumentiert)

---

## Fragen?

**Jakob erreichen:**
- Email: drjakobvicari@gmail.com
- Projekt-Ordner: Hier im Google Drive

**Bei Problemen:**
1. Checke `README.md` (Projekt-Übersicht)
2. Checke `ARCHITEKTUR.md` (technische Details)
3. Schau dir Inline-Kommentare im Code an
4. Schreib Jakob

---

**Viel Erfolg, Till! Das System läuft stabil, du kannst direkt loslegen.**
