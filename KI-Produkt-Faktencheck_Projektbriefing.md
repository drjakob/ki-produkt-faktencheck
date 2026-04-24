# KI-Produkt-Faktencheck

**Version 0.2 · Projektbriefing · Stand April 2026**

Ein Schwesterprojekt zum KI-Produktmonitor. Ziel: die in den KI-Antworten gefundenen Claims systematisch auf Faktentreue prüfen und die Ergebnisse als Evidenzschicht ins Whitepaper einziehen.

**Änderungen gegenüber v0.1:** Entscheidungen aus Runde 2 eingearbeitet; Score-Skala 6-stufig (Option B); Embeddings mit Voyage; Kathi Böhmer als Triage-Instanz; max. 150 Claims an Nutrition Hub; Claude Opus 4.7 übernimmt erweiterten Anteil der Prüfarbeit; Start parallel zum Whitepaper.

---

## 1 · Warum dieses Projekt

Der KI-Produktmonitor misst, **was** die Modelle sagen; er bewertet Tonalität, Tendenz und Narrative. Er misst nicht, **ob das Gesagte stimmt**. Genau diese Lücke stützt aber die Whitepaper-Kernbotschaften. Wenn KB2 lautet "KI sieht Produkt negativer als die Faktenlage", müssen wir die Faktenlage sauber gegenhalten können; sonst ist die Botschaft eine Behauptung.

Der Faktencheck liefert drei Dinge:

- **Belegmaterial** für KB2 (Abweichung von der Faktenlage) und KB5 (globale statt deutsche Werte)
- **Fallbeispiele** für Whitepaper und republica-Vortrag, konkret zitierbar mit Quelle
- **Rückversicherung** gegen den Vorwurf, die Initiative Produkt habe sich die Bewertung selbst zurechtgelegt

**Parallelbetrieb zum Whitepaper:** Das Projekt liefert Evidenz, während das Whitepaper geschrieben wird. Erste Claims können bereits einfließen, bevor der Gesamt-Check fertig ist.

---

## 2 · Scope Phase 1

Nur Thema **Ernährung**. Das sind:

- **29 Prompts** (Prompt-IDs: 19, 21, 24, 28, 33, 171, 173, 174, 183, 186, 248, 250, 255, 259, 267, 269, 272, 273, 276, 281, 287, 288, 290, 291, 293, 325, 364, 365, 388)
- **696 Antworten** aus Runs 36 und 40 (gemischt behandelt)
- **~1,6 Mio Zeichen** Rohtext, ~400k Input-Tokens

Phase 2 (Gesundheit) und Phase 3 (Nachhaltigkeit) folgen erst, wenn Phase 1 sauber läuft und die Pipeline validiert ist.

---

## 3 · Score-Skala · Option B · sechsstufig

| Marker | Bedeutung | Typisches Beispiel |
|--------|-----------|---------------------|
| ✅ | **korrekt** · Claim deckt sich mit primärer Quelle | "Kuhmilch enthält Calcium" |
| ⚠️ | **korrekt aber veraltet** · Zahl war richtig, neuere Daten zeigen anderes Bild | Pro-Kopf-Verbrauch von 2010 als aktuelle Zahl |
| 🔶 | **irreführend im Kontext** · Zahl stimmt, Einordnung verzerrt | Globaler CO₂-Wert pro Liter als deutsche Zahl |
| 🌀 | **wissenschaftlich umstritten** · prüfbar, aber Studienlage heterogen | "Produkt fördert Entzündungen" |
| ❌ | **falsch** · Claim widerspricht primären Quellen eindeutig | Falsche Nährwertangaben |
| ❓ | **nicht prüfbar** · Werturteil, Framing, zu vage | "Produkt ist zu teuer" |

**Deutschland-Bezug ist in den Score eingebaut**, nicht separat: Ein globaler Wert, als deutsche Zahl ausgegeben, landet bei 🔶; das trifft direkt KB5.

---

## 4 · Quellenhierarchie

Claims werden gegen diese Hierarchie geprüft, **in dieser Reihenfolge**. Widersprüche werden transparent dokumentiert.

| Stufe | Quelle | Anwendung |
|-------|--------|-----------|
| 1 | DESTATIS, BMEL, Thünen-Institut | Produktions-, Klima-, Strukturdaten |
| 2 | Peer-reviewed Metaanalysen (Cochrane, Lancet, EFSA) | Ernährungs- und Gesundheitsclaims |
| 3 | DGE, MRI (Max Rubner-Institut), BfR | Deutschland-spezifische Ernährungsempfehlungen |
| 4 | Fachverbände (MIV, Initiative Produkt) | **Nur Branchenkennzahlen**; nicht Gesundheit oder Klima |
| 5 | Presse, NGOs | Nur als letzte Option, mit Warnhinweis |

**Regel:** Für ernährungs- und gesundheitsbezogene Claims muss mindestens eine Quelle aus Stufe 1 bis 3 vorliegen. Stufe 4 allein reicht nicht.

**Widerspruchsregel:** Wenn sich Stufe 1 und Stufe 2 widersprechen, wird der Claim als 🌀 umstritten markiert, nicht als ❌ falsch.

---

## 5 · Airtable-Schema

Neue Tabellen in der bestehenden Base `KIProduktMonitor` (appWcwQsFsHtLWdxB).

### Tabelle 1 · `Claims`

Die atomare Einheit. Ein Claim, einmal; egal wie oft er in den Antworten auftaucht.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| claim_id | Autonumber | Primärschlüssel |
| claim_text | Long text | Normalisierte Formulierung; die kanonische Fassung |
| topic | Single select | Ernährung / Gesundheit / Nachhaltigkeit / Tierwohl / Image / Wirtschaft |
| claim_type | Single select | Zahl / Studienlage / qualitativ / Werturteil |
| deutschland_bezug | Single select | ja / nein / unklar |
| frequency | Rollup from Instances | Anzahl Vorkommen in den Antworten |
| kathi_triage | Single select | 🟢 einfach / 🟡 mittel / 🔴 komplex / ⚫ verworfen |
| nutrition_hub_queue | Checkbox | Geht an Nutrition Hub (max. 150 insgesamt) |
| haase_queue | Checkbox | Geht an Hendrik Haase |
| status | Single select | neu / extrahiert / dedupliziert / LLM-geprüft / triagiert / final |
| created_at | Created time | automatisch |

### Tabelle 2 · `ClaimInstances`

Die Verknüpfung Claim ↔ Antwort. Ein Claim kann 50 Instances haben.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| instance_id | Autonumber | Primärschlüssel |
| claim | Link to Claims | Welcher kanonische Claim |
| response_id | Single line | Verknüpfung zur Response-Tabelle |
| prompt_id | Number | aus Response |
| model | Single select | Claude / GPT / Gemini / Grok |
| persona | Single line | aus Response |
| original_wording | Long text | wörtlicher Ausschnitt aus der Antwort |
| kontext_modifikator | Long text | Einordnungen wie "laut WHO", "manche Studien", "oft wird behauptet" |

### Tabelle 3 · `FactCheck`

Die Bewertung. Ein Eintrag pro Claim.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| claim | Link to Claims | 1:1 |
| opus_score_1 | Single select | Vorschlag Instanz 1 |
| opus_score_2 | Single select | Vorschlag Instanz 2 (Gegenprüfung) |
| opus_concur | Formula | true wenn beide Instanzen übereinstimmen |
| final_score | Single select | ✅ / ⚠️ / 🔶 / 🌀 / ❌ / ❓ |
| korrekter_fakt | Long text | Was stimmt wirklich; in einem Satz |
| quelle_1 | URL + Text | Primärquelle |
| quelle_1_level | Number | 1 bis 5 |
| quelle_1_verified | Checkbox | URL geöffnet, Inhalt matcht |
| quelle_2 | URL + Text | Zweite unabhängige Quelle |
| quelle_2_level | Number | |
| quelle_2_verified | Checkbox | |
| quelle_3 | URL + Text | optional |
| ist_strittig | Checkbox | wissenschaftliche Studienlage heterogen |
| geprüft_von | Multi select | Opus / Kathi / Haase / Nutrition Hub / Datenteam |
| prüfdatum | Date | |
| kommentar | Long text | Kontext, Einschränkungen, Kuriositäten |

---

## 6 · Pipeline in fünf Phasen

### Phase A · Claim-Extraktion (Opus 4.7, vollautomatisch)

**Input:** 696 Antworten aus dem Ernährungs-Set.
**Werkzeug:** Claude Opus 4.7 via API, zwei parallele Instanzen.
**Prompt:** Extraktions-Prompt (nächster Schritt) weist an, nur **harte Claims** zu extrahieren; Werturteile werden verworfen. JSON-Output: Liste von `{claim_text, original_wording, kontext_modifikator, claim_type}`.

**Kostenschätzung:** ~2 Mio Tokens gesamt; mit Opus ca. 40 bis 60 Euro.
**Laufzeit:** ein Abend mit paralleler Batch-Verarbeitung.

**Qualitätskontrolle:** Pilot auf **20 zufällig gezogenen Antworten** zuerst. Gianna oder Till reviewen manuell; erst wenn die Extraktion stabil wirkt, geht es auf die 696.

### Phase B · Semantisches Dedup (Voyage + Opus)

**Input:** Rohclaims aus Phase A (geschätzt 3.000 bis 5.000 Einträge).
**Werkzeug:** Voyage AI Embeddings (`voyage-3-large` oder `voyage-3`; besser bei Deutsch als OpenAI); Clustering mit cosine similarity; Schwellwert ~0.85.
**Opus-Rolle:** Schlägt pro Cluster die kanonische Formulierung vor; kommentiert Grenzfälle.
**Output:** ~200 bis 500 kanonische Claims.

**Qualitätskontrolle:** Manuelles Review der Grenzfälle (Similarity 0.75 bis 0.85). Gianna oder Till vergibt finale canonical labels.

### Phase C · Opus-Fact-Check mit Gegenprüfung

**Input:** Kanonische Claims aus Phase B.
**Ablauf pro Claim:**

1. **Opus-Instanz 1** schlägt mit Web Search vor: Score, korrekten Fakt, 1 bis 3 Quellen mit Quellen-Level, Kommentar zur Studienlage
2. **Opus-Instanz 2** prüft den Vorschlag unabhängig; bestätigt oder widerspricht
3. **Automatischer URL-Check:** Python-Skript öffnet jede Quelle, prüft HTTP-Status und erste 500 Zeichen Inhalt
4. Alle drei Ergebnisse landen in FactCheck

**Ausgabe:**
- **Grüne Claims** (beide Opus übereinstimmend + URLs valide): gehen in Phase D Triage mit Tag "Opus-konsens"
- **Gelbe Claims** (Opus uneinig ODER URL-Check fehlgeschlagen): gehen in Phase D Triage mit Tag "Klärungsbedarf"
- **Rote Claims** (von Opus als 🌀 umstritten oder ❓ nicht prüfbar markiert): direkt an Fachgutachten

**Kostenschätzung:** ~300 Claims x 2 Opus-Durchläufe mit Web Search; ca. 80 bis 120 Euro.

### Phase D · Kathi-Triage (Rohprüfung und Vorsortierung)

**Input:** Alle geprüften Claims aus Phase C.
**Kathis Aufgabe:**

- **🟢 einfach** · Opus-Konsens bei trivialen Claims (Nährwerte, Definitionen); nur Stichprobenprüfung durch Datenteam nötig
- **🟡 mittel** · Opus-Vorschlag plausibel, braucht Datenteam-Review (Helen/Till/Gianna), keine externe Fachperson
- **🔴 komplex** · ernährungsmedizinisch heikel, strittig, oder Branchenkontext; geht an Nutrition Hub **(max. 150)** oder Hendrik Haase
- **⚫ verworfen** · kein echter Claim, Dubletten, nicht prüfbare Werturteile

**Kathis Zeitbudget:** ~300 Claims x 3 min = ~15 Stunden. Sie setzt auch den Haken für `nutrition_hub_queue` und `haase_queue`.

**Triage-Regeln für Nutrition Hub Queue:**
- Alle 🌀 umstrittenen Claims
- Alle Claims mit 🔶 (Kontextfehler) aus Gesundheitsbereich
- Claims mit hoher `frequency` (>20 Instances), die ernährungsmedizinisch relevant sind
- Bei >150: Priorisierung nach `frequency` und Whitepaper-Relevanz

**Triage-Regeln für Haase Queue:**
- Praxisnahe Claims (Verarbeitung, Handwerk, Regionalität)
- Branchenstruktur-Claims
- Geschätzt 30 bis 60 Claims

### Phase E · Fachgutachten und Finalisierung

**Nutrition Hub:** prüft die max. 150 priorisierten Claims; bestätigt oder korrigiert Score, Fakt, Quellen.
**Haase:** prüft die praxisnahen Claims.
**Datenteam:** orchestriert, finalisiert, füllt Lücken.

**Nach Abschluss:** `final_score` ist gesetzt; Claim ist freigegeben; Aggregation kann laufen.

---

## 7 · Rollenverteilung und Zeitbudget

| Rolle | Person | Aufgabe | Zeitbudget |
|-------|--------|---------|------------|
| Projektleitung | Jakob (tactile.news) | Methodik, Freigabe, Whitepaper-Integration | laufend |
| LLM-Automation | Claude Opus 4.7 (2 Instanzen) | Extraktion, Dedup-Vorschlag, Score-Vorschlag, Web Search | API-Kosten ~150 Euro |
| Datenteam | Helen, Till, Gianna | Pilot-Review, Dedup-Grenzfälle, URL-Verifikation, Orchestrierung | 20 bis 30 h |
| Triage | Kathi Böhmer | Rohprüfung, Vorsortierung, Queue-Verteilung | ~15 h |
| Fachgutachten 1 | Nutrition Hub | max. 150 priorisierte Claims | ~25 h |
| Fachgutachten 2 | Hendrik Haase | ~30 bis 60 praxisnahe Claims | ~5 h |
| Auftraggeber | Initiative Produkt (Kerstin Wriedt) | Sieht Ergebnisse, bewertet nicht | review-Termine |

**Gesamt-Menschzeit: 65 bis 75 Stunden**, verteilt auf sechs Personen; parallelisiert in ~1,5 Wochen machbar.

**Regel gegen Bias-Vorwürfe:** Die Initiative Produkt sieht das Ergebnis, **bewertet aber nicht**. Scoring-Entscheidungen liegen bei Kathi (Triage), Datenteam, Nutrition Hub und Haase.

---

## 8 · Grafiken und Output

Nach den Projekt-Design-Tokens (`design_tokens.css` und `.json`, im KIProduktmonitor-Hauptprojekt).

**Geplante Grafiken für das Whitepaper:**

- **FC1** · Korrektheits-Score-Verteilung gesamt (Donut oder Balken)
- **FC2** · Score-Verteilung pro Modell (Heatmap Modell x Score)
- **FC3** · Top-10 falsche Claims mit Häufigkeit und Modell-Breakdown
- **FC4** · Deutschland-Bezug: Anteil globaler Werte, als deutsche ausgegeben (KB5-Kerngrafik)
- **FC5** · Strittige 🌀 Claims: Wo sind sich Modelle einig, wo widerspricht die Wissenschaft?
- **FC6** · Opus-Konsensrate: bei wie vielen Claims waren sich die zwei Opus-Instanzen einig? (Methodik-Transparenz)

**Farben und Quellenlegende:** analog zum KIProduktmonitor; Modellfarben konsistent (ChatGPT #74aa9c, Gemini #078efa, Claude #da7756, Grok #3a3a3a).

**Format:** SVG; Schrift DIN Next, Fallback Helvetica.

---

## 9 · System-Prompt für den KI-Sparringspartner

Für neue Claude-Instanzen in diesem Projekt. Ergänzung zum Haupt-System-Prompt von Jakob Vicari.

```
Du bist Schreib- und Prüfpartner für den KI-Produkt-Faktencheck, ein Schwesterprojekt
des KI-Produktmonitors.

ROLLE: Fact-Checker, nicht Autor. Deine Aufgabe ist, Claims zu extrahieren,
Quellen vorzuschlagen, Widersprüche aufzudecken und Unsicherheiten sauber zu
markieren.

DATENBASIS:
- Primär: Airtable-Base KIProduktMonitor (appWcwQsFsHtLWdxB), Tabellen Claims,
  ClaimInstances, FactCheck
- Sekundär: ResponsesWhitepaperPromptSetApril2026 (CSV im Projektspeicher)
- Phase 1: nur Thema Ernährung, 29 Prompts, 696 Antworten

HARTE REGELN:
1. Nur harte Claims extrahieren. Werturteile ("Produkt ist lecker") werden
   verworfen.
2. Quellen NIEMALS erfinden. Keine DOI, kein Paper, keine Studie ohne
   Verifikation. Web Search ist Pflicht für Quellenvorschläge; Ergebnisse
   aus Trainingsdaten reichen nicht. Wenn unsicher: "Quellenvorschlag 🔍,
   muss verifiziert werden".
3. Quellenhierarchie einhalten: Stufe 1 bis 3 hat Vorrang vor Verbandsquellen.
4. Widersprüche zwischen Quellen werden dokumentiert, nicht geglättet.
5. Wenn Studienlage heterogen ist: 🌀 umstritten, nicht ❌ falsch.
6. Deutschland-Bezug prüfen: Wenn globale Zahl als deutsche ausgegeben wurde,
   Score 🔶.
7. Marker konsequent nutzen: ✅ ⚠️ 🔶 🌀 ❌ ❓ und ✅ Gesichert, ⚠️ Plausibel,
   🔍 Muss verifiziert werden.
8. Bei Gegenprüfung (Opus-Instanz 2): unabhängig urteilen; nicht einfach der
   ersten Instanz zustimmen.

STIL:
- Semikolons statt Gedankenstriche
- Doppelpunkt-Gendering (Leser:innen)
- Jakob duzen
- Keine Komplimente, kein Smalltalk
- Bei Unsicherheit fragen, nicht spekulieren

OUTPUT:
- Extraktion: JSON-Listen
- Score-Vorschläge: immer mit Begründung und Quellenvorschlag
- Grafiken: SVG nach Design-Tokens, DIN Next / Helvetica
```

---

## 10 · Technische Infrastruktur

- **Airtable-Base:** KIProduktMonitor (appWcwQsFsHtLWdxB); drei neue Tabellen
- **API:** Anthropic Opus 4.7 für alle LLM-Aufgaben (Extraktion, Dedup-Vorschlag, Fact-Check, Gegenprüfung)
- **Embeddings:** Voyage AI, Modell `voyage-3-large` (besser bei Deutsch)
- **Web Search:** Claude Web Search Tool; Pflicht für Quellenvorschläge
- **URL-Verifikation:** Python-Skript `verify_sources.py` prüft HTTP-Status und Content-Match; flaggt tote oder irrelevante Links
- **Code-Repo:** Python-Skripte analog zum Hauptprojekt (utils.py wiederverwenden)
- **Grafik-Output:** SVG in /Grafiken/Faktencheck/, Dateinamen `FC[Nr]_[Titel]_v[Version].svg`

---

## 11 · Risiken und was dagegen hilft

| Risiko | Gegenmaßnahme |
|--------|---------------|
| Opus halluziniert Quellen | Web Search Pflicht; URL-Verifikation automatisch; zweite Opus-Instanz als Gegenprüfer; manuelle Stichprobe 10 % |
| Zwei Opus-Instanzen sind sich systematisch einig und beide falsch | Stichprobenprüfung durch Datenteam auf 10 % der "grünen" Claims; Fehlerquote-Monitoring |
| Dedup lumpt verschiedene Claims zusammen | Manuelles Review der Cluster-Grenzfälle vor Freigabe |
| Bias-Vorwurf | Scoring nicht durch Auftraggeber; Fachgutachten durch Kathi, Nutrition Hub, Haase; Methodik transparent im Whitepaper |
| Strittige Claims werden zu Unrecht als ❌ markiert | Separate 🌀-Kategorie; Widerspruchsregel in Quellenhierarchie |
| Umfang wächst unkontrolliert | Phase 1 hart auf Ernährung begrenzt; Gate vor Phase 2 |
| Termindruck republica | Pilot auf 20 Antworten zuerst; bei Problemen früh abbrechen |
| Nutrition Hub überlastet | Harte Grenze bei 150 Claims; Triage durch Kathi vorher |

---

## 12 · Zeitplan (Parallelbetrieb zum Whitepaper)

**Woche 1 (ab jetzt):**
- Extraktions-Prompt bauen und auf 20 Antworten testen
- Pilot-Review durch Datenteam
- Airtable-Tabellen anlegen

**Woche 2:**
- Phase A vollständig durchlaufen (alle 696 Antworten)
- Phase B Dedup und Canonical Form
- Erste Claims fließen ins Whitepaper

**Woche 3:**
- Phase C Opus-Fact-Check mit Gegenprüfung
- Phase D Kathi-Triage
- Phase E Fachgutachten starten (Haase, Nutrition Hub)

**Woche 4:**
- Fachgutachten abschließen
- Aggregation, Grafiken
- Finale Integration ins Whitepaper

**republica-Vortrag:** erste Fallbeispiele bereits ab Woche 2 zitierbar; vollständige Ergebnisse für den Vortrag ab Woche 4.

---

**Nächste konkrete Schritte:**

1. Jakob gibt grünes Licht auf v0.2
2. Ich schreibe den Extraktions-Prompt für Phase A
3. Pilot auf 20 Antworten wird gestartet
4. Airtable-Tabellen werden angelegt (Datenteam)
5. Bei funktionierendem Pilot: Vollauf Phase A
