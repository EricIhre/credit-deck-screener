"""
Deterministic regex extractor for the 50 lender presentations.

The LLM (Claude Code) is used separately as an independent verification pass,
not in this pipeline -- see verify_llm/.

Output:
    extraction/extracted.csv   one row per issuer (analysis-ready)
    extraction/extracted.json  same, with provenance fields for auditing

All monetary values are normalised to EUR millions regardless of the
currency-unit convention stated in each PDF.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, asdict, field
from typing import Optional

import pandas as pd
import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESENTATIONS = os.path.join(ROOT, "presentations")
ID_MAP = os.path.join(ROOT, "keys", "id_map.csv")
OUT_CSV = os.path.join(ROOT, "extraction", "extracted.csv")
OUT_JSON = os.path.join(ROOT, "extraction", "extracted.json")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _norm_name(s: str) -> str:
    """Normalise a company name for joining (drop punctuation/case/spacing)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _num(s: str) -> float:
    """'1,253,287.2' -> 1253287.2"""
    return float(s.replace(",", ""))


def search(pattern: str, text: str, group: int = 1, flags=re.I) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def read_text(pdf_path: str) -> str:
    parts = []
    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def flatten(text: str) -> str:
    """Collapse all whitespace to single spaces.

    Narrative facts frequently wrap across lines in the PDF text layer
    (e.g. 'operating\\n5 principal sites'); matching against a flattened
    view makes the narrative regexes wrap-insensitive. Cover-page fields
    stay on the raw text because they are line-anchored.
    """
    return re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
@dataclass
class Record:
    # identity / keys
    company: str
    unique_id: Optional[str]
    cohort: int                       # 2024 = research, 2025 = validation
    # cover page
    sector: Optional[str] = None
    hq_country: Optional[str] = None
    transaction_type: Optional[str] = None
    bookrunner: Optional[str] = None
    presentation_date: Optional[str] = None
    # business overview
    founded_year: Optional[int] = None
    company_age_years: Optional[int] = None
    n_sites: Optional[int] = None
    n_employees: Optional[int] = None
    auditor: Optional[str] = None
    esg_rating: Optional[str] = None
    tech_disruption_risk: Optional[str] = None     # LOW / MODERATE / ELEVATED
    # management & ownership
    ownership_type: Optional[str] = None           # sponsor / family
    ceo_tenure_years: Optional[int] = None
    # financials (all EUR millions)
    revenue_eur_m: Optional[float] = None
    ebitda_eur_m: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None
    ebitda_margin_prior_pct: Optional[float] = None
    ebitda_margin_delta_bps: Optional[float] = None  # current - prior, +ve = expanding
    net_debt_eur_m: Optional[float] = None
    net_leverage_x: Optional[float] = None
    net_leverage_is_derived: bool = False          # True when computed net_debt/EBITDA
    # customers & markets
    top3_customer_concentration_pct: Optional[float] = None
    recurring_revenue_pct: Optional[float] = None
    # provenance (for auditing, not modelling)
    currency_unit_raw: Optional[str] = None
    margin_trend_raw: Optional[str] = None
    source_file: Optional[str] = None


RISK_ORDER = {"LOW": 0, "MODERATE": 1, "ELEVATED": 2}


# --------------------------------------------------------------------------- #
# Field extraction
# --------------------------------------------------------------------------- #
def extract_financials(text: str, rec: Record) -> None:
    """Parse the Financial Highlights table and normalise to EUR millions."""
    unit_raw = search(r"All figures in (EUR[^.]*?) unless otherwise stated", text)
    rec.currency_unit_raw = unit_raw
    # scale factor to convert the printed number into EUR millions
    if unit_raw and "000" in unit_raw:          # "EUR '000s" -> thousands
        scale = 1 / 1000.0
    else:                                        # "EUR millions"
        scale = 1.0

    rev = search(r"\bRevenue\s+([\d,]+\.?\d*)", text)
    ebitda = search(r"\bEBITDA\s+([\d,]+\.?\d*)", text)
    net_debt = search(r"\bNet debt\s+([\d,]+\.?\d*)", text)
    margin = search(r"EBITDA margin \(%\)\s+([\d.]+)%", text)
    lev = search(r"Net leverage \(Net debt / EBITDA\)\s+([\d.]+)x", text)

    if rev:
        rec.revenue_eur_m = round(_num(rev) * scale, 4)
    if ebitda:
        rec.ebitda_eur_m = round(_num(ebitda) * scale, 4)
    if net_debt:
        rec.net_debt_eur_m = round(_num(net_debt) * scale, 4)
    if margin:
        rec.ebitda_margin_pct = float(margin)
    if lev:
        rec.net_leverage_x = float(lev)
    elif rec.net_debt_eur_m is not None and rec.ebitda_eur_m not in (None, 0):
        # Some presentations omit the headline multiple ("a single headline
        # multiple is not presented"). Derive it from the disclosed components.
        rec.net_leverage_x = round(rec.net_debt_eur_m / rec.ebitda_eur_m, 2)
        rec.net_leverage_is_derived = True


def extract_margin_trend(text: str, rec: Record) -> None:
    """Prior-year margin is disclosed two ways: explicit level, or a bps delta."""
    explicit = search(
        r"prior-year \(LTM-1\) EBITDA margin was ([\d.]+)%", text
    )
    if explicit:
        rec.margin_trend_raw = f"explicit prior margin {explicit}%"
        rec.ebitda_margin_prior_pct = float(explicit)
    else:
        m = re.search(
            r"margin (expanded|contracted) by approximately (\d+)\s*bps year-on-year",
            text, re.I,
        )
        if m:
            direction, bps = m.group(1).lower(), int(m.group(2))
            rec.margin_trend_raw = m.group(0)
            if rec.ebitda_margin_pct is not None:
                # "expanded" => current > prior ; "contracted" => current < prior
                signed = bps if direction == "expanded" else -bps
                rec.ebitda_margin_prior_pct = round(
                    rec.ebitda_margin_pct - signed / 100.0, 4
                )

    if rec.ebitda_margin_pct is not None and rec.ebitda_margin_prior_pct is not None:
        rec.ebitda_margin_delta_bps = round(
            (rec.ebitda_margin_pct - rec.ebitda_margin_prior_pct) * 100, 1
        )


def extract_record(pdf_path: str, name_to_id: dict) -> Record:
    text = read_text(pdf_path)
    flat = flatten(text)          # wrap-insensitive view for narrative fields
    year = int(os.path.basename(os.path.dirname(pdf_path)))
    company = os.path.basename(pdf_path).replace(".pdf", "").replace("_", " ")

    rec = Record(
        company=company,
        unique_id=name_to_id.get(_norm_name(company)),
        cohort=year,
        source_file=os.path.relpath(pdf_path, ROOT),
    )

    # ---- cover page (label<TAB/space>value on one line) ----
    rec.sector = search(r"^Sector\s+(.+)$", text, flags=re.I | re.M)
    rec.hq_country = search(r"^Headquarters\s+(.+)$", text, flags=re.I | re.M)
    rec.transaction_type = search(r"^Transaction\s+(.+)$", text, flags=re.I | re.M)
    rec.bookrunner = search(
        r"^Sole Physical Bookrunner\s+(.+)$", text, flags=re.I | re.M
    )
    rec.presentation_date = search(r"^Date\s+(\d{4}-\d{2})", text, flags=re.I | re.M)

    # ---- business overview (narrative -> flat view) ----
    fy = search(r"Founded in (\d{4})", flat)
    if fy:
        rec.founded_year = int(fy)
        rec.company_age_years = year - int(fy)
    sites = search(r"operating (\d+)\s+principal sites", flat)
    if sites:
        rec.n_sites = int(sites)
    emp = search(r"employing approximately ([\d,]+)\s+people", flat)
    if emp:
        rec.n_employees = int(emp.replace(",", ""))
    rec.auditor = search(r"audited by ([A-Za-z][A-Za-z& ]+?) and maintains", flat)
    rec.esg_rating = search(r"sustainability rating of '([A-D])'", flat)
    rec.tech_disruption_risk = search(
        r"disruption risk is assessed as ([A-Z]+)", flat
    )

    # ---- management & ownership ----
    if re.search(r"privately held by its founding family", flat, re.I):
        rec.ownership_type = "family"
    elif re.search(r"majority-owned by a leading financial sponsor", flat, re.I):
        rec.ownership_type = "sponsor"
    tenure = search(r"held the role for (\d+)\s+years", flat)
    if tenure:
        rec.ceo_tenure_years = int(tenure)

    # ---- financials ----
    extract_financials(flat, rec)
    extract_margin_trend(flat, rec)

    # ---- customers & markets ----
    conc = search(
        r"top three customers together account for\s+approximately (\d+)%", flat
    )
    if conc:
        rec.top3_customer_concentration_pct = float(conc)
    rec_rev = search(r"approximately (\d+)% of revenue is recurring", flat)
    if rec_rev:
        rec.recurring_revenue_pct = float(rec_rev)

    return rec


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def main() -> pd.DataFrame:
    id_map = pd.read_csv(ID_MAP)
    name_to_id = {_norm_name(n): i for n, i in zip(id_map.CompanyName, id_map.UNIQUE_ID)}

    pdfs = sorted(glob.glob(os.path.join(PRESENTATIONS, "*", "*.pdf")))
    records = [extract_record(p, name_to_id) for p in pdfs]

    rows = [asdict(r) for r in records]
    df = pd.DataFrame(rows)

    df.to_csv(OUT_CSV, index=False)
    with open(OUT_JSON, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Extracted {len(df)} issuers -> {os.path.relpath(OUT_CSV, ROOT)}")
    return df


if __name__ == "__main__":
    main()
