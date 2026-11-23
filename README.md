# Lender-presentation signal — code & analysis

## What's in this folder

| Path | What it is |
|------|------------|
| `1_code.ipynb` | The analysis — start here. |
| `2_Note_for_PM.md` | One-page note for a PM. |
| `3_Extraction_work.md` | How the extraction works and was checked. |
| `4_more_time_less_sure.md` | Next steps and caveats. |
| `5_Optional.md` | Optional deeper dive. |
| `extraction/` | Extraction scripts and their outputs. |
| `presentations/`, `keys/`, `returns/` | Source PDFs, ID map, returns. |

## Setup (Python 3.9+)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python extraction/extract.py    # PDFs -> extraction/extracted.csv + .json
python extraction/validate.py   # -> extraction/validation_report.txt
```

Then open `1_code.ipynb` from this folder and run top to bottom.
