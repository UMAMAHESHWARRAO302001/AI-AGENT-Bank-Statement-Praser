
import pytest
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_parser():
    from custom_parsers.icici_parser import parse
    
    pdf_path = "data/icici/icic_sample.pdf"
    expected_csv = "data/icici/expected.csv"
    
    result_df = parse(pdf_path)
    expected_df = pd.read_csv(expected_csv)
    
    print(f"Result shape: {result_df.shape}")
    print(f"Expected shape: {expected_df.shape}")
    
    for col in ['Debit Amt', 'Credit Amt', 'Balance']:
        result_df[col] = pd.to_numeric(result_df[col], errors='coerce')
        expected_df[col] = pd.to_numeric(expected_df[col], errors='coerce')
    
    assert result_df.shape == expected_df.shape, f"Shape mismatch: {result_df.shape} vs {expected_df.shape}"
    assert list(result_df.columns) == list(expected_df.columns), f"Columns mismatch: {list(result_df.columns)} vs {list(expected_df.columns)}"
    
    pd.testing.assert_frame_equal(
        result_df.reset_index(drop=True), 
        expected_df.reset_index(drop=True), 
        check_dtype=False, 
        atol=0.01
    )
    print("[PASS] All tests passed!")

if __name__ == "__main__":
    test_parser()
