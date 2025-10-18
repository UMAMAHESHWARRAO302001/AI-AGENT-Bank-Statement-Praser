"""
Bank Statement Parser Agent - Enhanced with HIGH PRIORITY improvements
1. Better PDF Analysis - Deep table structure extraction
2. Error Categorization & Targeted Fixing
3. Structured Code Templates
4. Improved Prompts with examples
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import TypedDict, Literal, Dict, List, Any
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
import pandas as pd
import json

# ============================================
# CONFIGURATION
# ============================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "ENTER YOUR API KEY")

# Different temperatures for different tasks
llm_analysis = ChatGroq(temperature=0.6, model_name="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)
llm_code = ChatGroq(temperature=0.1, model_name="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)
llm_planning = ChatGroq(temperature=0.5, model_name="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)


class TableStructure(TypedDict):
    """Structured representation of PDF table"""
    page_num: int
    table_index: int
    num_columns: int
    num_rows: int
    headers: List[str]
    sample_rows: List[List[str]]
    column_mapping: Dict[str, int]  # CSV column name -> PDF column index


class ErrorAnalysis(TypedDict):
    """Categorized error information"""
    error_type: str  # 'shape', 'columns', 'values', 'syntax', 'runtime'
    specific_issue: str
    failed_assertion: str
    row_count_diff: str
    column_issues: List[str]


class AgentState(TypedDict):
    """Enhanced state with structured data"""
    bank_name: str
    pdf_path: str
    csv_path: str
    
    # Enhanced analysis data
    table_structures: List[TableStructure]  # NEW: Structured table info
    expected_row_count: int
    expected_columns: List[str]
    column_mapping: Dict[str, int]  # NEW: CSV col -> PDF col index
    
    # Analysis outputs
    pdf_analysis: str  # Focused summary
    plan: str
    
    # Code and testing
    parser_code: str
    test_results: str
    error_analysis: ErrorAnalysis  # NEW: Structured error info
    attempt: int
    max_attempts: int
    
    # Learning from attempts
    previous_issues: List[str]  # NEW: Track what we've tried to fix


def deep_analyze_pdf(pdf_path: str) -> List[TableStructure]:
    """
    ENHANCEMENT #1: Deep PDF table structure extraction
    Identifies exact table layout, columns, and data patterns
    """
    import pdfplumber
    
    structures = []
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"   Analyzing {len(pdf.pages)} pages...")
        
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            
            if not tables:
                continue
            
            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:  # Need header + at least 1 row
                    continue
                
                # Extract structure
                headers = [str(cell).strip() if cell else "" for cell in table[0]]
                sample_rows = []
                
                for row in table[1:min(6, len(table))]:  # Get 5 sample rows
                    cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                    if any(cleaned_row):  # Skip empty rows
                        sample_rows.append(cleaned_row)
                
                structure: TableStructure = {
                    'page_num': page_num,
                    'table_index': table_idx,
                    'num_columns': len(headers),
                    'num_rows': len(table) - 1,  # Exclude header
                    'headers': headers,
                    'sample_rows': sample_rows,
                    'column_mapping': {}
                }
                
                structures.append(structure)
                
                print(f"   Page {page_num}, Table {table_idx}: {len(headers)} cols, {structure['num_rows']} rows")
                print(f"      Headers: {headers}")
    
    return structures


def identify_column_mapping(table_structures: List[TableStructure], expected_columns: List[str]) -> Dict[str, int]:
    """
    ENHANCEMENT #1: Intelligent column mapping
    Maps expected CSV columns to PDF table column indices
    """
    # Use the first table structure (assuming consistent format)
    if not table_structures:
        return {}
    
    main_table = table_structures[0]
    headers = main_table['headers']
    
    mapping = {}
    
    # Smart matching logic
    for csv_col in expected_columns:
        csv_lower = csv_col.lower()
        
        for idx, pdf_header in enumerate(headers):
            pdf_lower = pdf_header.lower()
            
            # Exact or partial match
            if csv_lower in pdf_lower or pdf_lower in csv_lower:
                mapping[csv_col] = idx
                break
            
            # Handle common variations
            if csv_col == "Debit Amt" and any(x in pdf_lower for x in ['debit', 'withdrawal', 'dr']):
                mapping[csv_col] = idx
            elif csv_col == "Credit Amt" and any(x in pdf_lower for x in ['credit', 'deposit', 'cr']):
                mapping[csv_col] = idx
            elif csv_col == "Balance" and 'balance' in pdf_lower:
                mapping[csv_col] = idx
            elif csv_col == "Date" and 'date' in pdf_lower:
                mapping[csv_col] = idx
            elif csv_col == "Description" and any(x in pdf_lower for x in ['description', 'particulars', 'narration', 'details']):
                mapping[csv_col] = idx
    
    return mapping


def categorize_error(test_results: str, expected_row_count: int) -> ErrorAnalysis:
    """
    ENHANCEMENT #2: Error categorization for targeted fixing
    Parses test output to identify specific failure type
    """
    analysis: ErrorAnalysis = {
        'error_type': 'unknown',
        'specific_issue': '',
        'failed_assertion': '',
        'row_count_diff': '',
        'column_issues': []
    }
    
    lines = test_results.split('\n')
    
    # Check for syntax errors
    if 'SyntaxError' in test_results or 'IndentationError' in test_results:
        analysis['error_type'] = 'syntax'
        for line in lines:
            if 'Error' in line:
                analysis['specific_issue'] = line.strip()
                break
        return analysis
    
    # Check for runtime errors
    if 'AttributeError' in test_results or 'TypeError' in test_results or 'KeyError' in test_results:
        analysis['error_type'] = 'runtime'
        for line in lines:
            if 'Error:' in line or 'Traceback' in line:
                analysis['specific_issue'] = line.strip()
        return analysis
    
    # Check for shape mismatch
    if 'Shape mismatch' in test_results:
        analysis['error_type'] = 'shape'
        for line in lines:
            if 'Shape mismatch' in line:
                analysis['failed_assertion'] = line.strip()
                # Extract actual vs expected
                if 'vs' in line:
                    parts = line.split('vs')
                    if len(parts) == 2:
                        actual = parts[0].split('(')[-1].strip() if '(' in parts[0] else ''
                        expected = parts[1].split(')')[0].strip() if ')' in parts[1] else ''
                        analysis['row_count_diff'] = f"Got {actual}, expected {expected}"
        
        # Determine if we have too few or too many rows
        if 'Got' in analysis['row_count_diff']:
            try:
                got_rows = int(analysis['row_count_diff'].split('Got')[1].split(',')[0].strip())
                if got_rows < expected_row_count:
                    analysis['specific_issue'] = f"Missing rows: got {got_rows} but need {expected_row_count}. Likely not iterating all pages."
                else:
                    analysis['specific_issue'] = f"Too many rows: got {got_rows} but need {expected_row_count}. Likely including header/summary rows."
            except:
                analysis['specific_issue'] = "Row count mismatch"
        
        return analysis
    
    # Check for column mismatch
    if 'Columns mismatch' in test_results or 'columns' in test_results.lower():
        analysis['error_type'] = 'columns'
        for line in lines:
            if 'Columns' in line or 'columns' in line:
                analysis['failed_assertion'] = line.strip()
                analysis['specific_issue'] = "Column names don't match expected format"
        return analysis
    
    # Check for value mismatch
    if 'DataFrame mismatch' in test_results or 'assert_frame_equal' in test_results:
        analysis['error_type'] = 'values'
        analysis['specific_issue'] = "Data values don't match expected output"
        
        # Try to identify which columns have issues
        for line in lines:
            if 'Debit' in line or 'Credit' in line or 'Balance' in line or 'Date' in line:
                analysis['column_issues'].append(line.strip())
        
        return analysis
    
    # Generic failure
    analysis['specific_issue'] = "Test failed but error type unclear"
    return analysis


def analyze_node(state: AgentState) -> AgentState:
    """
    ENHANCEMENT #1: Deep analysis with table structure extraction
    """
    print(f"\n[ANALYZING] {state['bank_name']} statement with deep structure extraction...")
    
    # Deep table extraction
    state['table_structures'] = deep_analyze_pdf(state['pdf_path'])
    
    if not state['table_structures']:
        print("   [WARNING] No tables found in PDF!")
        state['pdf_analysis'] = "ERROR: No extractable tables found in PDF"
        return state
    
    # Read expected CSV structure
    df = pd.read_csv(state['csv_path'])
    state['expected_row_count'] = len(df)
    state['expected_columns'] = list(df.columns)
    
    # Identify column mapping
    state['column_mapping'] = identify_column_mapping(state['table_structures'], state['expected_columns'])
    
    print(f"   Found {len(state['table_structures'])} tables across {len(set(t['page_num'] for t in state['table_structures']))} pages")
    print(f"   Expected output: {state['expected_row_count']} rows")
    print(f"   Column mapping: {state['column_mapping']}")
    
    # Create focused analysis summary
    main_table = state['table_structures'][0]
    analysis_summary = f"""PDF STRUCTURE ANALYSIS:
- Total tables found: {len(state['table_structures'])}
- Pages with tables: {len(set(t['page_num'] for t in state['table_structures']))}
- Main table structure:
  * Columns: {main_table['num_columns']}
  * Headers: {main_table['headers']}
  * Sample data: {main_table['sample_rows'][:2]}

COLUMN MAPPING (CSV -> PDF index):
{json.dumps(state['column_mapping'], indent=2)}

EXPECTED OUTPUT:
- Rows: {state['expected_row_count']}
- Columns: {state['expected_columns']}
- Sample CSV data:
{df.head(3).to_string()}

KEY OBSERVATIONS:
- Tables appear on {len(set(t['page_num'] for t in state['table_structures']))} pages
- Must iterate ALL pages to get {state['expected_row_count']} rows
- Date format in CSV: {df['Date'].iloc[0] if len(df) > 0 else 'Unknown'}
- Debit/Credit pattern: Check if separate columns or single column with +/-
"""
    
    state['pdf_analysis'] = analysis_summary
    
    # Use analysis-optimized LLM for deeper insights
    insight_prompt = f"""Analyze this bank statement structure and provide parsing strategy:

{analysis_summary}

Provide concise technical insights:
1. Which table index contains transactions (if multiple tables per page)?
2. How to distinguish transaction rows from header/summary rows?
3. Debit/Credit detection logic (separate columns? signs? keywords?)
4. Any data cleaning needed (remove commas, handle empty cells)?
5. Critical edge cases to handle?

Keep response focused and actionable (5-7 bullet points)."""
    
    response = llm_analysis.invoke(insight_prompt)
    state['pdf_analysis'] += f"\n\nLLM INSIGHTS:\n{response.content}"
    
    print("[OK] Deep analysis complete")
    return state


def plan_node(state: AgentState) -> AgentState:
    """
    ENHANCEMENT #4: Improved planning with structured templates
    """
    print("\n[PLANNING] Creating implementation strategy with code template...")
    
    plan_prompt = f"""Create a precise implementation plan for parsing this bank statement:

STRUCTURE:
{state['pdf_analysis']}

COLUMN MAPPING:
{json.dumps(state['column_mapping'], indent=2)}

TARGET: Extract {state['expected_row_count']} rows with columns {state['expected_columns']}

Create a step-by-step plan:

1. **Page Iteration**: How to loop through all pages
2. **Table Selection**: Which table index to use (0, 1, etc.)
3. **Row Filtering**: How to skip header/summary rows
4. **Column Extraction**: Exact mapping using indices {state['column_mapping']}
5. **Data Cleaning**: Handle empty cells, commas, data types
6. **Debit/Credit Logic**: Which column gets which value
7. **Edge Cases**: None values, merged cells, multi-line text

Keep plan technical and specific with exact column indices."""

    response = llm_planning.invoke(plan_prompt)
    state['plan'] = response.content
    
    print("[OK] Implementation plan created")
    return state


def code_node(state: AgentState) -> AgentState:
    """
    ENHANCEMENT #3: Structured code generation with template
    ENHANCEMENT #4: Few-shot examples in prompt
    """
    print(f"\n[CODING] Generating parser (attempt {state['attempt'] + 1})...")
    
    # Build error context if this is a retry
    error_context = ""
    if state.get('error_analysis') and state['error_analysis']['error_type'] != 'unknown':
        error_context = f"""
PREVIOUS ATTEMPT FAILED:
Error Type: {state['error_analysis']['error_type']}
Issue: {state['error_analysis']['specific_issue']}
Failed: {state['error_analysis']['failed_assertion']}

FIXES NEEDED:
{get_fix_suggestions(state['error_analysis'], state['column_mapping'])}
"""
    
    # ENHANCEMENT #3: Provide code template
    code_template = '''import pdfplumber
import pandas as pd

def parse(pdf_path: str) -> pd.DataFrame:
    """Parse bank statement PDF to DataFrame"""
    all_transactions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:
                continue
            
            # Use the main transaction table (index 0 or 1)
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
                debit_amt = ""
                credit_amt = ""
                
                # [YOUR LOGIC HERE for determining debit vs credit]
                
                # Parse balance
                balance_str = row[BALANCE_COL_INDEX] if row[BALANCE_COL_INDEX] else ""
                balance = float(balance_str.replace(",", "")) if balance_str else ""
                
                all_transactions.append([date, description, debit_amt, credit_amt, balance])
    
    return pd.DataFrame(all_transactions, columns=['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'])
'''
    
    # ENHANCEMENT #4: Few-shot examples
    few_shot_examples = """
EXAMPLE 1 - Separate Debit/Credit columns:
If PDF has: [Date, Desc, Debit, Credit, Balance]
And row is: ['01-01-2024', 'Purchase', '100.50', '', '500.00']
Then: debit_amt = float(row[2].replace(",", "")) if row[2] and row[2].strip() else ""
      credit_amt = float(row[3].replace(",", "")) if row[3] and row[3].strip() else ""

EXAMPLE 2 - Single amount column with keyword detection:
If PDF has: [Date, Desc, Amount, Balance]
And desc has 'credit'/'deposit': amount goes to credit_amt
And desc has 'debit'/'withdrawal': amount goes to debit_amt

EXAMPLE 3 - Handling None/empty values safely:
WRONG: amount = row[2].replace(",", "")  # Crashes if row[2] is None
RIGHT: amount = row[2].replace(",", "") if row[2] and row[2].strip() else ""
"""
    
    code_prompt = f"""Generate complete Python parser for {state['bank_name']}_parser.py

STRUCTURE ANALYSIS:
{state['pdf_analysis'][:1000]}

IMPLEMENTATION PLAN:
{state['plan'][:800]}

{error_context}

COLUMN MAPPING (Use these exact indices):
{json.dumps(state['column_mapping'], indent=2)}

REQUIREMENTS:
1. Function: def parse(pdf_path: str) -> pd.DataFrame
2. Return columns: {state['expected_columns']}
3. Expected rows: {state['expected_row_count']}
4. Use table index: {state['table_structures'][0]['table_index']} (from analysis)
5. Iterate ALL pages: for page in pdf.pages (NOT pdf.pages[0])
6. Empty Debit/Credit must be "" not NaN
7. Always check if cell is None/empty before calling .strip() or .replace()

CODE TEMPLATE TO FOLLOW:
{code_template}

{few_shot_examples}

CRITICAL PATTERNS:
- Always: if row[idx] and row[idx].strip() before processing
- Float conversion: float(val.replace(",", "")) if val and val.strip() else ""
- Skip rows: if not row or not row[0]: continue

Generate ONLY the complete parse() function with imports. NO test code or main blocks."""

    response = llm_code.invoke(code_prompt)
    code = response.content
    
    # Clean code extraction
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0].strip()
    elif "```" in code:
        code = code.split("```")[1].split("```")[0].strip()
    
    # Remove test/example code
    code_lines = code.split('\n')
    cleaned_lines = []
    
    for line in code_lines:
        if any(x in line for x in ['if __name__', '# Test', '# Example', 'pdf_path = "', 'print(parse']):
            break
        cleaned_lines.append(line)
    
    code = '\n'.join(cleaned_lines).rstrip() + '\n'
    
    state['parser_code'] = code
    state['attempt'] += 1
    
    print("[OK] Code generated with structured template")
    return state


def get_fix_suggestions(error_analysis: ErrorAnalysis, column_mapping: Dict[str, int]) -> str:
    """Generate specific fix suggestions based on error type"""
    
    if error_analysis['error_type'] == 'shape':
        if 'Missing rows' in error_analysis['specific_issue']:
            return """
- CRITICAL: Ensure iterating ALL pages: for page in pdf.pages (not pdf.pages[0])
- Check table_index: might be using wrong table on each page
- Verify not breaking loop early
- Check if skipping too many rows (header check too strict)
"""
        elif 'Too many rows' in error_analysis['specific_issue']:
            return """
- Likely including header rows from each page
- Add check: if row[0] in ['Date', 'date', 'DATE']: continue
- Verify starting from table[1:] not table[0:]
- Check for summary rows at end of tables
"""
    
    elif error_analysis['error_type'] == 'runtime':
        return """
- Check for None values: if row[idx] and row[idx].strip() before processing
- Ensure column indices are valid: verify {column_mapping}
- Wrap string operations: val.replace() only if val is not None
"""
    
    elif error_analysis['error_type'] == 'values':
        return """
- Verify Debit/Credit logic matches expected pattern
- Check number format: remove commas before float conversion
- Validate date format matches CSV exactly
- Ensure empty amounts are "" not NaN or 0
"""
    
    elif error_analysis['error_type'] == 'syntax':
        return """
- Fix indentation errors
- Check for unclosed brackets/parentheses
- Verify all imports are present
"""
    
    return "Review code structure and logic"


def test_node(state: AgentState) -> AgentState:
    """Test with enhanced error analysis"""
    print("\n[TESTING] Running validation with error categorization...")
    
    # Save and run test (same as before)
    parser_dir = Path("custom_parsers")
    parser_dir.mkdir(exist_ok=True)
    
    init_file = parser_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding='utf-8')
    
    parser_file = parser_dir / f"{state['bank_name']}_parser.py"
    with open(parser_file, 'w', encoding='utf-8') as f:
        f.write(state['parser_code'])
    
    print(f"   Parser saved to: {parser_file}")
    
    # Create test file
    test_code = f"""
import pytest
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_parser():
    from custom_parsers.{state['bank_name']}_parser import parse
    
    pdf_path = "{state['pdf_path']}"
    expected_csv = "{state['csv_path']}"
    
    result_df = parse(pdf_path)
    expected_df = pd.read_csv(expected_csv)
    
    print(f"Result shape: {{result_df.shape}}")
    print(f"Expected shape: {{expected_df.shape}}")
    
    for col in ['Debit Amt', 'Credit Amt', 'Balance']:
        result_df[col] = pd.to_numeric(result_df[col], errors='coerce')
        expected_df[col] = pd.to_numeric(expected_df[col], errors='coerce')
    
    assert result_df.shape == expected_df.shape, f"Shape mismatch: {{result_df.shape}} vs {{expected_df.shape}}"
    assert list(result_df.columns) == list(expected_df.columns), f"Columns mismatch: {{list(result_df.columns)}} vs {{list(expected_df.columns)}}"
    
    pd.testing.assert_frame_equal(
        result_df.reset_index(drop=True), 
        expected_df.reset_index(drop=True), 
        check_dtype=False, 
        atol=0.01
    )
    print("[PASS] All tests passed!")

if __name__ == "__main__":
    test_parser()
"""
    
    test_file = Path(f"test_{state['bank_name']}_parser.py")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_code)
    
    print(f"   Test saved to: {test_file}")
    
    # Run pytest
    result = subprocess.run(
        ['pytest', str(test_file), '-v', '--tb=short'],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    test_output = result.stdout + result.stderr
    
    if result.returncode == 0:
        print("[OK] Tests PASSED!")
        state['error_analysis'] = {
            'error_type': 'none',
            'specific_issue': '',
            'failed_assertion': '',
            'row_count_diff': '',
            'column_issues': []
        }
    else:
        print("[FAIL] Tests FAILED - Analyzing error...")
        
        # ENHANCEMENT #2: Categorize error
        state['error_analysis'] = categorize_error(test_output, state['expected_row_count'])
        
        print(f"   Error Type: {state['error_analysis']['error_type']}")
        print(f"   Issue: {state['error_analysis']['specific_issue']}")
        
        # Track this issue
        if 'previous_issues' not in state:
            state['previous_issues'] = []
        state['previous_issues'].append(state['error_analysis']['specific_issue'])
    
    return state


def refine_node(state: AgentState) -> AgentState:
    """
    ENHANCEMENT #2: Targeted refinement based on error category
    """
    print(f"\n[REFINING] Targeted fix for '{state['error_analysis']['error_type']}' error...")
    
    error_type = state['error_analysis']['error_type']
    
    # Create focused refinement prompt based on error type
    if error_type == 'shape':
        focus = "Fix the row count issue - ensure ALL pages are processed and correct rows are extracted."
    elif error_type == 'runtime':
        focus = "Fix the runtime error - add None/empty checks before string operations."
    elif error_type == 'values':
        focus = "Fix the data value mismatch - verify Debit/Credit logic and number formatting."
    elif error_type == 'columns':
        focus = "Fix the column mismatch - ensure exact column names match expected output."
    else:
        focus = "Fix the identified issues in the code."
    
    refine_prompt = f"""Fix the parser code - FOCUSED FIX ONLY.

ERROR ANALYSIS:
Type: {state['error_analysis']['error_type']}
Issue: {state['error_analysis']['specific_issue']}
Failed: {state['error_analysis']['failed_assertion']}

CURRENT CODE:
{state['parser_code']}

COLUMN MAPPING:
{json.dumps(state['column_mapping'], indent=2)}

PLAN:
{state['plan'][:500]}

FOCUS: {focus}

SPECIFIC FIXES NEEDED:
{get_fix_suggestions(state['error_analysis'], state['column_mapping'])}

PREVIOUS ATTEMPTS TRIED TO FIX:
{', '.join(state.get('previous_issues', [])) if state.get('previous_issues') else 'None'}

Generate the COMPLETE CORRECTED code (imports + parse function only, no test code).
Make MINIMAL changes - only fix what's broken."""

    response = llm_code.invoke(refine_prompt)
    code = response.content
    
    # Clean extraction
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0].strip()
    elif "```" in code:
        code = code.split("```")[1].split("```")[0].strip()
    
    # Remove test code
    code_lines = code.split('\n')
    cleaned_lines = []
    
    for line in code_lines:
        if any(x in line for x in ['if __name__', '# Test', '# Example', 'pdf_path = "']):
            break
        cleaned_lines.append(line)
    
    code = '\n'.join(cleaned_lines).rstrip() + '\n'
    
    state['parser_code'] = code
    print(f"[OK] Targeted refinement complete for {error_type} error")
    return state


def should_continue(state: AgentState) -> Literal["refine", "end"]:
    """Decide whether to refine or end"""
    has_error = state.get('error_analysis', {}).get('error_type') not in ['none', 'unknown', '']
    can_retry = state['attempt'] < state['max_attempts']
    
    if has_error and can_retry:
        return "refine"
    return "end"


def create_agent_graph():
    """Create the enhanced LangGraph workflow"""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("analyze_pdf", analyze_node)
    workflow.add_node("create_plan", plan_node)
    workflow.add_node("generate_code", code_node)
    workflow.add_node("run_tests", test_node)
    workflow.add_node("refine_code", refine_node)
    
    workflow.set_entry_point("analyze_pdf")
    workflow.add_edge("analyze_pdf", "create_plan")
    workflow.add_edge("create_plan", "generate_code")
    workflow.add_edge("generate_code", "run_tests")
    workflow.add_conditional_edges(
        "run_tests",
        should_continue,
        {
            "refine": "refine_code",
            "end": END
        }
    )
    workflow.add_edge("refine_code", "generate_code")
    
    return workflow.compile()


def main():
    parser = argparse.ArgumentParser(description="Generate bank statement parser - ENHANCED")
    parser.add_argument("--target", required=True, help="Bank name (e.g., icici)")
    parser.add_argument("--max-attempts", type=int, default=5, help="Max retry attempts")
    args = parser.parse_args()
    
    bank_name = args.target.lower()
    pdf_path = f"data/{bank_name}/icic_sample.pdf"
    csv_path = f"data/{bank_name}/expected.csv"
    
    # Verify files exist
    if not Path(pdf_path).exists():
        print(f"[ERROR] PDF not found at {pdf_path}")
        sys.exit(1)
    if not Path(csv_path).exists():
        print(f"[ERROR] CSV not found at {csv_path}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"ENHANCED BANK PARSER AGENT")
    print(f"{'='*60}")
    print(f"Target Bank: {bank_name.upper()}")
    print(f"PDF: {pdf_path}")
    print(f"CSV: {csv_path}")
    print(f"Model: llama-3.3-70b-versatile")
    print(f"Enhancements: Deep PDF Analysis, Error Categorization, Code Templates")
    print(f"{'='*60}")
    
    # Initialize state
    initial_state: AgentState = {
        "bank_name": bank_name,
        "pdf_path": pdf_path,
        "csv_path": csv_path,
        "table_structures": [],
        "expected_row_count": 0,
        "expected_columns": [],
        "column_mapping": {},
        "pdf_analysis": "",
        "plan": "",
        "parser_code": "",
        "test_results": "",
        "error_analysis": {
            'error_type': 'unknown',
            'specific_issue': '',
            'failed_assertion': '',
            'row_count_diff': '',
            'column_issues': []
        },
        "attempt": 0,
        "max_attempts": args.max_attempts,
        "previous_issues": []
    }
    
    # Create and run agent
    agent = create_agent_graph()
    
    try:
        final_state = agent.invoke(initial_state)
        
        # Summary
        print(f"\n{'='*60}")
        print("EXECUTION SUMMARY")
        print(f"{'='*60}")
        
        if final_state['error_analysis']['error_type'] in ['none', '']:
            print("✅ [SUCCESS] Parser generated and tested!")
            print(f"\n📁 Files created:")
            print(f"   - Parser: custom_parsers/{bank_name}_parser.py")
            print(f"   - Test: test_{bank_name}_parser.py")
            print(f"\n📊 Stats:")
            print(f"   - Attempts used: {final_state['attempt']}/{final_state['max_attempts']}")
            print(f"   - Tables found: {len(final_state['table_structures'])}")
            print(f"   - Rows extracted: {final_state['expected_row_count']}")
            print(f"\n🎯 Column Mapping:")
            for csv_col, pdf_idx in final_state['column_mapping'].items():
                print(f"   - {csv_col}: PDF column {pdf_idx}")
        else:
            print("❌ [FAILED] Could not generate working parser")
            print(f"\n🔍 Final Error Analysis:")
            print(f"   - Type: {final_state['error_analysis']['error_type']}")
            print(f"   - Issue: {final_state['error_analysis']['specific_issue']}")
            print(f"   - Attempts: {final_state['attempt']}/{final_state['max_attempts']}")
            
            print(f"\n💡 Suggestions:")
            print(f"   1. Review generated parser: custom_parsers/{bank_name}_parser.py")
            print(f"   2. Check column mapping: {final_state['column_mapping']}")
            print(f"   3. Manually verify PDF table structure")
            print(f"   4. Run test manually: pytest test_{bank_name}_parser.py -v")
            print(f"   5. Check if PDF format is unusual or has merged cells")
            
            if final_state.get('previous_issues'):
                print(f"\n📝 Issues encountered:")
                for i, issue in enumerate(final_state['previous_issues'], 1):
                    print(f"   {i}. {issue}")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n[ERROR] Agent execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()