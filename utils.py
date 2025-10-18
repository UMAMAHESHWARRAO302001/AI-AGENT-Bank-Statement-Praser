import pdfplumber
import csv

def extract_table_from_pdf(pdf_path):
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    all_rows.append(row)
    cleaned_rows = [
        [cell.strip() if cell else '' for cell in row] for row in all_rows if any(row)
    ]
    return cleaned_rows

def write_rows_to_csv(rows, csv_path):
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
