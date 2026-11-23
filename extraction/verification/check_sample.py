"""
Certify the regex extraction against an independent hand-read of the PDFs.

ground_truth_sample.json holds values read by eye from the rendered PDF pages
(a different pipeline from the pdfplumber text layer the extractor uses). This
script diffs those against extraction/extracted.csv, field by field, and prints
any mismatch. Zero mismatches => the extraction reproduces an independent human
read on the sampled issuers.
"""
import json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

gt = json.load(open(os.path.join(HERE, "ground_truth_sample.json")))["records"]
df = pd.read_csv(os.path.join(ROOT, "extraction", "extracted.csv")).set_index("company")

FLOAT_TOL = 0.02
checks = mismatches = 0
for rec in gt:
    company = rec["company"]
    row = df.loc[company]
    for field, expected in rec.items():
        if field == "company":
            continue
        actual = row[field]
        checks += 1
        if expected is None:
            ok = pd.isna(actual)
        elif isinstance(expected, bool):
            ok = bool(actual) == expected
        elif isinstance(expected, (int, float)):
            ok = pd.notna(actual) and abs(float(actual) - expected) <= FLOAT_TOL
        else:
            ok = str(actual).strip() == str(expected).strip()
        if not ok:
            mismatches += 1
            print(f"  MISMATCH {company}.{field}: extracted={actual!r} expected={expected!r}")

print(f"\nChecked {checks} fields across {len(gt)} hand-read issuers.")
print(f"Mismatches: {mismatches}")
print("RESULT:", "PASS - extraction matches independent read" if not mismatches else "FAIL")
