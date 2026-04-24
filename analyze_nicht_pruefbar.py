"""
KI-Produkt-Faktencheck · Analyse "NICHT_PRÜFBAR" Claims

Analysiert die Gründe für nicht prüfbare Claims und gibt Empfehlungen.
"""

import pandas as pd
import sys
from collections import Counter

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "claims_factchecked.csv"

    print(f"Analysiere {input_file}...\n")

    df = pd.read_csv(input_file, sep=";")

    # Gesamt-Statistik
    total = len(df)
    nicht_pruefbar = df[df["bewertung"] == "NICHT_PRÜFBAR"]
    n_np = len(nicht_pruefbar)

    print("="*70)
    print("NICHT_PRÜFBAR ANALYSE")
    print("="*70)
    print(f"Gesamt Claims: {total}")
    print(f"NICHT_PRÜFBAR: {n_np} ({n_np/total*100:.1f}%)")
    print()

    # Gründe-Verteilung
    if "nicht_pruefbar_grund" in df.columns:
        gruende = nicht_pruefbar["nicht_pruefbar_grund"].value_counts()

        print("GRÜNDE FÜR NICHT_PRÜFBAR:")
        print("-" * 70)
        for grund, count in gruende.items():
            if pd.notna(grund) and grund != "":
                pct = count / n_np * 100
                print(f"  {grund:20s}: {count:4d} ({pct:.1f}%)")
        print()

    # Top-10 NICHT_PRÜFBAR Claims nach Frequency
    print("TOP-10 NICHT_PRÜFBARE CLAIMS (nach Häufigkeit):")
    print("-" * 70)
    top_np = nicht_pruefbar.nlargest(10, "frequency")

    for _, row in top_np.iterrows():
        claim_short = row["canonical_text"][:80]
        grund = row.get("nicht_pruefbar_grund", "unbekannt")
        print(f"\n{row['canonical_id']}: {claim_short}...")
        print(f"  Frequency: {row['frequency']} | Grund: {grund}")
        print(f"  Begründung: {row['begründung'][:120]}...")

    print()
    print("="*70)
    print("EMPFEHLUNGEN")
    print("="*70)

    # Empfehlungen basierend auf Gründen
    if "nicht_pruefbar_grund" in df.columns:
        gruende_dict = dict(gruende)

        if gruende_dict.get("technisch", 0) > n_np * 0.3:
            print("⚠️  >30% 'technisch' → Perplexity-Retry-Mechanismus verbessern")

        if gruende_dict.get("zu_vage", 0) > n_np * 0.2:
            print("⚠️  >20% 'zu_vage' → Claims präziser formulieren (Claim-Extraktion verbessern)")

        if gruende_dict.get("keine_quellen", 0) > n_np * 0.2:
            print("⚠️  >20% 'keine_quellen' → Alternative Suchquellen einbinden (Google Scholar, PubMed)")

        if gruende_dict.get("historisch", 0) > 10:
            print(f"⚠️  {gruende_dict.get('historisch')} historische Claims → Archiv-Datenbanken nutzen")

    # Prüfbare Claims - Accuracy
    pruefbar = df[df["bewertung"] != "NICHT_PRÜFBAR"]
    if len(pruefbar) > 0:
        richtig = len(pruefbar[pruefbar["bewertung"].isin(["RICHTIG", "WEITGEHEND_RICHTIG"])])
        acc = richtig / len(pruefbar) * 100

        print(f"\n✅ ACCURACY (prüfbare Claims): {acc:.1f}% ({richtig}/{len(pruefbar)})")

if __name__ == "__main__":
    main()
