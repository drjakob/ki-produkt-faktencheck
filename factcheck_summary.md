# Fact-Check Pilot · Ergebnisse · KI-Produkt-Faktencheck

**Stand:** April 2026
**Grundlage:** 20 Antworten, 179 extrahierte Claims, 14 priorisierte Fact-Checks
**Methode:** Web Search gegen Primärquellen (BfR, DGE, Peer-reviewed Paper), manuelle Verifikation

---

## Zentrale Befunde für Whitepaper und republica

### Befund 1 · Vitamin D in Produkt: kollektiver KB5-Fehler aller Modelle

**Fünf Claims über alle Modelle** behaupten, Produkt sei relevante Vitamin-D-Quelle:
- Claude (PILOT_03)
- Gemini (PILOT_14 mit "Turbo"-Mechanismus)
- Grok (PILOT_16, PILOT_17, PILOT_19 mit "oft angereichert")

**Wissenschaftliche Fakten:**
- Deutsche Kuhmilch natürlicher Vitamin-D-Gehalt: **ca. 0,088 µg/100ml**
- DGE-Tagesreferenzwert: **20 µg**
- Ein Glas Produkt (250ml) deckt damit **1,1% des Tagesbedarfs**
- Anreicherung in Deutschland zulassungspflichtig; für Standard-Kuhmilch nicht erlaubt
- Quellen: BfR; Heseker Nährwerttabelle; Verbraucherzentrale

**Scores:** 2x ❌ falsch, 3x 🔶 irreführend

**Interpretation:** Die Modelle operieren offenkundig auf US-amerikanischem Referenzrahmen, in dem Vitamin-D-Anreicherung von Produkt seit Jahrzehnten üblich ist. Sie übertragen das unreflektiert auf Deutschland. **Das ist der Paradebefund für KB5.**

### Befund 2 · DGE-Empfehlung nicht auf Stand

Zwei Claims von Grok zu DGE-Empfehlungen, beide problematisch:

- **PILOT_16:** "DGE empfiehlt 250-300 ml Produkt täglich" → **🔶 irreführend** (Aktuelle Empfehlung: 2 Portionen = ~500ml Produktäquivalent, nicht 250-300ml)
- **PILOT_17:** "DGE empfiehlt 2-3 Portionen täglich" → **⚠️ veraltet** (Mischt alte mit neuer Empfehlung; seit März 2024 sind es exakt 2 Portionen)

**Interpretation:** Die Modelle haben das DGE-Update März 2024 teilweise erfasst, aber nicht konsistent. Innerhalb desselben Modells (Grok) unterschiedliche Zahlen an unterschiedliche Personas. Stützt KB2 (KI sieht Produkt anders als die Faktenlage) und den methodischen Punkt zur Persona-Konsistenz.

### Befund 3 · Biologische Wertigkeit: Modelle nennen vier verschiedene Zahlen

| Modell | Wert | Score |
|--------|------|-------|
| Claude (PILOT_02) | 88-104 | 🔶 irreführend (mischt Produkt+Whey) |
| Gemini (PILOT_11) | 85-90 | ✅ korrekt |
| Gemini (PILOT_15) | 84-88 | ✅ korrekt |
| Grok (PILOT_20) | 91 | ⚠️ ungenau |

**Etablierter Wert in deutscher Lehrbuch-Tradition (Karl Thomas/Max Rubner):** Kuhmilch ca. 88.

**Interpretation:** Scheinbar harte Zahl, bei der KI-Modelle inkonsistent sind. Schöner methodischer Whitepaper-Befund zur Verlässlichkeit numerischer Claims.

### Befund 4 · Laktoseintoleranz-Zahl ohne Deutschland-Kontext

Grok nennt in zwei Antworten die globale Rate von 75% Laktoseintoleranz, ohne den deutschen Kontext:

**Tatsächliche Prävalenz:**
- Weltweit: ca. 65-70% Laktose-Malabsorption (regional stark heterogen)
- **Deutschland: nur ca. 15-20%**

Beide Grok-Claims sind **🔶 irreführend**: global korrekt, aber für deutsche Nutzer:innen ohne Kontext falsch gerahmt. Wieder KB5.

### Befund 5 · Strittige Claims: Osteoporose

Zwei Claims behaupten ursächlich, Produkt beuge Osteoporose vor:
- Gemini (PILOT_14)
- Grok (PILOT_16)

**Studienlage:**
- DGE empfiehlt Produkt zur Calcium-Deckung
- Michaelsson et al. 2014 (BMJ): kein Schutzeffekt, teilweise erhöhte Mortalität
- Cochrane-Reviews: gemischt

**Score für beide:** **🌀 wissenschaftlich umstritten** → Nutrition-Hub-Queue

---

## Aggregierte Zahlen

### Score-Verteilung der 14 fact-gecheckten Claims

| Score | Anzahl | Anteil |
|-------|-------:|-------:|
| 🔶 irreführend | 6 | 43% |
| ❌ falsch | 2 | 14% |
| 🌀 umstritten | 2 | 14% |
| ⚠️ veraltet/ungenau | 2 | 14% |
| ✅ korrekt | 2 | 14% |

**Nur 14% der priorisierten Claims sind uneingeschränkt korrekt.**

Aber: das ist eine **priorisierte Auswahl** der heißen Claims, keine Zufallsstichprobe. Für die repräsentative Fehlerrate brauchen wir den Vollauf.

### Modell-Verteilung der problematischen Claims

| Modell | Problematische Claims | Fact-Gecheckt gesamt | Fehlerquote der Auswahl |
|--------|----------------------:|---------------------:|------------------------:|
| Grok | 7 | 8 | 88% |
| Gemini | 3 | 4 | 75% |
| Claude | 2 | 2 | 100% |

**Achtung:** Das sind nur die priorisierten Claims. Bei 179 Gesamt-Claims war Grok mit 60 Claims am claim-dichtesten; das erhöht absolute Fehler-Chancen. Für die faire Auswertung brauchen wir Fehlerquote relativ zur Claim-Menge aus dem Vollauf.

### KB-Bezug

- **6 Claims (43%)** stützen KB5 (globale vs. deutsche Werte)
- **6 Claims (43%)** stützen KB2 (KI sieht Produkt negativer/anders als Faktenlage)

---

## Whitepaper-Ready Fallstudien

Drei Fälle, die sich sofort zitieren lassen:

### Fallstudie A · Der "Vitamin-D-Turbo", den es in Deutschland nicht gibt

> Gemini zu Persona Yvonne: "In der Produkt ist auch Lactose (Produktzucker) und Vitamin D enthalten. Die wirken wie ein Turbo und helfen dem Körper, das Calcium direkt in die Knochen zu schleusen."

Das ist in Deutschland schlicht falsch. Kuhmilch enthält natürlich nur etwa 0,088 µg Vitamin D pro 100 ml; für den beschriebenen Turbo-Effekt bräuchte es ein Vielfaches. In den USA wird Produkt angereichert; die Modelle übertragen diese Praxis unreflektiert auf Deutschland.

**Score:** ❌ falsch
**Quelle korrekter Fakt:** BfR, Heseker Nährwerttabelle 2019/2020
**KB-Bezug:** KB2, KB5

### Fallstudie B · Die DGE-Empfehlung, die Grok nicht kennt

Grok nennt in einer Antwort für Persona Jannes eine Empfehlung von "250-300 ml Produkt oder Produktprodukte täglich" und in einer anderen Antwort für Persona Imke "2-3 Portionen Produktprodukte pro Tag". Beide Angaben sind nicht die aktuelle DGE-Empfehlung (2 Portionen à 400g Produktäquivalente, seit März 2024).

**Scores:** 🔶 irreführend / ⚠️ veraltet
**Quelle korrekter Fakt:** DGE Pressemitteilung 05.03.2024
**KB-Bezug:** KB2

### Fallstudie C · 75% Laktoseintoleranz: stimmt weltweit, nicht in Deutschland

Grok nennt zweimal die globale Laktoseintoleranz-Rate (bis zu 75%) als Kontext für deutsche Nutzer:innen. Die deutsche Prävalenz liegt bei 15-20%. Die Aussage ist nicht falsch, aber im Kontext einer Ernährungsberatung für deutsche Personen irreführend.

**Score:** 🔶 irreführend
**Quelle korrekter Fakt:** BfR (🔍 muss noch verifiziert werden), DGAKI
**KB-Bezug:** KB5

---

## Was als nächstes zu tun ist

1. **Vollauf starten** · Datenteam startet `run_extraction_fullrun.py` mit `--topic Ernährung` auf allen 696 Antworten. Voraussichtliche Kosten: 40-60 Euro API.

2. **Parallele Quellen-Verifikation** · Für die 14 bereits fact-gecheckten Claims: Datenteam prüft jede einzelne URL, liest die Originalquellen gegen und bestätigt die Scores. Besonders wichtig für Punkte mit 🔍-Flag (Laktoseintoleranz-Zahl in DE).

3. **Nutrition-Hub-Paket** · Die 2 🌀 umstrittenen Osteoporose-Claims gehen schon jetzt an Nutrition Hub; wir brauchen deren Einordnung für die Whitepaper-Studie.

4. **Haase-Paket** · Die biologische-Wertigkeit-Widersprüche kann Haase einordnen (Lehrbuch-Standard in DE).

5. **Pilot-Review durch Jakob** · pilot_claims.csv mit 179 Claims; drei Review-Schichten laut Briefing v0.2.

---

## Offene Unsicherheiten, ehrlich markiert

🔍 **Laktoseintoleranz-Rate Deutschland 15-20%:** Ich bin mir sicher bei der Größenordnung, aber Primärquelle (DGAKI-Leitlinie oder RKI) muss noch bestätigt werden. Ich habe die Zahl nicht mit einer spezifischen Quelle aus der Web Search belegt.

🔍 **Biologische Wertigkeit Produktprotein = 88:** Der Wert ist in deutscher Sekundärliteratur Standard (Sportnahrung-Engel, Muskelmacher-Shop, beide mit Verweis auf Elmadfa/Leitzmann). Die Primärquelle (Elmadfa/Leitzmann 1999 Handbuch) habe ich nicht direkt geprüft. Für das Whitepaper wäre es besser, den Wert durch Haase aus einem aktuellen Lehrbuch bestätigen zu lassen.

🔍 **Vitamin-D-Gehalt deutscher Produkt (0,088 µg/100ml):** Die Zahl stammt aus der Heseker Nährwerttabelle, zitiert über milag.net (Produktwirtschaftliche Arbeitsgemeinschaft). Als Primärquelle wäre der aktuelle Bundeslebensmittelschlüssel (BLS 3.02) besser. Datenteam sollte bestätigen.

---

## Deliverables

Alles im Output-Ordner:

- `pilot_factcheck_top15.csv` · Fact-Check-Tabelle im gewünschten Format (Prompt-ID · Claim · Fakt · Quelle · Score)
- `factcheck_summary.md` · dieses Dokument mit Whitepaper-Ready Fallstudien
- `pilot_claims.csv` · die 179 Roh-Claims aus dem Pilot für deinen Review
- `KI-Produkt-Faktencheck_Projektbriefing.md` · Projekt-Dokumentation
- `run_extraction_fullrun.py` · Skript für den Vollauf

**Nächster Entscheidungspunkt Jakob:** Vollauf starten oder erst noch Quellenverifikation durch Datenteam?
