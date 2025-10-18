import pdfplumber
import pandas as pd

def parse(pdf_path: str) -> pd.DataFrame:
    """Parse bank statement PDF to DataFrame"""
    all_transactions = []
    TABLE_INDEX = 0
    DATE_COL_INDEX = 0
    DESC_COL_INDEX = 1
    DEBIT_COL_INDEX = 2
    CREDIT_COL_INDEX = 3
    BALANCE_COL_INDEX = 4
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:
                continue
            
            # Use the main transaction table (index 0)
            table = tables[TABLE_INDEX]
            
            # Skip header row, process data rows
            for row in table[1:]:
                # Skip empty rows
                if not row or not row[DATE_COL_INDEX]:
                    continue
                
                # Extract columns using mapping
                date = row[DATE_COL_INDEX].strip() if row[DATE_COL_INDEX] else ""
                description = row[DESC_COL_INDEX].strip() if row[DESC_COL_INDEX] else ""
                
                # Handle Debit/Credit with proper empty string handling
                debit_amt = float(row[DEBIT_COL_INDEX].replace(",", "")) if row[DEBIT_COL_INDEX] and row[DEBIT_COL_INDEX].strip() else ""
                credit_amt = float(row[CREDIT_COL_INDEX].replace(",", "")) if row[CREDIT_COL_INDEX] and row[CREDIT_COL_INDEX].strip() else ""
                
                # Parse balance
                balance_str = row[BALANCE_COL_INDEX] if row[BALANCE_COL_INDEX] else ""
                balance = float(balance_str.replace(",", "")) if balance_str and balance_str.strip() else ""
                
                all_transactions.append([date, description, debit_amt, credit_amt, balance])
    
    return pd.DataFrame(all_transactions, columns=['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'])
