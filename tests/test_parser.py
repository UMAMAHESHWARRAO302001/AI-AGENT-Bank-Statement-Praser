# tests/test_parser.py
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from custom_parsers import icici_parser  # type: ignore

def test_icici_parse_matches_csv():
    pdf = next(p for p in (ROOT / "data" / "icici").iterdir() if p.suffix == ".pdf")
    csv = next(p for p in (ROOT / "data" / "icici").iterdir() if p.suffix == ".csv")
    df = icici_parser.parse(str(pdf))
    expected = pd.read_csv(str(csv))[["Date","Description","Debit Amt","Credit Amt","Balance"]]
    for c in ["Debit Amt","Credit Amt","Balance"]:
        expected[c] = pd.to_numeric(expected[c], errors="coerce")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    assert df.reset_index(drop=True).equals(expected.reset_index(drop=True))
