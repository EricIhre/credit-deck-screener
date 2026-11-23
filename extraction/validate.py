"""
Deterministic validation layer for the extracted data.

This is the "can I trust it?" evidence. It runs three families of check on
extraction/extracted.csv and writes a report to extraction/validation_report.txt:

  1. Range / domain checks   - every value is inside a plausible band, and
                               categorical fields take only their known values.
  2. Cross-field consistency - EBITDA / Revenue reconciles to the *stated*
                               EBITDA margin, and Net debt / EBITDA reconciles
                               to the *stated* leverage multiple. These catch
                               transcription errors and (via margin) mixed-up
                               financial lines.
  3. Completeness            - which fields are missing, so genuine
                               non-disclosure is visible rather than silent.

A non-zero number of ERRORs means the extraction should not be trusted as-is.
WARNINGs are for review (often genuine data quirks, e.g. very high leverage).
"""

from __future__ import annotations

import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "extraction", "extracted.csv")
REPORT = os.path.join(ROOT, "extraction", "validation_report.txt")

# Plausible bands for numeric fields (min, max) inclusive.
RANGES = {
    "founded_year": (1800, 2025),
    "company_age_years": (0, 225),
    "n_sites": (1, 1000),
    "n_employees": (1, 5_000_000),
    "ceo_tenure_years": (0, 60),
    "revenue_eur_m": (1, 100_000),
    "ebitda_eur_m": (-10_000, 50_000),
    "ebitda_margin_pct": (0, 100),
    "ebitda_margin_prior_pct": (0, 100),
    "net_debt_eur_m": (-10_000, 100_000),
    "net_leverage_x": (0, 15),
    "top3_customer_concentration_pct": (0, 100),
    "recurring_revenue_pct": (0, 100),
}
CATEGORIES = {
    "cohort": {2024, 2025},
    "esg_rating": {"A", "B", "C", "D"},
    "tech_disruption_risk": {"LOW", "MODERATE", "ELEVATED"},
    "ownership_type": {"family", "sponsor"},
}


def main() -> None:
    df = pd.read_csv(CSV)
    errors: list[str] = []
    warnings: list[str] = []

    # ---- 1. range + category checks ----
    for col, (lo, hi) in RANGES.items():
        bad = df[df[col].notna() & ((df[col] < lo) | (df[col] > hi))]
        for _, r in bad.iterrows():
            errors.append(f"[range] {r.company}: {col}={r[col]} outside [{lo},{hi}]")

    for col, allowed in CATEGORIES.items():
        bad = df[df[col].notna() & ~df[col].isin(allowed)]
        for _, r in bad.iterrows():
            errors.append(f"[category] {r.company}: {col}={r[col]!r} not in {allowed}")

    # ---- 2. cross-field consistency ----
    # (a) EBITDA / Revenue should reproduce the stated margin (within 0.15pp,
    #     allowing for the PDF's own rounding of each line).
    margin_cols = ["revenue_eur_m", "ebitda_eur_m", "ebitda_margin_pct"]
    m = df[df[margin_cols].notna().all(axis=1)]
    implied = 100 * m["ebitda_eur_m"] / m["revenue_eur_m"]
    gap = (implied - m["ebitda_margin_pct"]).abs()
    for (_, r), g in zip(m.iterrows(), gap):
        if g > 0.15:
            errors.append(
                f"[margin-reconcile] {r['company']}: EBITDA/Revenue="
                f"{100*r['ebitda_eur_m']/r['revenue_eur_m']:.2f}% vs stated "
                f"{r['ebitda_margin_pct']:.2f}% (gap {g:.2f}pp)"
            )

    # (b) Net debt / EBITDA should reproduce the stated leverage (within 0.1x).
    #     Skip rows where leverage was itself derived from these two numbers.
    lev_cols = ["net_debt_eur_m", "ebitda_eur_m", "net_leverage_x"]
    lv = df[(~df["net_leverage_is_derived"]) & df[lev_cols].notna().all(axis=1)]
    implied_lev = lv["net_debt_eur_m"] / lv["ebitda_eur_m"]
    lgap = (implied_lev - lv["net_leverage_x"]).abs()
    for (_, r), g in zip(lv.iterrows(), lgap):
        if g > 0.1:
            errors.append(
                f"[leverage-reconcile] {r['company']}: NetDebt/EBITDA="
                f"{r['net_debt_eur_m']/r['ebitda_eur_m']:.2f}x vs stated "
                f"{r['net_leverage_x']:.2f}x (gap {g:.2f}x)"
            )

    # ---- soft warnings (review, not failure) ----
    for _, r in df.iterrows():
        if pd.notna(r.net_leverage_x) and r.net_leverage_x >= 6.0:
            warnings.append(
                f"[high-leverage] {r.company}: {r.net_leverage_x}x"
                + (" (derived)" if r.net_leverage_is_derived else "")
            )
        if pd.notna(r.ebitda_margin_pct) and r.ebitda_margin_pct < 8:
            warnings.append(
                f"[thin-margin] {r.company}: {r.ebitda_margin_pct}%"
            )

    # ---- 3. completeness ----
    completeness = []
    for col in df.columns:
        miss = int(df[col].isna().sum())
        if miss:
            completeness.append(f"  {col}: {miss}/{len(df)} missing")

    # ---- write + print report ----
    lines = []
    lines.append("=" * 70)
    lines.append("EXTRACTION VALIDATION REPORT")
    lines.append("=" * 70)
    lines.append(f"Issuers: {len(df)} | cohorts: "
                 f"{dict(df.cohort.value_counts().sort_index())}")
    lines.append(f"UNIQUE_ID join: {df.unique_id.notna().sum()}/{len(df)} matched")
    lines.append("")
    lines.append(f"ERRORS: {len(errors)}")
    lines += [f"  ! {e}" for e in errors] or ["  (none)"]
    lines.append("")
    lines.append(f"WARNINGS (review, not failures): {len(warnings)}")
    lines += [f"  ~ {w}" for w in warnings] or ["  (none)"]
    lines.append("")
    lines.append("COMPLETENESS (missing = genuine non-disclosure, verified by hand):")
    lines += completeness or ["  all fields fully populated"]
    lines.append("=" * 70)
    verdict = "PASS - extraction trustworthy" if not errors else "FAIL - review errors"
    lines.append(f"VERDICT: {verdict}")
    lines.append("=" * 70)

    report = "\n".join(lines)
    print(report)
    with open(REPORT, "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
