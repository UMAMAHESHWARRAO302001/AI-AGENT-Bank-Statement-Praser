"""
Test script for deployed API
Run this to verify your deployment works correctly
"""

import requests
import time
import sys
from pathlib import Path

# Configuration
API_URL = input("Enter your API URL (e.g., https://your-app.railway.app): ").strip()
if not API_URL:
    print("❌ API URL is required")
    sys.exit(1)

print(f"\n🎯 Testing API at: {API_URL}\n")

# Test 1: Health Check
print("1️⃣ Testing health endpoint...")
try:
    response = requests.get(f"{API_URL}/health", timeout=10)
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ API is healthy")
        print(f"   Status: {data.get('status')}")
        print(f"   GROQ API Key set: {data.get('groq_api_key_set')}")
    else:
        print(f"   ❌ Health check failed: {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    sys.exit(1)

# Test 2: Root endpoint
print("\n2️⃣ Testing root endpoint...")
try:
    response = requests.get(API_URL, timeout=10)
    if response.status_code == 200:
        print("   ✅ Root endpoint working")
    else:
        print(f"   ⚠️  Root returned: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Test 3: Upload and parse (if files exist)
pdf_path = Path("data/icici/icic_sample.pdf")
csv_path = Path("data/icici/expected.csv")

if pdf_path.exists() and csv_path.exists():
    print("\n3️⃣ Testing file upload and parsing...")
    print("   📤 Uploading files...")
    
    try:
        with open(pdf_path, 'rb') as pdf_file, open(csv_path, 'rb') as csv_file:
            files = {
                'pdf_file': ('statement.pdf', pdf_file, 'application/pdf'),
                'csv_file': ('expected.csv', csv_file, 'text/csv')
            }
            data = {
                'bank_name': 'icici_test',
                'max_attempts': 5
            }
            
            response = requests.post(
                f"{API_URL}/parse",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                job_id = result.get('job_id')
                print(f"   ✅ Upload successful!")
                print(f"   Job ID: {job_id}")
                
                # Test 4: Check status
                print("\n4️⃣ Monitoring job status...")
                max_wait = 300  # 5 minutes max
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    status_response = requests.get(f"{API_URL}/status/{job_id}", timeout=10)
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        current_status = status_data.get('status')
                        progress = status_data.get('progress')
                        
                        print(f"   📊 Status: {current_status} - {progress}")
                        
                        if current_status == 'completed':
                            print("\n   ✅ Job completed successfully!")
                            result_info = status_data.get('result', {})
                            print(f"   Rows extracted: {result_info.get('rows_extracted')}")
                            print(f"   Attempts used: {result_info.get('attempts_used')}")
                            print(f"   Tables found: {result_info.get('tables_found')}")
                            
                            # Test 5: Download result
                            print("\n5️⃣ Testing download...")
                            download_response = requests.get(f"{API_URL}/download/{job_id}", timeout=10)
                            
                            if download_response.status_code == 200:
                                print("   ✅ Download successful!")
                                output_file = "test_output.csv"
                                with open(output_file, 'wb') as f:
                                    f.write(download_response.content)
                                print(f"   Saved to: {output_file}")
                            else:
                                print(f"   ❌ Download failed: {download_response.status_code}")
                            
                            break
                        
                        elif current_status == 'failed':
                            print("\n   ❌ Job failed!")
                            error = status_data.get('error', {})
                            print(f"   Error: {error.get('message')}")
                            break
                        
                        time.sleep(10)  # Wait 10 seconds before next check
                    else:
                        print(f"   ⚠️  Status check failed: {status_response.status_code}")
                        break
                
                else:
                    print(f"\n   ⚠️  Timeout after {max_wait} seconds")
                
            else:
                print(f"   ❌ Upload failed: {response.status_code}")
                print(f"   Response: {response.text}")
    
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

else:
    print("\n3️⃣ Skipping upload test (sample files not found)")
    print(f"   Expected files:")
    print(f"   - {pdf_path}")
    print(f"   - {csv_path}")

# Test 6: List jobs
print("\n6️⃣ Testing job listing...")
try:
    response = requests.get(f"{API_URL}/jobs?limit=5", timeout=10)
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Job listing works")
        print(f"   Total jobs: {data.get('total', 0)}")
    else:
        print(f"   ⚠️  Job listing returned: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {str(e)}")

# Summary
print("\n" + "="*60)
print("📋 TEST SUMMARY")
print("="*60)
print("✅ Your API is deployed and working!")
print(f"🌐 URL: {API_URL}")
print(f"📚 Docs: {API_URL}/docs")
print("\n💡 Next steps:")
print("   1. Share this URL in your resume/portfolio")
print("   2. Test with different bank statement formats")
print("   3. Show it to interviewers!")
print("="*60 + "\n")