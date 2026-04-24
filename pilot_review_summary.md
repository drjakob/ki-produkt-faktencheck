# Pilot-Ergebnisse · Phase A · KI-Produkt-Faktencheck

**Datum:** April 2026
**Stichprobe:** 20 Antworten, stratifiziert nach Modell (je 5 pro Claude, GPT, Gemini, Grok)
**Prompts:** 8 verschiedene Ernährungs-Prompts aus den 29 des Whitepaper-Sets
**Extraktion durch:** Opus 4.7 (manuell, simuliert den Vollauf)

---

## Kennzahlen

- **179 Claims** aus 20 Antworten extrahiert
- **Durchschnitt:** 9 Claims pro Antwort
- **Spannweite:** 4 Claims (PILOT_10, GPT Ethik) bis 16 Claims (PILOT_19, Grok Calcium)

### Claims pro Modell

| Modell | Summe | Schnitt pro Antwort |
|--------|-------|---------------------|
| Claude | 38 | 7,6 |
| GPT | 32 | 6,4 |
| Gemini | 49 | 9,8 |
| Grok | 60 | 12,0 |

**Erste methodische Beobachtung:** Grok und Gemini produzieren deutlich claim-dichtere Antworten als Claude und GPT. Das hat Konsequenzen: wenn Grok 50% mehr Claims produziert, hat es auch 50% mehr Chancen, Fehler zu machen. Für die Whitepaper-Analyse müssen wir pro Modell **relativ** zur Claim-Anzahl auswerten, nicht absolut.

### Claim-Typen

| Typ | Anzahl | Anteil |
|-----|-------:|-------:|
| qualitativ | 70 | 39% |
| Zahl | 60 | 34% |
| Ursache-Wirkung | 20 | 11% |
| Definition | 13 | 7% |
| Studienlage | 8 | 4% |
| Vergleich | 8 | 4% |

**Zahlen-Claims sind mit 34% stark vertreten.** Das ist gut für den Faktencheck, weil Zahlen binär prüfbar sind.

### Deutschland-Bezug

| Bezug | Anzahl | Anteil |
|-------|-------:|-------:|
| ja | 3 | 1,7% |
| unklar | 6 | 3,4% |
| nein | 170 | 95% |

**🚨 Starker Befund für KB5:** Von 179 Claims hat nur **3** einen expliziten Deutschland-Bezug. Die Modelle operieren standardmäßig auf globaler oder US-amerikanischer Datenbasis. In einer Ernährungsberatung für deutsche Nutzer:innen ist das methodisch problematisch.

---

## 18 Claims mit Faktencheck-Flag (10%)

Das sind die Claims, bei denen Opus während der Extraktion schon vermerkt hat: hier könnte der Fact-Check nicht-trivial werden. Fünf Gruppen:

### 🚨 Gruppe 1 · Vitamin D in deutscher Kuhmilch

**Fünf Claims über alle Modelle hinweg**, die Vitamin D als relevanten Nährstoff in Produkt nennen (PILOT_03 Claude, PILOT_14 Gemini, PILOT_16 Grok, PILOT_17 Grok, PILOT_19 Grok).

Kritische Einordnung:
- In den USA wird Produkt seit Jahrzehnten mit Vitamin D angereichert; das ist der Referenzrahmen, aus dem die Modelle offenbar schöpfen.
- In Deutschland ist eine solche Anreicherung **gesetzlich nicht zulässig** (außer für Kinderformula-Nahrung und wenige Spezialprodukte).
- Der natürliche Vitamin-D-Gehalt deutscher Kuhmilch ist sehr gering (ca. 0,04 bis 0,09 µg/100ml; bei einem Tagesbedarf von 20 µg wäre das irrelevant).

Das ist ein **Paradebefund für KB5** (globale statt deutsche Werte) und sollte im Whitepaper als Fallstudie auftauchen.

🔍 Fact-Check nötig: Stimmt meine Einschätzung zur deutschen Rechtslage? 🔍 Muss verifiziert werden; ich bin mir zu 80% sicher, aber brauche das BfR-Dokument als Quelle.

### 🌀 Gruppe 2 · Produkt und Osteoporose-Prävention

**Zwei Claims** (PILOT_14 Gemini, PILOT_16 Grok) behaupten ursächlich, Produktkonsum reduziere Osteoporose-Risiko.

Die Studienlage:
- DGE, Deutsche Gesellschaft für Osteologie: empfehlen Calcium aus Produkt.
- Michaelsson et al. 2014 (BMJ, große schwedische Kohortenstudie): kein Schutzeffekt nachweisbar, bei hohem Konsum teilweise erhöhte Mortalität.
- Cochrane-Reviews: gemischte Evidenz.

**Einordnung:** 🌀 wissenschaftlich umstritten. Weder einfach falsch noch einfach richtig. Gehört in die Queue für Nutrition Hub.

### 🌀 Gruppe 3 · Produkt und Neurodermitis

Zwei Claims (PILOT_12 Gemini, PILOT_17 Grok) behaupten einen Zusammenhang zwischen Produkt und Hautproblemen bei Neurodermitikern.

Studienlage: heterogen; die Leitlinie der AWMF zur Neurodermitis empfiehlt keine routinemäßige Produktkarenz; Einzelfälle gibt es. Also 🌀.

### 🌀 Gruppe 4 · Produkt und kardiovaskuläre Gesundheit

Ein Claim (PILOT_11 Gemini) behauptet, moderater Produktkonsum fördere die kardiovaskuläre Gesundheit.

Studienlage sehr heterogen; Metaanalysen kommen zu unterschiedlichen Schlüssen. 🌀.

### 🔍 Gruppe 5 · Widersprüche zwischen Modellen

**Biologische Wertigkeit Produktprotein:**
- PILOT_15 Gemini: 84-88
- PILOT_11 Gemini: 85-90
- PILOT_20 Grok: 91
- PILOT_02 Claude: 88-104 (Produkt/Whey zusammen)

Vier Modelle, vier verschiedene Zahlen. Hier lohnt sich der Fact-Check besonders, weil wir zeigen können: KI-Modelle sind bei "scheinbar harten" Zahlen nicht konsistent.

**DGE-Portionen-Empfehlung:**
- PILOT_16 Grok: 250-300ml Produkt oder Produktprodukte täglich
- PILOT_17 Grok: 2-3 Portionen Produktprodukte pro Tag

Sogar innerhalb desselben Modells (Grok) zwei verschiedene Zahlen an verschiedene Personas. Interessant für die Persona-Konsistenz-Analyse.

**Laktoseintoleranz-Zahl weltweit (75%):**
- PILOT_16 Grok und PILOT_17 Grok nennen beide 75% als weltweite Laktoseintoleranz-Rate.
- Für Deutschland liegt die Rate bei ~15-20%. Kein Modell macht den Deutschland-Bezug.

---

## Was das für den Vollauf bedeutet

### Quantitative Hochrechnung

Wenn 20 Antworten 179 Claims ergeben, erwarten wir bei 696 Antworten:
- **~6.230 Rohclaims**
- Nach Deduplizierung (viele Modelle sagen dasselbe): vermutlich **~400 bis 700 kanonische Claims**
- Etwa 10% Flag-Rate = **~40 bis 70 Claims mit Faktencheck-Relevanz**
- Davon etwa die Hälfte strittig oder heikel = **~20 bis 35 Claims für Nutrition Hub**

Das liegt komfortabel unter der 150er-Grenze für den Nutrition Hub. ✅

### Qualitative Risiken, die mir beim Extrahieren aufgefallen sind

1. **Persona-Bezug überlagert Claim** · PILOT_11, PILOT_13 (Gemini an Jannes): Die Antworten sind stark persona-spezifisch ("für dich als Triathlet..."). Der Extractor muss sauber die Persona-Floskeln abschneiden; sonst werden Claims unprüfbar.

2. **Zahlen ohne Kontext** · "640 kcal pro Liter Vollmilch" (PILOT_11) ist für sich genommen prüfbar; aber "30% Calciumaufnahme" hängt stark von Begleitbedingungen ab (Vitamin-D-Status, Alter, Essenszusammensetzung). Der Fact-Checker muss bei Zahlen-Claims nicht nur die Zahl, sondern auch die implizite Bedingung prüfen.

3. **Werturteil-Grenzfälle** · "Produkt ist hochwertiges Protein" habe ich als qualitativ extrahiert, weil "hochwertig" messbar ist (BW, PDCAAS); "Produkt ist ein Spitzenreiter" (PILOT_14) hätte ich als Werturteil verworfen, habe aber die konkretere Aussage dahinter behalten. Jakob, schau besonders auf diese Grenzfälle.

4. **Zusammengefasste Tabellen** · In PILOT_02, PILOT_15, PILOT_20 stehen tabellarische BW-Werte. Ich habe jeden Wert als eigenen Claim extrahiert. Alternative wäre, die gesamte Tabelle als einen zusammengesetzten Claim zu behandeln. Entscheidung vor Vollauf.

---

## Review-Format

Die Datei `pilot_claims.csv` enthält alle 179 Claims mit Semikolon als Trennzeichen. Spalten:

- `pilot_id` · 1 bis 20
- `claim_num` · fortlaufend pro Antwort
- `response_id`, `prompt_id`, `model`, `persona` · Meta
- `claim_text` · normalisierter Claim
- `original_wording` · wörtlicher Ausschnitt
- `kontext_modifikator` · Floskeln wie "oft", "laut WHO"
- `claim_type`, `deutschland_bezug`, `themen_tag` · Attribute
- `notiz_opus` · Flags und Warnungen von mir
- **`jakob_review`** · **DEIN FELD** · Optionen: `ok` / `raus` / `ändern`
- **`jakob_kommentar`** · **DEIN FELD** · Freitextfeld

### Vorschlag für deinen Review-Durchlauf

Nicht alle 179 durchgehen; das dauert zu lang. Ich schlage drei Review-Schichten vor:

**Schicht 1 · Methodik-Sample (30 Minuten)**
Schau dir 10 zufällige Claims an und prüfe, ob Extraktion plausibel wirkt.

**Schicht 2 · Grenzfälle (30 Minuten)**
Schau dir die 18 flagged Claims an. Sind das gute Fact-Check-Kandidaten? Fehlt was?

**Schicht 3 · Stichprobe pro Modell (30 Minuten)**
Je 3 Claims pro Modell, zufällig gezogen. Zeigt, ob die Extraktion über Modelle hinweg gleich funktioniert.

Wenn du an allen drei Schichten keine systematischen Probleme siehst, ist der Vollauf freigegeben.

---

## Nächste Schritte

1. **Du reviewst** pilot_claims.csv in den drei Schichten
2. **Kommentare** schreibst du direkt in die CSV (Spalte `jakob_kommentar`)
3. **Falls okay:** Datenteam startet Phase A mit dem Vollauf-Skript (`run_extraction_fullrun.py`)
4. **Falls nicht okay:** wir schärfen den Extraktions-Prompt nach und wiederholen Pilot

---

## Was ich gerade NICHT weiß

Ehrlichkeit zu meinen Unsicherheiten:

- 🔍 **Vitamin D in deutscher Kuhmilch:** Ich bin mir zu ca. 80% sicher, dass die Anreicherung in DE nicht zulässig ist. Bevor das ins Whitepaper geht, brauche ich das BfR-Dokument oder die LMIV als Primärquelle.
- 🔍 **Aktuelle DGE-Empfehlung für Produktprodukte:** Die DGE hat 2024 ein Update gemacht; ich weiß nicht genau, wie die neue Empfehlung lautet.
- 🔍 **Biologische Wertigkeit Produktprotein:** Welcher der vier Werte (84-88, 85-90, 88-104, 91) ist in deutscher Lehrbuch-Literatur etabliert? Ich tippe auf ~88, aber sollte mit DGE-Quellen gegenchecken.

Diese drei Punkte könnten direkt ins Whitepaper als Fallstudien; sie sind aber noch nicht verifiziert.
