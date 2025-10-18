"""
FastAPI wrapper for Bank Statement Parser Agent
Production-ready API for deployment
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
import os
import sys
import uuid
import shutil
import pandas as pd
from pathlib import Path
import logging
from datetime import datetime
import json
import io

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import create_agent_graph, AgentState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Bank Statement Parser API",
    description="AI-powered agent that generates custom parsers for bank statement PDFs",
    version="1.0.0"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (use Redis/Database in production)
jobs: Dict[str, dict] = {}

# Create necessary directories
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


class ParseRequest(BaseModel):
    """Request model for parsing"""
    bank_name: str
    max_attempts: Optional[int] = 5


class JobStatus(BaseModel):
    """Job status response"""
    job_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    progress: str
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": "Bank Statement Parser API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "parse": "POST /parse - Upload PDF and CSV to generate parser",
            "status": "GET /status/{job_id} - Check job status",
            "download": "GET /download/{job_id} - Download extracted CSV",
            "health": "GET /health - Health check"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "groq_api_key_set": bool(os.getenv("GROQ_API_KEY"))
    }


@app.post("/parse")
async def parse_statement(
    background_tasks: BackgroundTasks,
    pdf_file: UploadFile = File(...),
    csv_file: UploadFile = File(...),
    bank_name: Optional[str] = "bank",
    max_attempts: Optional[int] = 5
):
    """
    Upload PDF and expected CSV to generate custom parser
    
    - **pdf_file**: Bank statement PDF
    - **csv_file**: Expected CSV output (for validation)
    - **bank_name**: Identifier for the bank (e.g., 'icici', 'hdfc')
    - **max_attempts**: Maximum retry attempts (default: 5)
    
    Returns job_id for tracking progress
    """
    
    # Validate files
    if not pdf_file.filename.endswith('.pdf'):
        raise HTTPException(400, "PDF file must have .pdf extension")
    if not csv_file.filename.endswith('.csv'):
        raise HTTPException(400, "CSV file must have .csv extension")
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Create job directory
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    
    # Save uploaded files
    pdf_path = job_dir / f"{bank_name}_statement.pdf"
    csv_path = job_dir / f"{bank_name}_expected.csv"
    
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(pdf_file.file, f)
    
    with open(csv_path, "wb") as f:
        shutil.copyfileobj(csv_file.file, f)
    
    logger.info(f"Job {job_id}: Files uploaded for {bank_name}")
    
    # Initialize job status
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": "Files uploaded, queued for processing",
        "bank_name": bank_name,
        "pdf_path": str(pdf_path),
        "csv_path": str(csv_path),
        "max_attempts": max_attempts,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "result": None,
        "error": None
    }
    
    # Start background processing
    background_tasks.add_task(process_job, job_id)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job queued for processing",
        "status_url": f"/status/{job_id}",
        "download_url": f"/download/{job_id}"
    }


async def process_job(job_id: str):
    """Background task to process the parsing job"""
    
    try:
        job = jobs[job_id]
        job["status"] = "processing"
        job["progress"] = "Analyzing PDF structure..."
        
        logger.info(f"Job {job_id}: Starting processing")
        
        # Initialize agent state
        initial_state: AgentState = {
            "bank_name": job["bank_name"],
            "pdf_path": job["pdf_path"],
            "csv_path": job["csv_path"],
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
            "max_attempts": job["max_attempts"],
            "previous_issues": []
        }
        
        # Create and run agent
        agent = create_agent_graph()
        
        job["progress"] = "Agent running..."
        final_state = agent.invoke(initial_state)
        
        # Check if successful
        if final_state['error_analysis']['error_type'] in ['none', '']:
            # Success! Parse the PDF and return data
            logger.info(f"Job {job_id}: Parser generated successfully")
            
            # Import the generated parser
            parser_module = f"custom_parsers.{job['bank_name']}_parser"
            
            # Dynamic import
            import importlib
            parser = importlib.import_module(parser_module)
            
            # Parse the PDF
            df = parser.parse(job["pdf_path"])
            
            # Save output CSV
            output_path = OUTPUT_DIR / f"{job_id}_output.csv"
            df.to_csv(output_path, index=False)
            
            job["status"] = "completed"
            job["progress"] = "Complete"
            job["completed_at"] = datetime.now().isoformat()
            job["result"] = {
                "success": True,
                "attempts_used": final_state['attempt'],
                "rows_extracted": len(df),
                "columns": list(df.columns),
                "output_file": str(output_path),
                "parser_file": f"custom_parsers/{job['bank_name']}_parser.py",
                "column_mapping": final_state['column_mapping'],
                "tables_found": len(final_state['table_structures'])
            }
            
            logger.info(f"Job {job_id}: Completed successfully - {len(df)} rows extracted")
            
        else:
            # Failed
            logger.error(f"Job {job_id}: Failed - {final_state['error_analysis']['specific_issue']}")
            
            job["status"] = "failed"
            job["progress"] = "Failed"
            job["completed_at"] = datetime.now().isoformat()
            job["error"] = {
                "error_type": final_state['error_analysis']['error_type'],
                "message": final_state['error_analysis']['specific_issue'],
                "attempts_used": final_state['attempt'],
                "max_attempts": final_state['max_attempts']
            }
    
    except Exception as e:
        logger.error(f"Job {job_id}: Exception - {str(e)}", exc_info=True)
        job["status"] = "failed"
        job["progress"] = "Error"
        job["completed_at"] = datetime.now().isoformat()
        job["error"] = {
            "error_type": "system_error",
            "message": str(e)
        }


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get job status and progress"""
    
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    
    job = jobs[job_id]
    
    return JobStatus(
        job_id=job["job_id"],
        status=job["status"],
        progress=job["progress"],
        result=job.get("result"),
        error=job.get("error"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at")
    )


@app.get("/download/{job_id}")
async def download_result(job_id: str):
    """Download extracted CSV data"""
    
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(400, f"Job is not completed yet. Current status: {job['status']}")
    
    if not job.get("result"):
        raise HTTPException(500, "Result file not found")
    
    output_file = Path(job["result"]["output_file"])
    
    if not output_file.exists():
        raise HTTPException(500, "Output file does not exist")
    
    return FileResponse(
        path=output_file,
        filename=f"{job['bank_name']}_extracted.csv",
        media_type="text/csv"
    )


@app.get("/download/{job_id}/parser")
async def download_parser(job_id: str):
    """Download generated parser code"""
    
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(400, f"Job is not completed yet. Current status: {job['status']}")
    
    parser_file = Path(job["result"]["parser_file"])
    
    if not parser_file.exists():
        raise HTTPException(500, "Parser file not found")
    
    return FileResponse(
        path=parser_file,
        filename=f"{job['bank_name']}_parser.py",
        media_type="text/plain"
    )


@app.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    """List all jobs with optional status filter"""
    
    filtered_jobs = jobs.values()
    
    if status:
        filtered_jobs = [j for j in filtered_jobs if j["status"] == status]
    
    # Sort by created_at descending
    sorted_jobs = sorted(
        filtered_jobs,
        key=lambda x: x["created_at"],
        reverse=True
    )
    
    return {
        "total": len(sorted_jobs),
        "jobs": list(sorted_jobs)[:limit]
    }


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its files"""
    
    if job_id not in jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    
    job = jobs[job_id]
    
    # Delete job directory
    job_dir = UPLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    
    # Delete output file if exists
    if job.get("result") and job["result"].get("output_file"):
        output_file = Path(job["result"]["output_file"])
        if output_file.exists():
            output_file.unlink()
    
    # Remove from jobs dict
    del jobs[job_id]
    
    logger.info(f"Job {job_id}: Deleted")
    
    return {"message": f"Job {job_id} deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )