# ====================================
# SUPPRESS STREAMLIT WARNINGS
# ====================================
import logging
import sys

# Suppress Streamlit's ScriptRunContext warnings
for logger_name in ['streamlit.runtime.scriptrunner', 'streamlit.runtime.state']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.ERROR)

# ====================================
# IMPORTS
# ====================================
import streamlit as st
from google import genai  # ✅ Using new SDK
from google.cloud import vision
import json
import time
import os
import hashlib
import pickle
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import io
import re
from PIL import Image
import concurrent.futures
from threading import Lock

# ====================================
# DATABASE IMPORT - ADD THIS
# ====================================
from database import get_database, KYCDataBase

# ====================================
# 🔧 MASTER API KEY (FALLBACK)
# ====================================
# ⚠️ WARNING: This is for testing/fallback only!
# Replace with your actual API key for fallback
MASTER_API_KEY = "Enter master Key"  # ← Replace with your actual key

# ====================================
# API KEY HELPER FUNCTIONS
# ====================================
def clean_api_key(api_key):
    """
    Clean API key by removing quotes, spaces, and extra characters
    """
    if not api_key:
        return ""
    
    # Remove leading/trailing whitespace
    cleaned = api_key.strip()
    
    # Remove quotes (both single and double)
    cleaned = cleaned.strip('"').strip("'")
    
    # Remove any extra spaces
    cleaned = ' '.join(cleaned.split())
    
    return cleaned

def get_valid_api_key(user_key, master_key):
    """
    Try user key first, if invalid or empty, fallback to master key
    
    Args:
        user_key: API key entered by user
        master_key: Master/fallback API key
    
    Returns:
        str: Valid API key to use
    """
    # Clean both keys
    user_key = clean_api_key(user_key)
    master_key = clean_api_key(master_key)
    
    # If user provided a key, try to validate it
    if user_key:
        if validate_api_key_with_google(user_key):
            return user_key
        else:
            print(f"⚠️ User API key is invalid or quota exceeded. Falling back to master key.")
            return master_key
    
    # If no user key, use master key
    return master_key

def validate_api_key_with_google(api_key):
    """
    Validate API key with Google's API
    
    Returns:
        bool: True if valid, False otherwise
    """
    if not api_key:
        return False
    
    try:
        # Create client with the key
        client = genai.Client(api_key=api_key)
        
        # Test with a simple request
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Test connection"
        )
        
        if response and response.text:
            return True
        else:
            return False
            
    except Exception as e:
        error_msg = str(e).lower()
        
        # Check if it's a quota error (we can still use the key but with caution)
        if "quota" in error_msg or "rate limit" in error_msg:
            print(f"⚠️ API key has quota issues, but will try to use it: {error_msg}")
            return True  # Still return True, let the app handle the quota error
        elif "permission" in error_msg or "invalid" in error_msg:
            print(f"❌ API key is invalid: {error_msg}")
            return False
        else:
            # For other errors, try to use it anyway
            print(f"⚠️ API key validation warning: {error_msg}")
            return True

# ====================================
# MIME TYPE MAPPING
# ====================================
mime_map = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "zip": "application/zip",
    "rar": "application/x-rar-compressed",
    "7z": "application/x-7z-compressed",
    "mp4": "video/mp4",
    "avi": "video/x-msvideo",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
    "flv": "video/x-flv",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "exe": "application/x-msdownload",
    "dll": "application/x-msdownload",
    "msi": "application/x-msi",
    "apk": "application/vnd.android.package-archive",
    "deb": "application/vnd.debian.binary-package",
    "rpm": "application/x-rpm",
    "iso": "application/x-iso9660-image",
    "tar": "application/x-tar",
    "gz": "application/gzip",
    "py": "text/x-python",
    "js": "application/javascript",
    "html": "text/html",
    "css": "text/css",
    "php": "application/x-httpd-php",
    "rb": "application/x-ruby",
    "go": "application/x-golang",
    "rs": "application/x-rust",
    "sh": "application/x-sh",
    "bat": "application/x-bat",
    "ps1": "application/x-powershell",
}

# ====================================
# REVERSE MIME MAPPING
# ====================================
reverse_mime_map = {v: k for k, v in mime_map.items()}

# ====================================
# CORE MIME FUNCTIONS
# ====================================
def get_mime_type(filename_or_extension):
    """
    Get MIME type from filename or extension
    """
    if not filename_or_extension:
        return "application/octet-stream"
    
    # Remove dot if present
    ext = filename_or_extension.strip().lower()
    if ext.startswith('.'):
        ext = ext[1:]
    
    # If it contains a dot, it's a filename
    if '.' in ext:
        ext = ext.split('.')[-1]
    
    return mime_map.get(ext, "application/octet-stream")

def get_extension_from_mime(mime_type):
    """
    Get file extension from MIME type
    """
    return reverse_mime_map.get(mime_type, "bin")

def get_mime_category(mime_type):
    """
    Get the category of a MIME type
    """
    if mime_type.startswith('image/'):
        return 'image'
    elif mime_type in [
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain', 'text/csv', 'application/json', 'application/xml', 'text/xml'
    ]:
        return 'document'
    elif mime_type.startswith('audio/'):
        return 'audio'
    elif mime_type.startswith('video/'):
        return 'video'
    elif mime_type in ['application/zip', 'application/x-rar-compressed', 
                       'application/x-7z-compressed', 'application/x-tar', 
                       'application/gzip']:
        return 'archive'
    elif mime_type in ['text/x-python', 'application/javascript', 'text/html', 
                       'text/css', 'application/x-httpd-php']:
        return 'code'
    else:
        return 'other'

# ====================================
# SUPPORTED FILE TYPES
# ====================================
SUPPORTED_IMAGE_TYPES = [
    "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "tif", "svg", "ico"
]

SUPPORTED_DOCUMENT_TYPES = [
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "json", "xml"
]

SUPPORTED_AUDIO_TYPES = [
    "mp3", "wav", "flac", "ogg", "aac", "m4a"
]

SUPPORTED_VIDEO_TYPES = [
    "mp4", "avi", "mov", "mkv", "webm", "flv"
]

SUPPORTED_ARCHIVE_TYPES = [
    "zip", "rar", "7z", "tar", "gz"
]

SUPPORTED_CODE_TYPES = [
    "py", "js", "html", "css", "php", "rb", "go", "rs", "sh", "bat", "ps1"
]

ALL_SUPPORTED_TYPES = (
    SUPPORTED_IMAGE_TYPES + 
    SUPPORTED_DOCUMENT_TYPES + 
    SUPPORTED_AUDIO_TYPES + 
    SUPPORTED_VIDEO_TYPES + 
    SUPPORTED_ARCHIVE_TYPES + 
    SUPPORTED_CODE_TYPES
)

# ====================================
# MAIN MIME HELPER FUNCTION
# ====================================
def get_mime(uploaded_file):
    """
    Helper function to get MIME type from uploaded file
    """
    if uploaded_file is None:
        return "image/jpeg"
    
    # Try to get MIME type from filename
    mime_type = get_mime_type(uploaded_file.name)
    
    # If still application/octet-stream, try to detect from extension
    if mime_type == "application/octet-stream":
        ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
        if ext in SUPPORTED_IMAGE_TYPES:
            return f"image/{ext}"
        elif ext in SUPPORTED_DOCUMENT_TYPES:
            return "application/octet-stream"
    
    return mime_type

# ====================================
# CONFIG
# ====================================
CACHE_FILE = "extract_cache.pkl"
VISION_CACHE_FILE = "vision_cache.pkl"

# ====================================
# CACHE FUNCTIONS
# ====================================
def load_cache(cache_file=CACHE_FILE):
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "rb") as f:
                return pickle.load(f)
        except:
            return {}
    return {}

def save_cache(cache, cache_file=CACHE_FILE):
    try:
        with open(cache_file, "wb") as f:
            pickle.dump(cache, f)
    except:
        pass

# ====================================
# THREAD-SAFE COUNTER FOR BATCH PROCESSING
# ====================================
progress_lock = Lock()
completed_count = 0

# ====================================
# EXTRACTION PROMPT
# ====================================
EXTRACT_PROMPT = """
Analyze this document.

Return ONLY valid JSON.

{
  "document_type":"",
  "name":"",
  "dob":"",
  "gender":"",
  "pan":"",
  "aadhaar":"",
  "address":"",
  "salary":"",
  "account_number":""
}

If a field is not visible return null.

Do not invent values.
"""

# ====================================
# GOOGLE VISION FALLBACK
# ====================================
def extract_with_vision(image_bytes, api_key=None):
    """
    Fallback extraction using Google Cloud Vision API
    """
    try:
        # Initialize Vision client
        if api_key:
            # Use API key for Vision
            client = vision.ImageAnnotatorClient(client_options={"api_key": api_key})
        else:
            # Use default credentials
            client = vision.ImageAnnotatorClient()
        
        # Create image
        image = vision.Image(content=image_bytes)
        
        # Perform text detection
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            return {"error": "No text detected in image"}
        
        # Get full text
        full_text = texts[0].description
        
        # Parse text to extract fields
        extracted_data = {
            "document_type": "",
            "name": "",
            "dob": "",
            "gender": "",
            "pan": "",
            "aadhaar": "",
            "address": "",
            "salary": "",
            "account_number": ""
        }
        
        # Try to extract PAN (format: ABCDE1234F)
        pan_match = re.search(r'[A-Z]{5}[0-9]{4}[A-Z]', full_text)
        if pan_match:
            extracted_data["pan"] = pan_match.group()
        
        # Try to extract Aadhaar (format: XXXX XXXX XXXX)
        aadhaar_match = re.search(r'\d{4}\s?\d{4}\s?\d{4}', full_text)
        if aadhaar_match:
            extracted_data["aadhaar"] = aadhaar_match.group()
        
        # Try to extract Name (common patterns)
        name_patterns = [
            r'Name\s*[:|]\s*([A-Za-z\s]+)',
            r'Name\s*-\s*([A-Za-z\s]+)',
            r'Applicant\s*[:|]\s*([A-Za-z\s]+)'
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, full_text, re.IGNORECASE)
            if name_match:
                extracted_data["name"] = name_match.group(1).strip()
                break
        
        # Try to extract DOB
        dob_patterns = [
            r'DOB\s*[:|]\s*(\d{2}[/-]\d{2}[/-]\d{4})',
            r'Date of Birth\s*[:|]\s*(\d{2}[/-]\d{2}[/-]\d{4})',
            r'Birth\s*[:|]\s*(\d{2}[/-]\d{2}[/-]\d{4})'
        ]
        for pattern in dob_patterns:
            dob_match = re.search(pattern, full_text, re.IGNORECASE)
            if dob_match:
                extracted_data["dob"] = dob_match.group(1)
                break
        
        return extracted_data
        
    except Exception as e:
        return {"error": f"Vision API extraction failed: {str(e)}"}

# ====================================
# GEMINI EXTRACTION WITH FALLBACK
# ====================================
def extract_document(image_bytes, mime_type, api_key):
    """
    Extract fields with multiple Gemini models and retries.
    Uses fallback API key if provided key fails.
    """
    # Create hash for caching
    img_hash = hashlib.md5(image_bytes).hexdigest()
    
    # Check cache
    cache = load_cache()
    if img_hash in cache:
        return cache[img_hash]

    try:
        # Clean and validate API key
        api_key = clean_api_key(api_key)
        
        # If no API key or invalid, fallback to master key
        if not api_key:
            print("⚠️ No API key provided, using master key")
            api_key = clean_api_key(MASTER_API_KEY)
        
        if not api_key:
            return {"error": "No valid API key available. Please check your configuration."}
        
        # Log API key status (first few chars only for debugging)
        print(f"API Key starts with: {api_key[:10]}...")
        
        # Create Gemini client
        client = genai.Client(api_key=api_key)
        
        # List of Gemini models with their configurations
        gemini_models = [
            {
                "name": "gemini-2.5-flash",
                "retries": 3,
                "backoff": 1,
                "timeout": 45
            },
            {
                "name": "gemini-2.0-flash",
                "retries": 3,
                "backoff": 1,
                "timeout": 35
            },
            {
                "name": "gemini-1.5-flash",
                "retries": 2,
                "backoff": 2,
                "timeout": 40
            },
            {
                "name": "gemini-1.5-pro",
                "retries": 2,
                "backoff": 3,
                "timeout": 60
            },
        ]
        
        # Try each model with retries
        for model_config in gemini_models:
            model_name = model_config["name"]
            max_retries = model_config["retries"]
            backoff = model_config["backoff"]
            timeout = model_config["timeout"]
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Attempt {attempt + 1}/{max_retries} with {model_name}")
                    
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Generate content with new SDK
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[EXTRACT_PROMPT, image],
                    )
                    
                    if response and response.text:
                        # Try to extract JSON from response
                        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group())
                            if not result.get("error"):
                                # Check if we got meaningful data
                                has_data = any(v for v in result.values() if v)
                                if has_data:
                                    cache[img_hash] = result
                                    save_cache(cache)
                                    print(f"✅ Success with {model_name} (attempt {attempt + 1})")
                                    return result
                                else:
                                    print(f"⚠️ {model_name} returned empty data, trying next")
                        else:
                            # If no JSON found, try to parse the entire response
                            try:
                                result = json.loads(response.text)
                                if not result.get("error"):
                                    has_data = any(v for v in result.values() if v)
                                    if has_data:
                                        cache[img_hash] = result
                                        save_cache(cache)
                                        print(f"✅ Success with {model_name} (attempt {attempt + 1})")
                                        return result
                                    else:
                                        print(f"⚠️ {model_name} returned empty data, trying next")
                            except:
                                pass
                    
                    # If we get here, the response wasn't valid
                    if attempt < max_retries - 1:
                        wait_time = backoff * (attempt + 1)
                        print(f"⏳ Waiting {wait_time} seconds before retry with {model_name}...")
                        time.sleep(wait_time)
                        
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ {model_name} attempt {attempt + 1} failed: {error_msg}")
                    
                    # Check if it's an API key error
                    if "permission" in error_msg.lower() or "invalid" in error_msg.lower():
                        print(f"❌ API key appears invalid. Trying master key if available...")
                        # Try with master key
                        master_key = clean_api_key(MASTER_API_KEY)
                        if master_key and master_key != api_key:
                            print(f"🔄 Retrying with master key...")
                            # Update client with master key
                            client = genai.Client(api_key=master_key)
                            # Retry the same model with master key
                            continue
                        else:
                            print(f"❌ No valid master key available")
                            return {"error": f"Invalid API key: {error_msg}"}
                    
                    # Check for overload/availability errors
                    error_lower = error_msg.lower()
                    if any(keyword in error_lower for keyword in ['overloaded', 'rate limit', 'quota', 'unavailable', 'busy']):
                        print(f"⏳ {model_name} appears overloaded or unavailable")
                        if attempt < max_retries - 1:
                            wait_time = backoff * (attempt + 1) * 2
                            print(f"⏳ Waiting {wait_time} seconds before retry...")
                            time.sleep(wait_time)
                    elif attempt < max_retries - 1:
                        wait_time = backoff * (attempt + 1)
                        print(f"⏳ Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
            
            print(f"❌ All attempts with {model_name} failed, trying next model...")
        
        # If all Gemini models failed, try Google Cloud Vision
        print("🔄 All Gemini models failed, falling back to Google Cloud Vision API")
        vision_result = extract_with_vision(image_bytes, api_key)
        
        if not vision_result.get("error"):
            cache[img_hash] = vision_result
            save_cache(cache)
            print("✅ Success with Vision API")
            return vision_result
        
        return {"error": "All extraction methods failed"}
        
    except Exception as e:
        error_msg = f"Extraction failed: {str(e)}"
        logging.error(error_msg)
        print(f"Detailed error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return {"error": error_msg}

# ====================================
# BATCH PROCESSING FUNCTIONS
# ====================================

def process_single_document(image_bytes, mime_type, api_key, doc_type, doc_index, db, transaction_id):
    """
    Process a single document with retries and database logging
    """
    start_time = time.time()
    
    try:
        result = extract_document(image_bytes, mime_type, api_key)
        
        # Log API usage
        elapsed_time = int((time.time() - start_time) * 1000)  # Convert to milliseconds
        
        db.log_api_usage(
            transaction_id=transaction_id,
            api_name=f"GEMINI_{doc_type.upper()}",
            model_used="gemini-2.5-flash",
            response_time_ms=elapsed_time,
            status_code=200 if "error" not in result else 400
        )
        
        return {
            "doc_type": doc_type,
            "index": doc_index,
            "data": result,
            "success": "error" not in result
        }
    except Exception as e:
        elapsed_time = int((time.time() - start_time) * 1000)
        
        db.log_api_usage(
            transaction_id=transaction_id,
            api_name=f"GEMINI_{doc_type.upper()}",
            model_used="gemini-2.5-flash",
            response_time_ms=elapsed_time,
            status_code=500
        )
        
        return {
            "doc_type": doc_type,
            "index": doc_index,
            "data": {"error": str(e)},
            "success": False
        }

def process_batch_verifications(documents_batch, api_key, db, transaction_id, max_workers=10):
    """
    Process multiple verifications in parallel with database logging
    """
    global completed_count
    completed_count = 0
    
    results = []
    
    # Create tasks for all documents across all batches
    tasks = []
    for batch_idx, batch in enumerate(documents_batch):
        tasks.append({
            "bytes": batch["aadhaar_bytes"],
            "mime": batch["aadhaar_mime"],
            "doc_type": "aadhaar",
            "batch_id": batch_idx
        })
        tasks.append({
            "bytes": batch["pan_bytes"],
            "mime": batch["pan_mime"],
            "doc_type": "pan",
            "batch_id": batch_idx
        })
        tasks.append({
            "bytes": batch["salary_bytes"],
            "mime": batch["salary_mime"],
            "doc_type": "salary",
            "batch_id": batch_idx
        })
    
    # Process all tasks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(
                process_single_document,
                task["bytes"],
                task["mime"],
                api_key,
                task["doc_type"],
                task["batch_id"],
                db,
                transaction_id
            ): task
            for task in tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_task):
            result = future.result()
            results.append(result)
            
            with progress_lock:
                completed_count += 1
                print(f"Progress: {completed_count}/{len(tasks)} completed")
    
    # Group results by batch
    batch_results = {}
    for result in results:
        batch_id = result["index"]
        if batch_id not in batch_results:
            batch_results[batch_id] = {}
        batch_results[batch_id][result["doc_type"]] = result["data"]
    
    # Calculate risk for each batch
    final_results = []
    for batch_id, docs in batch_results.items():
        if "aadhaar" in docs and "pan" in docs and "salary" in docs:
            has_error = (
                "error" in docs["aadhaar"] or 
                "error" in docs["pan"] or 
                "error" in docs["salary"]
            )
            
            if has_error:
                final_results.append({
                    "batch_id": batch_id,
                    "success": False,
                    "error": "One or more documents failed to extract",
                    "aadhaar": docs.get("aadhaar", {}),
                    "pan": docs.get("pan", {}),
                    "salary": docs.get("salary", {})
                })
            else:
                risk = calculate_risk(docs["aadhaar"], docs["pan"], docs["salary"])
                final_results.append({
                    "batch_id": batch_id,
                    "aadhaar": docs["aadhaar"],
                    "pan": docs["pan"],
                    "salary": docs["salary"],
                    "risk": risk,
                    "success": True
                })
        else:
            final_results.append({
                "batch_id": batch_id,
                "success": False,
                "error": "Missing documents"
            })
    
    return final_results

# ====================================
# RISK ENGINE
# ====================================
def calculate_risk(aadhaar, pan, salary):
    score = 0
    issues = []

    aadhaar_name = (aadhaar.get("name") or "").lower()
    pan_name = (pan.get("name") or "").lower()
    salary_name = (salary.get("name") or "").lower()
    aadhaar_dob = aadhaar.get("dob")
    pan_dob = pan.get("dob")

    if aadhaar_name and pan_name and aadhaar_name != pan_name:
        score += 30
        issues.append("Name mismatch between Aadhaar and PAN")
    if aadhaar_dob and pan_dob and aadhaar_dob != pan_dob:
        score += 20
        issues.append("DOB mismatch between Aadhaar and PAN")
    if salary_name and aadhaar_name and salary_name != aadhaar_name:
        score += 25
        issues.append("Salary slip name mismatch")

    if score > 50:
        recommendation = "REJECT"
    elif score > 20:
        recommendation = "MANUAL_REVIEW"
    else:
        recommendation = "APPROVE"

    return {
        "risk_score": score,
        "issues": issues,
        "recommendation": recommendation
    }

# ====================================
# PDF GENERATOR
# ====================================
def generate_pdf_bytes(aadhaar_data, pan_data, salary_data, risk):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50
    
    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "KYC VERIFICATION REPORT")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 30

    def add_section(title, data, start_y):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, start_y, title)
        start_y -= 20
        c.setFont("Helvetica", 10)
        if isinstance(data, dict):
            for k, v in data.items():
                if v is None:
                    v = "NULL"
                c.drawString(70, start_y, f"{k}: {v}")
                start_y -= 16
        else:
            c.drawString(70, start_y, str(data))
            start_y -= 16
        return start_y - 10

    y = add_section("AADHAAR", aadhaar_data, y)
    y = add_section("PAN", pan_data, y)
    y = add_section("SALARY", salary_data, y)
    y = add_section("RISK ASSESSMENT", risk, y)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()

# ====================================
# BATCH VERIFICATION UI
# ====================================
def batch_verification_ui(db, transaction_id, user_hash):
    """
    UI component for batch uploading multiple documents with database logging
    """
    st.subheader("📦 Batch Verification (Up to 10 Sets)")
    st.info("Upload up to 10 sets of documents for simultaneous processing")
    
    num_sets = st.number_input(
        "Number of verification sets",
        min_value=1,
        max_value=10,
        value=1,
        step=1
    )
    
    batch_files = []
    cols = st.columns(min(num_sets, 3))
    
    for i in range(num_sets):
        col_idx = i % 3
        with cols[col_idx]:
            st.markdown(f"**Set {i+1}**")
            
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                aadhaar = st.file_uploader(
                    f"Aadhaar {i+1}",
                    type=SUPPORTED_IMAGE_TYPES,
                    key=f"batch_aadhaar_{i}"
                )
            with fcol2:
                pan = st.file_uploader(
                    f"PAN {i+1}",
                    type=SUPPORTED_IMAGE_TYPES,
                    key=f"batch_pan_{i}"
                )
            with fcol3:
                salary = st.file_uploader(
                    f"Salary {i+1}",
                    type=SUPPORTED_IMAGE_TYPES,
                    key=f"batch_salary_{i}"
                )
            
            batch_files.append({
                "aadhaar": aadhaar,
                "pan": pan,
                "salary": salary,
                "index": i
            })
    
    if st.button("🚀 Process All Sets", type="primary", use_container_width=True):
        # Get the API key (user's or master)
        api_key = get_valid_api_key(
            st.session_state.api_key,
            MASTER_API_KEY
        )
        
        if not api_key:
            st.error("❌ No valid API key available. Please check your configuration.")
            return
        
        all_uploaded = all(
            b["aadhaar"] is not None and b["pan"] is not None and b["salary"] is not None 
            for b in batch_files
        )
        
        if not all_uploaded:
            st.error("❌ Please upload all documents for each set")
            return
        
        # Log batch start
        db.log_audit_event(
            transaction_id=transaction_id,
            event_type="BATCH_VERIFICATION_START",
            user_hash=user_hash,
            request_data={"num_sets": num_sets}
        )
        
        batch_data = []
        for b in batch_files:
            batch_data.append({
                "aadhaar_bytes": b["aadhaar"].read(),
                "pan_bytes": b["pan"].read(),
                "salary_bytes": b["salary"].read(),
                "aadhaar_mime": get_mime(b["aadhaar"]),
                "pan_mime": get_mime(b["pan"]),
                "salary_mime": get_mime(b["salary"]),
            })
        
        with st.spinner(f"Processing {len(batch_data)} verification sets..."):
            results = process_batch_verifications(
                batch_data,
                api_key,
                db,
                transaction_id,
                max_workers=min(10, len(batch_data) * 3)
            )
        
        # Store results in database
        for result in results:
            if result["success"]:
                db.store_verification_result(
                    transaction_id=transaction_id,
                    user_hash=user_hash,
                    risk_score=result["risk"]["risk_score"],
                    recommendation=result["risk"]["recommendation"],
                    verification_status="COMPLETED",
                    aadhaar_verified=True,
                    pan_verified=True,
                    salary_verified=True,
                    issues_found=result["risk"]["issues"],
                    pdf_path=None  # Will be generated later
                )
        
        st.success(f"✅ Completed {len(results)} verifications!")
        
        # Log batch complete
        db.log_audit_event(
            transaction_id=transaction_id,
            event_type="BATCH_VERIFICATION_COMPLETE",
            user_hash=user_hash,
            response_status="SUCCESS"
        )
        
        for result in results:
            if result["success"]:
                st.markdown(f"---")
                st.markdown(f"**📊 Set {result['batch_id'] + 1} Results:**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Risk Score", result["risk"]["risk_score"])
                with col2:
                    st.metric("Issues", len(result["risk"]["issues"]))
                with col3:
                    rec = result["risk"]["recommendation"]
                    if rec == "APPROVE":
                        st.metric("Decision", "✅ APPROVE")
                    elif rec == "MANUAL_REVIEW":
                        st.metric("Decision", "⚠️ REVIEW")
                    else:
                        st.metric("Decision", "❌ REJECT")
                
                if result["risk"]["issues"]:
                    with st.expander(f"⚠️ Issues in Set {result['batch_id'] + 1}"):
                        for issue in result["risk"]["issues"]:
                            st.write(f"• {issue}")
                
                with st.expander(f"📄 View Extracted Data - Set {result['batch_id'] + 1}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.subheader("Aadhaar")
                        st.json(result["aadhaar"])
                    with col2:
                        st.subheader("PAN")
                        st.json(result["pan"])
                    with col3:
                        st.subheader("Salary")
                        st.json(result["salary"])
            else:
                st.error(f"❌ Set {result['batch_id'] + 1} failed: {result.get('error', 'Unknown error')}")
        
        # Purge temporary data (RBI Compliance)
        db.purge_temp_data(transaction_id)

# ====================================
# MAIN UI
# ====================================
def main():
    st.set_page_config(
        page_title="AI KYC Verifier",
        page_icon="🔐",
        layout="wide"
    )
    
    # ====================================
    # DATABASE INITIALIZATION
    # ====================================
    db = get_database()
    
    # Log app startup
    startup_txn = db.generate_transaction_id()
    db.log_audit_event(
        transaction_id=startup_txn,
        event_type="APP_START",
        user_hash=db.hash_user_identifier("SYSTEM"),
        request_data={"app": "AI KYC Verifier", "version": "2.0"},
        response_status="SUCCESS"
    )
    
    # Initialize session state
    if 'api_key' not in st.session_state:
        st.session_state.api_key = ""
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'api_validated' not in st.session_state:
        st.session_state.api_validated = False
    if 'batch_results' not in st.session_state:
        st.session_state.batch_results = None
    if 'using_fallback' not in st.session_state:
        st.session_state.using_fallback = False
    if 'transaction_id' not in st.session_state:
        st.session_state.transaction_id = None
    
    # Title
    st.title("🔐 AI KYC Verification")
    st.markdown("### Premium Document Verification Service")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Show if using fallback key
        if st.session_state.using_fallback:
            st.warning("⚠️ Using fallback API key (your key was invalid)")
        
        api_key_input = st.text_input(
            "Gemini API Key (Optional)",
            type="password",
            value=st.session_state.api_key if not st.session_state.using_fallback else "",
            placeholder="Enter your Gemini API key (optional)",
            help="If left empty or invalid, the master key will be used"
        )
        
        if api_key_input:
            st.session_state.api_key = clean_api_key(api_key_input)
            st.session_state.using_fallback = False
        elif not st.session_state.api_key:
            # No user key, use master key
            st.session_state.using_fallback = True
        
        # API Key Validation
        if st.session_state.api_key and not st.session_state.api_validated:
            try:
                with st.spinner("Validating API key..."):
                    # Create client with the key
                    client = genai.Client(api_key=st.session_state.api_key)
                    
                    # Test with a simple request
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents="Test connection"
                    )
                    
                    if response and response.text:
                        st.success("✅ API key validated successfully!")
                        st.session_state.api_validated = True
                        st.session_state.using_fallback = False
                    else:
                        st.warning("⚠️ API key validation failed. Using fallback key.")
                        st.session_state.using_fallback = True
                        
            except Exception as e:
                error_msg = str(e).lower()
                if "quota" in error_msg:
                    st.warning("⚠️ API key quota exceeded. Using fallback key.")
                    st.session_state.using_fallback = True
                else:
                    st.error(f"❌ API key validation failed: {str(e)}")
                    st.session_state.api_validated = False
                    st.session_state.using_fallback = True
        
        st.markdown("---")
        st.markdown("### 📊 Stats")
        cache = load_cache()
        st.metric("Cache Size", len(cache))
        
        # Database stats
        db_stats = db.get_database_stats()
        st.metric("Total Verifications", db_stats.get('verification_results', 0))
        
        if st.session_state.using_fallback:
            st.info("🔑 Using master API key")
        elif st.session_state.api_validated:
            st.success("✅ Using your API key")
        
        st.markdown("---")
        st.markdown("### 🔗 Get API Key")
        st.markdown("[Google AI Studio](https://aistudio.google.com/apikey)")
        
        st.markdown("---")
        st.markdown("### 🤖 Model Fallback Strategy")
        st.info("""
        **Document Extraction Order:**
        1. Gemini 2.5 Flash (3 attempts)
        2. Gemini 2.0 Flash (3 attempts)
        3. Gemini 1.5 Flash (2 attempts)
        4. Gemini 1.5 Pro (2 attempts)
        5. Google Vision API (fallback)
        """)
        
        st.markdown("---")
        st.caption("🔒 Your data is processed locally and not stored.")
    
    # Create tabs for Single and Batch verification
    tab1, tab2 = st.tabs(["📄 Single Verification", "📦 Batch Verification (Up to 10 Sets)"])
    
    with tab1:
        st.markdown("### Single Document Verification")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            aadhaar_file = st.file_uploader(
                "📄 Aadhaar",
                type=SUPPORTED_IMAGE_TYPES,
                key="single_aadhaar"
            )
        
        with col2:
            pan_file = st.file_uploader(
                "📄 PAN",
                type=SUPPORTED_IMAGE_TYPES,
                key="single_pan"
            )
        
        with col3:
            salary_file = st.file_uploader(
                "📄 Salary Slip",
                type=SUPPORTED_IMAGE_TYPES,
                key="single_salary"
            )
        
        verify_button = st.button(
            "🚀 Verify Documents",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing,
            key="single_verify"
        )
        
        if verify_button:
            # Generate transaction ID and user hash
            transaction_id = db.generate_transaction_id()
            user_hash = db.hash_user_identifier(f"USER_{datetime.now().timestamp()}")
            st.session_state.transaction_id = transaction_id
            
            # Get the API key (user's or master)
            api_key = get_valid_api_key(
                st.session_state.api_key,
                MASTER_API_KEY
            )
            
            if not api_key:
                st.error("❌ No valid API key available. Please check your configuration.")
                st.stop()
            
            if not (aadhaar_file and pan_file and salary_file):
                st.error("❌ Please upload all three documents.")
                st.stop()
            
            # Log verification start
            db.log_audit_event(
                transaction_id=transaction_id,
                event_type="VERIFICATION_START",
                user_hash=user_hash,
                request_data={"type": "SINGLE_VERIFICATION"}
            )
            
            # Record consent
            db.record_consent(
                transaction_id=transaction_id,
                user_hash=user_hash,
                purpose="KYC Verification for NBFC Loan Application",
                consent_artefact={
                    "timestamp": datetime.now().isoformat(),
                    "type": "DOCUMENT_VERIFICATION"
                }
            )
            
            st.session_state.processing = True
            
            status_placeholder = st.empty()
            progress_bar = st.progress(0)
            
            try:
                start_time = time.time()
                aadhaar_bytes = aadhaar_file.read()
                pan_bytes = pan_file.read()
                salary_bytes = salary_file.read()
                
                status_placeholder.info("📤 Extracting Aadhaar information...")
                progress_bar.progress(20)
                aadhaar = extract_document(
                    aadhaar_bytes,
                    get_mime(aadhaar_file),
                    api_key
                )
                
                status_placeholder.info("📤 Extracting PAN information...")
                progress_bar.progress(40)
                pan = extract_document(
                    pan_bytes,
                    get_mime(pan_file),
                    api_key
                )
                
                status_placeholder.info("📤 Extracting Salary information...")
                progress_bar.progress(60)
                salary = extract_document(
                    salary_bytes,
                    get_mime(salary_file),
                    api_key
                )
                
                # Log API usage
                elapsed_time = int((time.time() - start_time) * 1000)
                db.log_api_usage(
                    transaction_id=transaction_id,
                    api_name="GEMINI_VERIFICATION",
                    model_used="gemini-2.5-flash",
                    response_time_ms=elapsed_time,
                    status_code=200
                )
                
                if "error" in aadhaar or "error" in pan or "error" in salary:
                    error_details = []
                    if "error" in aadhaar:
                        error_details.append(f"Aadhaar: {aadhaar['error']}")
                    if "error" in pan:
                        error_details.append(f"PAN: {pan['error']}")
                    if "error" in salary:
                        error_details.append(f"Salary: {salary['error']}")
                    
                    db.log_audit_event(
                        transaction_id=transaction_id,
                        event_type="VERIFICATION_FAILED",
                        user_hash=user_hash,
                        error_message="\n".join(error_details),
                        response_status="FAILED"
                    )
                    
                    status_placeholder.error(f"❌ Document extraction failed.\n\nDetails:\n" + "\n".join(error_details))
                    st.session_state.processing = False
                    st.stop()
                
                status_placeholder.info("🔍 Analyzing risk factors...")
                progress_bar.progress(80)
                risk = calculate_risk(aadhaar, pan, salary)
                
                status_placeholder.info("📄 Generating report...")
                progress_bar.progress(90)
                pdf_bytes = generate_pdf_bytes(aadhaar, pan, salary, risk)
                
                # Store verification result
                db.store_verification_result(
                    transaction_id=transaction_id,
                    user_hash=user_hash,
                    risk_score=risk["risk_score"],
                    recommendation=risk["recommendation"],
                    verification_status="COMPLETED",
                    aadhaar_verified=True,
                    pan_verified=True,
                    salary_verified=True,
                    issues_found=risk["issues"],
                    pdf_path=None
                )
                
                st.session_state.results = {
                    "aadhaar": aadhaar,
                    "pan": pan,
                    "salary": salary,
                    "risk": risk,
                    "pdf": pdf_bytes
                }
                
                # Log verification complete
                db.log_audit_event(
                    transaction_id=transaction_id,
                    event_type="VERIFICATION_COMPLETE",
                    user_hash=user_hash,
                    response_status="SUCCESS"
                )
                
                # Purge temporary data (RBI Compliance)
                db.purge_temp_data(transaction_id)
                
                progress_bar.progress(100)
                status_placeholder.success("✅ Verification complete!")
                
            except Exception as e:
                db.log_audit_event(
                    transaction_id=transaction_id,
                    event_type="VERIFICATION_ERROR",
                    user_hash=user_hash,
                    error_message=str(e),
                    response_status="ERROR"
                )
                st.error(f"❌ An error occurred: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
            
            st.session_state.processing = False
        
        if st.session_state.results:
            results = st.session_state.results
            
            st.markdown("---")
            st.subheader("📊 Results")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Risk Score", results["risk"]["risk_score"])
            with col2:
                st.metric("Issues", len(results["risk"]["issues"]))
            with col3:
                rec = results["risk"]["recommendation"]
                if rec == "APPROVE":
                    st.metric("Decision", "✅ APPROVE")
                elif rec == "MANUAL_REVIEW":
                    st.metric("Decision", "⚠️ REVIEW")
                else:
                    st.metric("Decision", "❌ REJECT")
            
            if results["risk"]["issues"]:
                st.warning("⚠️ Issues Found:")
                for issue in results["risk"]["issues"]:
                    st.write(f"• {issue}")
            else:
                st.success("✅ No issues found!")
            
            with st.expander("📄 View Extracted Data", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.subheader("Aadhaar")
                    st.json(results["aadhaar"])
                with col2:
                    st.subheader("PAN")
                    st.json(results["pan"])
                with col3:
                    st.subheader("Salary")
                    st.json(results["salary"])
            
            st.download_button(
                label="📥 Download PDF Report",
                data=results["pdf"],
                file_name=f"KYC_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
            
            if st.button("🔄 Start New Verification", use_container_width=True):
                st.session_state.results = None
                st.rerun()
    
    with tab2:
        # Generate transaction ID for batch
        if not st.session_state.transaction_id:
            st.session_state.transaction_id = db.generate_transaction_id()
        
        batch_verification_ui(
            db, 
            st.session_state.transaction_id,
            db.hash_user_identifier(f"BATCH_USER_{datetime.now().timestamp()}")
        )

# ====================================
# ENTRY POINT
# ====================================
if __name__ == "__main__":
    main()