# GitHub Setup Anleitung

**Status:** Projekt ist vorbereitet für GitHub-Upload

---

## Was wurde vorbereitet?

✅ `.gitignore` erstellt (schützt Secrets & Daten)
✅ `.env.example` erstellt (Template ohne echte Keys)
✅ `requirements.txt` erstellt (Dependencies)
✅ `LICENSE` erstellt (MIT License)
✅ Secrets aus Dokumentation entfernt
✅ Dokumentation vollständig (5 Markdown-Dateien)

---

## Schritt-für-Schritt GitHub-Upload

### 1. Git Repository initialisieren

```bash
cd "/Users/3g2-43a-u1/Library/CloudStorage/GoogleDrive-drjakobvicari@gmail.com/Meine Ablage/HSH-2025/JakobsProjekte2025/Produktreporting/Faktenchecker"

# Git initialisieren
git init

# Alle Dateien hinzufügen (ohne ignorierte)
git add .

# Status prüfen (sollte KEINE Secrets/Daten zeigen)
git status
```

**WICHTIG:** Prüfe, dass folgende Dateien NICHT in `git status` erscheinen:
- ❌ `*.csv` (außer Sample-Daten)
- ❌ `.env` (nur `.env.example` sollte committed werden)
- ❌ `*.pkl` (Embedding-Cache)
- ❌ `venv_*/` (Virtual Environment)

### 2. Ersten Commit erstellen

```bash
git commit -m "Initial commit: KI-Produkt-Faktencheck System

- 3-Phasen-Pipeline (Extraction, Deduplication, Fact-Checking)
- Hybrid Search (Perplexity + Google Scholar)
- Vollständige Dokumentation
- Ohne Secrets & Daten (siehe .gitignore)
"
```

### 3. GitHub Repository erstellen

**Option A: Via GitHub Web UI**
1. Gehe zu https://github.com/new
2. Repository Name: `ki-milch-faktencheck` (oder dein Wunschname)
3. Description: "Automatisiertes Fact-Checking System für KI-generierte Claims"
4. **Public** oder **Private** (deine Wahl)
5. **NICHT** "Initialize with README" ankreuzen (haben wir schon!)
6. Klicke "Create repository"

**Option B: Via GitHub CLI**
```bash
# Falls gh installiert ist
gh repo create ki-milch-faktencheck \
  --description "Automatisiertes Fact-Checking System" \
  --public  # oder --private
```

### 4. Remote hinzufügen & pushen

```bash
# Remote hinzufügen (ersetze USERNAME)
git remote add origin https://github.com/USERNAME/ki-milch-faktencheck.git

# Oder SSH:
# git remote add origin git@github.com:USERNAME/ki-milch-faktencheck.git

# Branch umbenennen (falls nötig)
git branch -M main

# Push
git push -u origin main
```

---

## Sicherheits-Checks VOR dem Push

### ✅ Secrets-Check

```bash
# Suche nach API-Keys in staged files
git diff --cached | grep -i "api.*key"
git diff --cached | grep -E "(sk-ant|pplx-|pa-)"

# Falls etwas gefunden wird: SOFORT STOPPEN!
```

### ✅ Daten-Check

```bash
# Prüfe, welche CSV-Dateien committed werden
git ls-files | grep "\.csv"

# Es sollten KEINE Daten-CSVs committed werden!
# Nur claims_sample.csv (falls vorhanden) ist OK
```

### ✅ .gitignore funktioniert

```bash
# Zeige ignorierte Dateien
git status --ignored

# Sollte zeigen:
# - venv_extraction/
# - *.csv (außer whitelisted)
# - *.pkl
# - .env
```

---

## Nach dem Upload

### README auf GitHub prüfen

1. Gehe zu `https://github.com/USERNAME/ki-milch-faktencheck`
2. Prüfe, dass README.md korrekt rendert
3. Prüfe, dass **KEINE Secrets** sichtbar sind

### Kollaboratoren einladen (optional)

```bash
# Via GitHub Web UI:
# Settings → Collaborators → Add people

# Oder via CLI:
gh repo invite-user USERNAME --repo ki-milch-faktencheck
```

---

## Was ist NICHT auf GitHub?

Folgende Dateien/Ordner sind in `.gitignore` und **nicht** auf GitHub:

### Secrets
- `.env` (echte API-Keys)
- `*.key` Files
- `credentials/`

### Daten
- `Responses-*.csv` (AI-Antworten, ~50 MB)
- `claims_raw.csv` (19k extrahierte Claims)
- `claims_canonical.csv` (1k deduplizierte Claims)
- `claims_factchecked*.csv` (Ergebnisse)
- `claims_*.csv` (alle anderen Daten-CSVs)

### Cache & Temp
- `embeddings_cache.pkl` (~100 MB)
- `venv_extraction/` (Virtual Environment)
- `*.log`, `*.jsonl` (Log-Dateien)

### System
- `.DS_Store` (macOS)
- `__pycache__/` (Python Cache)

---

## Was IST auf GitHub?

### Code (Python-Scripts)
- `run_extraction_v2.py`
- `dedup_claims.py`
- `run_factcheck_v2.py`
- `run_factcheck_v3.py`
- Alle anderen `.py` Files

### Dokumentation
- `README.md`
- `ARCHITEKTUR.md`
- `ENTWICKLER_DEEP_DIVE.md`
- `QUICK_START_TILL.md`
- `RESULTS_SUMMARY_MONTAG.md`
- `FACTCHECK_V2_VERGLEICH.md`

### Config-Templates
- `.env.example` (Template OHNE echte Keys)
- `requirements.txt` (Dependencies)
- `.gitignore` (Ignore-Rules)
- `LICENSE` (MIT License)

---

## Troubleshooting

### Problem: "Secrets wurden committed!"

**SOFORT:**
```bash
# Commit zurücksetzen (lokal)
git reset HEAD~1

# Datei aus Staging entfernen
git reset HEAD path/to/file_with_secret

# Secrets entfernen, dann erneut committen
```

**Falls schon gepusht:**
```bash
# Repo löschen & neu erstellen (einfachste Methode)
# ODER: git-filter-repo verwenden (kompliziert)
```

### Problem: "Große Dateien wurden committed"

```bash
# Falls CSV-Dateien versehentlich committed
git rm --cached claims_factchecked_v2_full.csv
git commit -m "Remove data files from tracking"
```

### Problem: ".gitignore wirkt nicht"

```bash
# Falls Dateien vorher schon tracked wurden
git rm --cached -r .
git add .
git commit -m "Fix .gitignore"
```

---

## Repository-Settings (empfohlen)

Nach dem ersten Push auf GitHub:

1. **Branch Protection** (Settings → Branches):
   - ✅ Require pull request reviews before merging
   - ✅ Require status checks to pass

2. **Secrets Management** (Settings → Secrets):
   - Füge API-Keys als Repository Secrets hinzu
   - Für GitHub Actions (falls gewünscht)

3. **README Badges** (optional):
   ```markdown
   ![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
   ![License](https://img.shields.io/badge/license-MIT-green.svg)
   ```

---

## Nächste Schritte

1. ✅ Secrets-Check durchführen
2. ✅ Ersten Commit erstellen
3. ✅ GitHub Repo erstellen
4. ✅ Push
5. ✅ README auf GitHub prüfen
6. Optional: Till als Collaborator einladen
7. Optional: GitHub Actions für Tests einrichten

---

**Viel Erfolg beim Upload! Bei Fragen: drjakobvicari@gmail.com**
