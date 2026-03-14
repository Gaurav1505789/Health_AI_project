from pathlib import Path
import pickle
import re
import os
from difflib import SequenceMatcher
import json
from datetime import datetime, timedelta
import hashlib
import math
import base64
import urllib.request
import urllib.parse
import socket
import sys

import pandas as pd
from flask import Flask, jsonify, request, send_file
import requests

# Verify required packages at startup
def _verify_dependencies():
    """Verify that all required packages are installed"""
    missing = []
    
    # Check requests library
    try:
        import requests
        print(f"[OK] requests library loaded")
    except ImportError:
        missing.append("requests")
        print("[WARN] requests library not found - MedlinePlus integration will fail")
    
    # Check pdfplumber
    try:
        import pdfplumber
        print(f"[OK] pdfplumber {pdfplumber.__version__} loaded")
    except ImportError:
        missing.append("pdfplumber")
        print("[WARN] pdfplumber not found - PDF analysis will fail")
    
    # Check PyPDF2
    try:
        import PyPDF2
        print(f"[OK] PyPDF2 loaded")
    except ImportError:
        missing.append("PyPDF2")
        print("[WARN] PyPDF2 not found")
    
    if missing:
        print(f"\n[ERROR] Missing packages: {', '.join(missing)}")
        print(f"[FIX] Run: pip install {' '.join(missing)}")
        print("[NOTE] Flask will still start but some features may fail\n")
    
    return len(missing) == 0

try:
    from google import genai
except ImportError:
    genai = None

# Import the medical report analyzer
from report_analyzer import analyze_medical_report

app = Flask(__name__)

# Verify dependencies when app starts
print("\n" + "="*60)
print("HEALTH AI - STARTING FLASK SERVER")
print("="*60)
_verify_dependencies()
print("="*60 + "\n")
app.secret_key = "health_ai_secret_key_2026"

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
EMERGENCY_ALERTS_FILE = DATA_DIR / "emergency_alerts.json"
MODEL_PATH = BASE_DIR / "model" / "model.pkl"
SYMPTOM_LIST_PATH = BASE_DIR / "model" / "symptom_list.pkl"
CRITICAL_SYMPTOMS = {
    "chest pain",
    "difficulty breathing",
    "loss of consciousness",
    "severe bleeding",
    "seizures",
}
FALLBACK_CHAT_REPLY = "I'm currently unable to respond. Please try again later."
HEALTH_ASSISTANT_PROMPT = (
    "You are a helpful AI health assistant. Provide safe, general health guidance, "
    "lifestyle advice, and symptom explanations. Do not provide medical diagnoses. "
    "Always suggest consulting a doctor for serious, persistent, or emergency symptoms."
)


def _load_csv_with_fallback(primary_name, fallback_names):
    """Load CSV by primary name and fallback names when needed."""
    for name in [primary_name] + fallback_names:
        file_path = DATA_DIR / name
        if file_path.exists():
            return pd.read_csv(file_path)
    raise FileNotFoundError(f"Could not find {primary_name} in {DATA_DIR}")


def _find_column(df, candidates):
    """Find a matching column name ignoring case and underscore/space differences."""
    normalized_map = {}
    for col in df.columns:
        key = col.strip().lower().replace("_", " ")
        key = re.sub(r"\s+", " ", key)
        normalized_map[key] = col

    for candidate in candidates:
        key = candidate.strip().lower().replace("_", " ")
        key = re.sub(r"\s+", " ", key)
        if key in normalized_map:
            return normalized_map[key]

    raise KeyError(f"Could not find columns: {candidates}")


def _normalize_disease(value):
    """Normalize disease text for cross-dataset matching."""
    text = str(value).strip().lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _safe_string(value):
    """Convert values to string while handling nulls safely."""
    if pd.isna(value):
        return ""
    return str(value)


def _format_confidence(probability):
    """Format confidence as a percentage string."""
    return f"{round(float(probability) * 100)}%"


def _normalize_text(value):
    """Normalize symptom text for matching and inference."""
    text = str(value).strip().lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ======================== USER AUTHENTICATION ========================

def _ensure_users_file_exists():
    """Create users.json if it doesn't exist."""
    if not USERS_FILE.exists():
        USERS_FILE.write_text(json.dumps({"users": []}, indent=2))


def _hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_users():
    """Load all users from JSON file."""
    _ensure_users_file_exists()
    return json.loads(USERS_FILE.read_text())


def _save_users(data):
    """Save users to JSON file."""
    USERS_FILE.write_text(json.dumps(data, indent=2))


def _user_exists(email):
    """Check if user already exists by email."""
    users_data = _load_users()
    return any(user["email"] == email for user in users_data["users"])


def _find_user(email):
    """Find user by email."""
    users_data = _load_users()
    for user in users_data["users"]:
        if user["email"] == email:
            return user
    return None


# ======================== EMERGENCY ALERTS ========================

def _ensure_emergency_file_exists():
    """Create emergency_alerts.json if it doesn't exist."""
    if not EMERGENCY_ALERTS_FILE.exists():
        EMERGENCY_ALERTS_FILE.write_text(json.dumps({"alerts": []}, indent=2))


def _load_emergency_alerts():
    """Load all emergency alerts from JSON file."""
    _ensure_emergency_file_exists()
    return json.loads(EMERGENCY_ALERTS_FILE.read_text())


def _save_emergency_alerts(data):
    """Save emergency alerts to JSON file."""
    EMERGENCY_ALERTS_FILE.write_text(json.dumps(data, indent=2))


def _severity_from_count(symptom_count):
    """Map symptom count to the configured risk level."""
    if symptom_count <= 2:
        return "Low"
    if symptom_count <= 4:
        return "Medium"
    return "High"


# Load trained model bundle.
with open(MODEL_PATH, "rb") as file_obj:
    model_bundle = pickle.load(file_obj)

model = model_bundle["model"]
mlb = model_bundle["mlb"]

if SYMPTOM_LIST_PATH.exists():
    with open(SYMPTOM_LIST_PATH, "rb") as file_obj:
        symptom_list = sorted(pickle.load(file_obj))
else:
    symptom_list = sorted(model_bundle.get("feature_names", mlb.classes_.tolist()))

disease_name_map = model_bundle.get("disease_name_map", {})
normalized_symptom_list = sorted({_normalize_text(symptom) for symptom in symptom_list if _normalize_text(symptom)})

GEMINI_API_KEY = "AIzaSyDoMnzsmVdQC64NSE4sDl-lKxo5dbmoo2Y"
GEMINI_CLIENT = None
GEMINI_MODEL_NAME = "gemini-2.5-flash"
CHAT_STATUS = "fallback"
CHAT_STATUS_REASON = "Gemini client is not initialized."

if genai is None:
    CHAT_STATUS_REASON = "google.genai package is not installed."
elif not GEMINI_API_KEY:
    CHAT_STATUS_REASON = "GEMINI_API_KEY is not set in the backend process environment."
else:
    try:
        GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
        CHAT_STATUS = "connected"
        CHAT_STATUS_REASON = "Gemini client initialized successfully."
    except Exception as exc:
        GEMINI_CLIENT = None
        CHAT_STATUS_REASON = f"Failed to initialize Gemini client: {exc}"


def _build_lookup_dictionaries():
    """Create fast disease->details dictionaries at server startup."""
    ayur_df = _load_csv_with_fallback("AyurGenixAI_Dataset.csv", [])
    patient_df = _load_csv_with_fallback("indian_diseases_dataset.csv", [])

    ayur_disease_col = _find_column(ayur_df, ["Disease"])
    ayur_formulation_col = _find_column(ayur_df, ["Formulation"])
    ayur_diet_col = _find_column(ayur_df, ["Diet and Lifestyle Recommendations"])
    ayur_prevention_col = _find_column(ayur_df, ["Prevention"])
    ayur_herbs_col = _find_column(ayur_df, ["Ayurvedic Herbs", "Herbs"])
    ayur_medical_col = _find_column(ayur_df, ["Medical Intervention"])

    patient_disease_col = _find_column(patient_df, ["disease_name"])
    patient_treatment_col = _find_column(patient_df, ["treatment_type"])
    patient_symptoms_col = _find_column(patient_df, ["symptoms"])

    # Create unified disease keys across datasets.
    ayur_df = ayur_df.copy()
    ayur_df["dataset_name"] = ayur_df[ayur_disease_col].astype(str).str.strip()
    ayur_df["disease"] = ayur_df["dataset_name"].apply(_normalize_disease)

    patient_df = patient_df.copy()
    patient_df["dataset_name"] = patient_df[patient_disease_col].astype(str).str.strip()
    patient_df["disease"] = patient_df["dataset_name"].apply(_normalize_disease)

    lookup_ayur = {}
    for _, row in ayur_df.iterrows():
        dataset_name = _safe_string(row["dataset_name"]).strip()
        disease = _safe_string(row["disease"]).strip()
        if not disease or disease in lookup_ayur:
            continue

        lookup_ayur[disease] = {
            "dataset_name": dataset_name,
            "medicine": _safe_string(row[ayur_medical_col]),
            "remedy": _safe_string(row[ayur_formulation_col]),
            "precautions": _safe_string(row[ayur_prevention_col]),
            "diet": _safe_string(row[ayur_diet_col]),
            "herbs": _safe_string(row[ayur_herbs_col]),
        }

    lookup_patient = {}
    for _, row in patient_df.iterrows():
        dataset_name = _safe_string(row["dataset_name"]).strip()
        disease = _safe_string(row["disease"]).strip()
        if not disease or disease in lookup_patient:
            continue

        lookup_patient[disease] = {
            "dataset_name": dataset_name,
            "medicine": _safe_string(row[patient_treatment_col]),
            "remedy": "",
            "precautions": _safe_string(row[patient_symptoms_col]),
            "diet": "",
            "herbs": "",
        }

    return lookup_ayur, lookup_patient


# Build lookup maps once to optimize prediction path.
LOOKUP_AYUR, LOOKUP_PATIENT = _build_lookup_dictionaries()


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS, PUT"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"ok": True})
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS, PUT"
        return response, 200


@app.route("/symptoms", methods=["GET", "OPTIONS"])
def get_symptoms():
    """Return all unique symptoms from model training vocabulary."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return jsonify({"symptoms": symptom_list})

@app.route("/health", methods=["GET", "OPTIONS"])
def health_check():
    """Health check endpoint."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return jsonify({
        "status": "healthy",
        "message": "Backend server is running",
        "endpoints": ["/symptoms", "/predict", "/api/exercise/start", "/api/exercise/complete", "/api/exercise/user/<id>"]
    }), 200


@app.route("/medlineplus-info", methods=["POST", "OPTIONS"])
def get_medlineplus_info():
    """
    Fetch health information from MedlinePlus for any symptom, condition, or disease.
    
    Request JSON:
    {
        "query": "diabetes"  or  "high blood pressure"  or  "chest pain"
    }
    
    Response includes:
    - query: The search term
    - results: Array of MedlinePlus information
    - source: Citation information
    - medlineplus_url: Link to MedlinePlus
    """
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    
    if not query:
        return jsonify({
            "error": "Query parameter is required",
            "example": {"query": "diabetes"}
        }), 400
    
    try:
        # Fetch MedlinePlus information
        medlineplus_results = _fetch_medlineplus_info(query)
        
        return jsonify({
            "success": True,
            "query": query,
            "results": medlineplus_results,
            "found": bool(medlineplus_results),
            "source": "MedlinePlus - National Library of Medicine",
            "medlineplus_url": "https://medlineplus.gov/",
            "disclaimer": "This information is for educational purposes. Always consult with a healthcare professional for medical advice."
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "query": query
        }), 500


def _extract_symptoms_from_text(input_text):
    """Extract known symptoms from free text using exact and fuzzy matching."""
    normalized_text = _normalize_text(input_text)
    if not normalized_text:
        return []

    tokens = normalized_text.split()
    phrase_candidates = set(tokens)
    for size in (2, 3):
        for index in range(len(tokens) - size + 1):
            phrase_candidates.add(" ".join(tokens[index : index + size]))

    matched = []
    for symptom in normalized_symptom_list:
        if symptom in normalized_text:
            matched.append(symptom)
            continue

        # Fuzzy fallback for close phrasing like "joint hurts" -> "joint pain".
        best_score = 0.0
        for candidate in phrase_candidates:
            score = SequenceMatcher(None, candidate, symptom).ratio()
            if score > best_score:
                best_score = score
        if best_score >= 0.82:
            matched.append(symptom)

    return sorted(set(matched))


def get_medlineplus_info(disease_name):
    """
    Fetch health information from MedlinePlus Connect API.
    
    MedlinePlus Connect is the official API provided by the National Library of Medicine
    for integrating MedlinePlus health information into third-party applications.
    
    API Specification:
    - Endpoint: https://connect.medlineplus.gov/service
    - Query Type: ICD10CM (International Classification of Diseases)
    - Response Type: JSON
    
    Args:
        disease_name (str): Name of the disease/condition to search for
        
    Returns:
        dict: Simplified information with:
            - title: Disease name
            - summary: Brief description
            - source_url: Link to full MedlinePlus article
            - related_topics: List of related health topics
            - error: Error message if API fails (fallback response)
            
    Example Response:
        {
            "title": "Diabetes",
            "summary": "Information about diabetes types and management...",
            "source_url": "https://medlineplus.gov/diabetes.html",
            "related_topics": ["Blood glucose", "Insulin", ...],
            "source": "MedlinePlus"
        }
    """
    try:
        # MedlinePlus Connect API endpoint
        # Documentation: https://www.nlm.nih.gov/medlineplus/connect/overview.html
        api_endpoint = "https://connect.medlineplus.gov/service"
        
        # Build query parameters for MedlinePlus Connect API
        params = {
            "mainSearchCriteria.v.c": disease_name,           # Search term
            "mainSearchCriteria.v.cs": "ICD10CM",              # ICD-10-CM coding system
            "knowledgeResponseType": "application/json"        # Request JSON response
        }
        
        print(f"\n[MEDLINEPLUS-CONNECT] Fetching info for disease: '{disease_name}'")
        print(f"[MEDLINEPLUS-CONNECT] API Endpoint: {api_endpoint}")
        print(f"[MEDLINEPLUS-CONNECT] Query Parameters: {params}")
        
        # Make request to MedlinePlus Connect API with timeout
        response = requests.get(
            api_endpoint,
            params=params,
            timeout=10,
            headers={"User-Agent": "Health-AI-Application/1.0"}
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        print(f"[MEDLINEPLUS-CONNECT] API Response received (Status: {response.status_code})")
        
        # Extract useful information from MedlinePlus response
        medlineplus_info = {
            "title": disease_name,
            "summary": "Information from MedlinePlus available.",
            "source_url": f"https://medlineplus.gov/",
            "related_topics": [],
            "source": "MedlinePlus (National Library of Medicine)"
        }
        
        # Parse knowledge documents from the response
        if isinstance(data, dict) and "feed" in data:
            feed = data.get("feed", {})
            
            # Extract title from feed
            if "title" in feed:
                medlineplus_info["title"] = feed["title"].get("$t", disease_name)
            
            # Extract summary/description
            if "description" in feed:
                medlineplus_info["summary"] = feed["description"].get("$t", "")[:500]
            elif "subtitle" in feed:
                medlineplus_info["summary"] = feed["subtitle"].get("$t", "")[:500]
            
            # Extract URL/link
            if "link" in feed:
                links = feed["link"] if isinstance(feed["link"], list) else [feed["link"]]
                for link in links:
                    if isinstance(link, dict) and link.get("type") == "text/html":
                        medlineplus_info["source_url"] = link.get("href", "https://medlineplus.gov/")
                        break
            
            # Extract related topics/entries
            if "entry" in feed:
                entries = feed["entry"] if isinstance(feed["entry"], list) else [feed["entry"]]
                related_topics = []
                for entry in entries[:10]:  # Limit to 10 related topics
                    if isinstance(entry, dict) and "title" in entry:
                        topic = entry["title"].get("$t", "")
                        if topic and topic not in related_topics:
                            related_topics.append(topic)
                medlineplus_info["related_topics"] = related_topics
        
        print(f"[MEDLINEPLUS-CONNECT] Successfully extracted info for '{disease_name}'")
        print(f"[MEDLINEPLUS-CONNECT] Title: {medlineplus_info['title']}")
        print(f"[MEDLINEPLUS-CONNECT] URL: {medlineplus_info['source_url']}")
        
        return medlineplus_info
        
    except requests.exceptions.Timeout:
        print(f"[MEDLINEPLUS-CONNECT] Timeout fetching info for '{disease_name}'")
        return {
            "title": disease_name,
            "summary": "Timeout connecting to MedlinePlus. Please try again or visit MedlinePlus directly.",
            "source_url": f"https://medlineplus.gov/search/search_results.html?search={disease_name}",
            "related_topics": [],
            "source": "MedlinePlus",
            "error": "Request timeout"
        }
    except requests.exceptions.ConnectionError as e:
        print(f"[MEDLINEPLUS-CONNECT] Connection error for '{disease_name}': {str(e)}")
        return {
            "title": disease_name,
            "summary": "Unable to connect to MedlinePlus. Using fallback information.",
            "source_url": f"https://medlineplus.gov/search/search_results.html?search={disease_name}",
            "related_topics": [],
            "source": "MedlinePlus",
            "error": "Connection failed"
        }
    except (ValueError, KeyError) as e:
        print(f"[MEDLINEPLUS-CONNECT] Error parsing response for '{disease_name}': {str(e)}")
        return {
            "title": disease_name,
            "summary": "Error processing MedlinePlus data. Please visit MedlinePlus directly.",
            "source_url": f"https://medlineplus.gov/search/search_results.html?search={disease_name}",
            "related_topics": [],
            "source": "MedlinePlus",
            "error": "Response parsing failed"
        }
    except Exception as e:
        print(f"[MEDLINEPLUS-CONNECT] Unexpected error for '{disease_name}': {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return fallback response - never crash the application
        return {
            "title": disease_name,
            "summary": "Unable to fetch detailed information at this moment. Health information available on MedlinePlus.",
            "source_url": f"https://medlineplus.gov/search/search_results.html?search={disease_name}",
            "related_topics": [],
            "source": "MedlinePlus",
            "error": str(e)
        }


# Legacy function for backward compatibility (redirects to new function)
def _fetch_medlineplus_info(symptom_or_condition):
    """
    Legacy wrapper for backward compatibility.
    Use get_medlineplus_info() instead.
    """
    info = get_medlineplus_info(symptom_or_condition)
    # Return in list format for backward compatibility
    return [info] if info and "error" not in info else []


@app.route("/extract-symptoms", methods=["POST", "OPTIONS"])
def extract_symptoms():
    """
    Extract structured symptom list from natural language user input.
    
    Also fetches relevant information from MedlinePlus for each symptom.
    
    Response includes:
    - symptoms: List of extracted symptom names
    - symptom_details: Detailed information from MedlinePlus for each symptom
    - medlineplus_status: Status of MedlinePlus API for each symptom
    """
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    data = request.get_json(silent=True) or {}
    text = data.get("text", "")

    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Input JSON must include a non-empty 'text' field."}), 400

    # Extract symptoms from text
    symptoms = _extract_symptoms_from_text(text)
    
    # Fetch MedlinePlus information for each symptom
    symptom_details = {}
    medlineplus_status = {}
    
    print(f"\n[EXTRACT-SYMPTOMS] Processing {len(symptoms)} symptoms: {symptoms}")
    
    for symptom in symptoms:
        print(f"\n[EXTRACT-SYMPTOMS] Processing symptom: '{symptom}'")
        medlineplus_info = _fetch_medlineplus_info(symptom)
        
        # Always add symptom to details, even if no MedlinePlus results
        symptom_details[symptom] = {
            "name": symptom,
            "medlineplus_results": medlineplus_info if medlineplus_info else [],
            "source": "MedlinePlus (National Library of Medicine)",
            "has_results": len(medlineplus_info) > 0 if medlineplus_info else False
        }
        
        medlineplus_status[symptom] = {
            "found": len(medlineplus_info) > 0 if medlineplus_info else False,
            "result_count": len(medlineplus_info) if medlineplus_info else 0
        }
        
        print(f"[EXTRACT-SYMPTOMS] Symptom '{symptom}' - Results: {medlineplus_status[symptom]}")
    
    response = {
        "symptoms": symptoms,
        "symptom_details": symptom_details,
        "medlineplus_status": medlineplus_status,
        "total_symptoms": len(symptoms),
        "medlineplus_enabled": True,
        "message": "Symptom extraction and MedlinePlus lookup complete"
    }
    
    print(f"\n[EXTRACT-SYMPTOMS] Response ready: {len(symptoms)} symptoms with MedlinePlus data")
    return jsonify(response)


def _generate_chat_reply(user_message):
    """Generate chatbot response with Gemini, or fallback if unavailable."""
    if GEMINI_CLIENT is None:
        return FALLBACK_CHAT_REPLY

    prompt = (
        f"System instruction: {HEALTH_ASSISTANT_PROMPT}\n"
        f"User message: {user_message}\n"
        "Assistant response:"
    )

    response = GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
    )

    reply = getattr(response, "text", "") or ""
    if not reply:
        # Some SDK versions expose text through nested candidates/parts.
        try:
            parts = []
            for candidate in getattr(response, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", []) or []:
                    text = getattr(part, "text", "")
                    if text:
                        parts.append(text)
            reply = "\n".join(parts)
        except Exception:
            reply = ""

    reply = reply.strip()
    return reply if reply else FALLBACK_CHAT_REPLY


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """Return a general health assistant reply for user questions."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Input JSON must include a non-empty 'message' field."}), 400

    try:
        reply = _generate_chat_reply(message.strip())
    except Exception:
        reply = FALLBACK_CHAT_REPLY

    return jsonify({"reply": reply})


@app.route("/chat-status", methods=["GET", "OPTIONS"])
def chat_status():
    """Return chat AI status."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    return jsonify(
        {
            "connected": GEMINI_CLIENT is not None,
            "status": CHAT_STATUS,
            "reason": CHAT_STATUS_REASON,
            "model": GEMINI_MODEL_NAME,
        }
    )


def _resolve_details(predicted_disease):
    """Search Ayur first; if medicine is missing, use Indian patient medicine as fallback."""
    ayur_details = LOOKUP_AYUR.get(predicted_disease)
    patient_details = LOOKUP_PATIENT.get(predicted_disease)

    if ayur_details:
        details = dict(ayur_details)
        if not details.get("medicine") and patient_details:
            details["medicine"] = patient_details.get("medicine", "")
        details["source"] = "AyurGenixAI"
        return details

    if patient_details:
        details = dict(patient_details)
        details["source"] = "indian_diseases_dataset"
        return details

    return {
        "dataset_name": disease_name_map.get(predicted_disease, predicted_disease.title()),
        "medicine": "",
        "remedy": "",
        "precautions": "",
        "diet": "",
        "herbs": "",
        "source": "none",
    }


def _top_predictions(feature_vector, top_n=3):
    """Return the top-N most probable diseases with confidence."""
    if not hasattr(model, "predict_proba"):
        predicted = str(model.predict(feature_vector)[0])
        details = _resolve_details(predicted)
        return [
            {
                "disease_prediction": predicted,
                "dataset_name": details.get("dataset_name", disease_name_map.get(predicted, predicted.title())),
                "confidence": "100%",
            }
        ]

    probabilities = model.predict_proba(feature_vector)[0]
    classes = model.classes_
    top_indices = sorted(range(len(probabilities)), key=lambda idx: probabilities[idx], reverse=True)[:top_n]

    predictions = []
    for idx in top_indices:
        disease_key = str(classes[idx])
        details = _resolve_details(disease_key)
        predictions.append(
            {
                "disease_prediction": disease_key,
                "dataset_name": details.get("dataset_name", disease_name_map.get(disease_key, disease_key.title())),
                "confidence": _format_confidence(probabilities[idx]),
            }
        )

    return predictions


@app.route("/predict", methods=["POST", "OPTIONS"])
def predict():
    """
    Predict possible diseases from symptoms and return integrated MedlinePlus information.
    
    This endpoint:
    1. Analyzes input symptoms using the trained ML model
    2. Predicts possible diseases with confidence scores
    3. Fetches MedlinePlus health information for each predicted disease
    4. Returns combined analysis with educational resources
    
    Request JSON:
    {
        "symptoms": ["headache", "fever", "cough"]
    }
    
    Response includes both symptom analysis and MedlinePlus health information.
    """
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    data = request.get_json(silent=True) or {}
    symptoms = data.get("symptoms")

    if not isinstance(symptoms, list) or not symptoms:
        return jsonify({"error": "Input JSON must include a non-empty 'symptoms' list."}), 400

    cleaned_symptoms = [_normalize_text(item) for item in symptoms if _normalize_text(item)]
    if not cleaned_symptoms:
        return jsonify({"error": "No valid symptoms were provided."}), 400

    print(f"\n[PREDICT] Received symptoms: {cleaned_symptoms}")
    
    # Determine severity level
    severity = _severity_from_count(len(cleaned_symptoms))
    emergency_warning = ""
    if any(symptom in CRITICAL_SYMPTOMS for symptom in cleaned_symptoms):
        emergency_warning = "Seek immediate medical attention"

    # Get ML model predictions
    X = mlb.transform([cleaned_symptoms])
    predictions = _top_predictions(X, top_n=3)
    top_prediction = predictions[0]
    predicted_disease = top_prediction["disease_prediction"]
    confidence = top_prediction["confidence"]

    details = _resolve_details(predicted_disease)
    dataset_name = details.get("dataset_name", disease_name_map.get(predicted_disease, predicted_disease))

    # ============================================================================
    # MEDLINEPLUS INTEGRATION: Fetch health information for top predicted disease
    # ============================================================================
    
    print(f"\n[PREDICT] Fetching MedlinePlus information for main disease: {dataset_name}")
    
    # Fetch MedlinePlus information for the top predicted disease
    top_medlineplus_info = get_medlineplus_info(dataset_name)
    
    print(f"[PREDICT] MedlinePlus data fetched for: {dataset_name}")
    
    # Build top 3 predictions with confidence for display
    top_3_predictions = []
    for pred in predictions:
        pred_disease_key = pred.get("disease_prediction")
        pred_details = _resolve_details(pred_disease_key)
        pred_disease_name = pred_details.get("dataset_name", pred_disease_key)
        
        top_3_predictions.append({
            "disease_name": pred_disease_name,
            "confidence": pred.get("confidence", "0%")
        })
    
    # Build comprehensive MedlinePlus data for the main disease
    medlineplus_section = {
        "title": top_medlineplus_info.get("title", dataset_name),
        "summary": top_medlineplus_info.get("summary", "Learn about this condition on MedlinePlus."),
        "url": top_medlineplus_info.get("source_url", f"https://medlineplus.gov/"),
        "related_topics": top_medlineplus_info.get("related_topics", []),
        "source": "MedlinePlus - National Library of Medicine"
    }
    
    # ============================================================================
    # BUILD FRONTEND-FRIENDLY RESPONSE
    # ============================================================================
    
    response = {
        # ===== MAIN DISEASE PREDICTION =====
        "main_disease": dataset_name,
        "confidence": confidence,
        "disease_prediction_key": predicted_disease,
        
        # ===== TOP 3 PREDICTIONS (for "📊 Top 3 Predictions" section) =====
        "top_3_predictions": top_3_predictions,
        
        # ===== MEDLINEPLUS HEALTH INFORMATION =====
        "medlineplus": medlineplus_section,
        
        # ===== RISK LEVEL (mapped from severity) =====
        "risk_level": severity,
        
        # ===== MEDICINE ADVICE (💊 section) =====
        "medicine_advice": details.get("medicine", "Not available"),
        
        # ===== AYURVEDIC REMEDY (🌿 Remedy section) =====
        "ayurvedic_remedy": details.get("remedy", "Not available"),
        
        # ===== DIET ADVICE (🥗 section) =====
        "diet_advice": details.get("diet", "Not available"),
        
        # ===== HERBS (🌿 Herbs section) =====
        "herbs": details.get("herbs", "Not available"),
        
        # ===== PRECAUTIONS (⚠ section) =====
        "precautions": details.get("precautions", "Not available"),
        
        # ===== EMERGENCY & SYMPTOM INFO =====
        "symptom_analysis": {
            "input_symptoms": cleaned_symptoms,
            "symptom_count": len(cleaned_symptoms),
            "severity": severity,
            "emergency_warning": emergency_warning if emergency_warning else "None"
        },
        
        # ===== BACKWARD COMPATIBILITY =====
        "disease": dataset_name,
        "disease_prediction": predicted_disease,
        "dataset_name": dataset_name,
        "medicine": details.get("medicine", ""),
        "remedy": details.get("remedy", ""),
        "precautions": details.get("precautions", ""),
        "diet": details.get("diet", ""),
        "herbs": details.get("herbs", ""),
        "predictions": predictions,
        
        # ===== METADATA =====
        "api_version": "3.0",
        "features": ["symptom_analysis", "medlineplus_integration", "ayurvedic_remedies"],
        "disclaimer": "This AI tool provides health suggestions and should not replace professional medical advice. Always consult a qualified doctor."
    }
    
    print(f"\n[PREDICT] Response prepared for disease: {dataset_name}")
    return jsonify(response)


# ======================== AUTHENTICATION ROUTES ========================

@app.route("/signup", methods=["POST", "OPTIONS"])
def signup():
    """Register a new user."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "Patient").strip()
    
    # Validation
    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required."}), 400
    
    if role not in ["Patient", "Doctor", "Hospital"]:
        return jsonify({"error": "Invalid role. Must be Patient, Doctor, or Hospital."}), 400
    
    if _user_exists(email):
        return jsonify({"error": "User already exists with this email."}), 409
    
    # Create new user
    users_data = _load_users()
    new_user = {
        "id": len(users_data["users"]) + 1,
        "name": name,
        "email": email,
        "password": _hash_password(password),
        "role": role,
        "created_at": datetime.now().isoformat()
    }
    
    users_data["users"].append(new_user)
    _save_users(users_data)
    
    return jsonify({
        "success": True,
        "message": "User registered successfully.",
        "user": {"id": new_user["id"], "name": name, "email": email, "role": role}
    }), 201


@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    """Authenticate user and return session token."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    
    user = _find_user(email)
    if not user or user["password"] != _hash_password(password):
        return jsonify({"error": "Invalid email or password."}), 401
    
    # Generate simple session token (in production, use JWT)
    session_token = hashlib.sha256(f"{email}{datetime.now().isoformat()}".encode()).hexdigest()
    
    return jsonify({
        "success": True,
        "message": "Login successful.",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        },
        "token": session_token
    }), 200


# ======================== EMERGENCY ROUTES ========================

@app.route("/emergency", methods=["POST", "OPTIONS"])
def emergency():
    """Handle emergency SOS requests."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    user_name = data.get("user_name", "Unknown")
    email = data.get("email", "Unknown")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    
    if not user_id or latitude is None or longitude is None:
        return jsonify({"error": "user_id, latitude, and longitude are required."}), 400
    
    # Create emergency alert
    alerts_data = _load_emergency_alerts()
    emergency_alert = {
        "id": len(alerts_data["alerts"]) + 1,
        "user_id": user_id,
        "user_name": user_name,
        "email": email,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }
    
    alerts_data["alerts"].append(emergency_alert)
    _save_emergency_alerts(alerts_data)
    
    return jsonify({
        "success": True,
        "message": "Emergency alert sent successfully.",
        "alert_id": emergency_alert["id"],
        "severity": "CRITICAL"
    }), 201


@app.route("/emergency-alerts", methods=["GET", "OPTIONS"])
def get_emergency_alerts():
    """Get all emergency alerts (for doctors and hospitals)."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    role = request.args.get("role", "Patient")
    
    if role not in ["Doctor", "Hospital"]:
        return jsonify({"error": "Only doctors and hospitals can view emergency alerts."}), 403
    
    alerts_data = _load_emergency_alerts()
    # Return only pending alerts
    pending_alerts = [alert for alert in alerts_data["alerts"] if alert["status"] == "pending"]
    
    return jsonify({
        "success": True,
        "alerts": pending_alerts,
        "total": len(pending_alerts)
    }), 200


# ======================== HOSPITAL LOCATION ROUTES ========================

def _calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula (in km)."""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def _load_hospitals():
    """Load hospital data from JSON file."""
    hospitals_file = DATA_DIR / "hospitals.json"
    if hospitals_file.exists():
        return json.loads(hospitals_file.read_text())
    return {"hospitals": []}


@app.route("/nearby-hospitals", methods=["POST", "OPTIONS"])
def nearby_hospitals():
    """Get nearby hospitals using Overpass API (real-time) with robust fallback to static data."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    radius = data.get("radius", 50)  # Default 50 km radius
    
    if latitude is None or longitude is None:
        return jsonify({"error": "Latitude and longitude are required."}), 400
    
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        radius = float(radius)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid coordinate values."}), 400
    
    # Try Overpass API first with aggressive error handling
    try:
        radius_meters = int(radius * 1000)
        # Simpler, more reliable Overpass query
        overpass_query = f"[out:json][timeout:25];(node[amenity=hospital](around:{radius_meters},{latitude},{longitude});way[amenity=hospital](around:{radius_meters},{latitude},{longitude}););out body;>;out skel qt;"
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Use requests library instead of urllib for better handling
        response = requests.post(
            overpass_url,
            data={'data': overpass_query},
            timeout=15,
            headers={'User-Agent': 'HealthAI/1.0'}
        )
        response.raise_for_status()
        
        result = response.json()
        
        hospitals = []
        for element in result.get("elements", []):
            # Skip elements without proper location data
            if element.get("type") not in ["node", "way"]:
                continue
                
            hosp_lat = element.get("lat")
            hosp_lon = element.get("lon")
            
            # For ways, use center coordinates
            if not hosp_lat and element.get("type") == "way":
                if "center" in element:
                    hosp_lat = element["center"].get("lat")
                    hosp_lon = element["center"].get("lon")
            
            if hosp_lat and hosp_lon:
                tags = element.get("tags", {})
                distance = _calculate_distance(latitude, longitude, float(hosp_lat), float(hosp_lon))
                
                # Build address from tags
                address_parts = []
                if tags.get("addr:street"):
                    address_parts.append(tags["addr:street"])
                if tags.get("addr:city"):
                    address_parts.append(tags["addr:city"])
                address = ", ".join(address_parts) if address_parts else "Address not available"
                
                hospitals.append({
                    "id": str(element.get("id", "")),
                    "name": tags.get("name", "Hospital"),
                    "latitude": float(hosp_lat),
                    "longitude": float(hosp_lon),
                    "distance": round(distance, 2),
                    "phone": tags.get("phone", tags.get("contact:phone", "")),
                    "website": tags.get("website", tags.get("contact:website", "")),
                    "address": address,
                    "location": address,
                    "beds": tags.get("beds", "N/A"),
                    "rating": 4.5,
                    "services": ["Emergency", "General Services"],
                    "doctors": "N/A",
                    "email": tags.get("email", tags.get("contact:email", ""))
                })
        
        if hospitals:
            hospitals.sort(key=lambda x: x["distance"])
            print(f"✅ Overpass API returned {len(hospitals)} hospitals")
            return jsonify({
                "success": True,
                "location": {"latitude": latitude, "longitude": longitude},
                "radius": radius,
                "hospitals": hospitals,
                "total": len(hospitals),
                "source": "OpenStreetMap (Real-time)"
            }), 200
        else:
            print("Overpass API returned no hospitals - using fallback")
                    
    except requests.exceptions.HTTPError as he:
        if he.response.status_code == 429:
            print("⚠️ Overpass API rate limited (429) - using fallback")
        else:
            print(f"HTTP Error from Overpass: {he.response.status_code} - using fallback")
    except requests.exceptions.Timeout:
        print("Overpass API timeout - using fallback")
    except requests.exceptions.RequestException as api_err:
        print(f"Overpass API error ({type(api_err).__name__}): {str(api_err)[:100]} - using fallback")
            
    except Exception as e:
        print(f"Outer exception during Overpass query: {str(e)[:100]}")
    
    # Fallback to static JSON data
    print("📍 Using static hospital database as fallback")
    hospitals_data = _load_hospitals()
    nearby = []
    
    for hospital in hospitals_data.get("hospitals", []):
        dist = _calculate_distance(
            latitude, longitude,
            hospital["latitude"], hospital["longitude"]
        )
        
        if dist <= radius:
            hospital_copy = dict(hospital)
            hospital_copy["distance"] = round(dist, 2)
            nearby.append(hospital_copy)
    
    # Sort by distance
    nearby.sort(key=lambda h: h["distance"])
    
    return jsonify({
        "success": True,
        "location": {"latitude": latitude, "longitude": longitude},
        "radius": radius,
        "hospitals": nearby,
        "total": len(nearby),
        "source": "Static Database (Fallback)"
    }), 200


@app.route("/all-hospitals", methods=["GET", "OPTIONS"])
def all_hospitals():
    """Get all hospitals in the database."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    hospitals_data = _load_hospitals()
    
    return jsonify({
        "success": True,
        "hospitals": hospitals_data.get("hospitals", []),
        "total": len(hospitals_data.get("hospitals", []))
    }), 200


# ======================== PATIENT REPORTS ROUTES ========================

def _load_patient_reports():
    """Load patient reports from JSON file."""
    reports_file = DATA_DIR / "patient_reports.json"
    if reports_file.exists():
        return json.loads(reports_file.read_text())
    return {"patient_reports": []}


def _save_patient_reports(data):
    """Save patient reports to JSON file."""
    reports_file = DATA_DIR / "patient_reports.json"
    reports_file.write_text(json.dumps(data, indent=2))


@app.route("/upload-report", methods=["POST", "OPTIONS"])
def upload_report():
    """Upload patient medical report (blood report, etc.)."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    
    user_id = data.get("user_id")
    user_name = data.get("user_name")
    email = data.get("email")
    report_type = data.get("report_type")  # e.g., "Blood Report", "X-Ray", "ECG"
    report_name = data.get("report_name")
    original_filename = data.get("original_filename", "")  # Original uploaded filename to preserve extension
    report_data = data.get("report_data")  # Base64 encoded file
    
    if not all([user_id, report_type, report_name, report_data]):
        return jsonify({"error": "user_id, report_type, report_name, and report_data are required."}), 400
    
    # Create reports directory if it doesn't exist
    reports_dir = DATA_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    # Decode base64 file
    try:
        file_content = base64.b64decode(report_data.split(',')[1] if ',' in report_data else report_data)
    except Exception as e:
        return jsonify({"error": f"Failed to decode file: {str(e)}"}), 400
    
    # Generate filename with proper extension
    # Prioritize original filename extension if available
    file_extension = ".txt"
    if original_filename and '.' in original_filename:
        # Extract extension from original filename
        ext = '.' + original_filename.split('.')[-1].lower()
        # Validate extension
        if ext.lower() in ['.pdf', '.txt', '.text']:
            file_extension = ext
    elif not report_name.lower().endswith(('.pdf', '.txt', '.text')):
        # Try to detect file type from content if no valid extension
        if file_content[:4] == b'%PDF':  # PDF magic bytes
            file_extension = ".pdf"
        elif file_content.startswith(b'\xff\xd8\xff'):
            file_extension = ".pdf"  # JPEG header (fallback)
    
    # Add extension if not already present
    if not report_name.lower().endswith(('.pdf', '.txt', '.text')):
        report_name = f"{report_name}{file_extension}"
    
    filename = f"report_{user_id}_{datetime.now().timestamp()}_{report_name}"
    file_path = reports_dir / filename
    
    # Save file
    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500
    
    # Save report metadata
    reports_data = _load_patient_reports()
    report_record = {
        "id": len(reports_data["patient_reports"]) + 1,
        "user_id": user_id,
        "user_name": user_name,
        "email": email,
        "report_type": report_type,
        "report_name": report_name,
        "filename": filename,
        "uploaded_at": datetime.now().isoformat(),
        "file_size": len(file_content),
        "status": "uploaded"
    }
    
    reports_data["patient_reports"].append(report_record)
    _save_patient_reports(reports_data)
    
    return jsonify({
        "success": True,
        "message": "Report uploaded successfully.",
        "report_id": report_record["id"],
        "report": report_record
    }), 201


@app.route("/analyze-report", methods=["POST", "OPTIONS"])
def analyze_report():
    """
    Analyze a medical report and extract medical information.
    
    This endpoint accepts a report file and extracts important medical data such as:
    - Patient demographics (name, age)
    - Vital measurements (blood pressure, blood sugar, hemoglobin, cholesterol)
    - Detected abnormalities and risk levels
    - Critical condition alerts
    
    Request JSON:
    {
        "report_id": 1,  # Optional: ID of existing report to analyze
        "report_file": "base64_encoded_file_content"  # Optional: Direct file upload
    }
    
    Response JSON:
    {
        "success": true,
        "patient_name": "John Doe",
        "age": 45,
        "blood_pressure": "140/90",
        "blood_sugar": 185,
        "hemoglobin": 13.5,
        "cholesterol": 220,
        "other_values": {...},
        "diseases_conditions": "Hypertension, Type 2 Diabetes",
        "abnormalities": [
            {
                "parameter": "Blood Sugar",
                "value": "185 mg/dL",
                "status": "High",
                "severity": "warning"
            }
        ],
        "critical_keywords": [],
        "risk_level": "Warning",
        "summary": "Patient John Doe, Age 45. Findings: Blood Sugar (High)..."
    }
    """
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        data = request.get_json(silent=True) or {}
        
        # Get the report to analyze
        report_id = data.get("report_id")
        report_file_data = data.get("report_file")
        
        if not report_id and not report_file_data:
            return jsonify({
                "success": False,
                "error": "Either report_id or report_file must be provided"
            }), 400
        
        file_path = None
        
        # If report_id provided, find the existing report file
        if report_id:
            try:
                report_id = int(report_id)
                reports_data = _load_patient_reports()
                
                # Find report by ID
                report_record = None
                for report in reports_data.get("patient_reports", []):
                    if report.get("id") == report_id:
                        report_record = report
                        break
                
                if not report_record:
                    return jsonify({
                        "success": False,
                        "error": f"Report with ID {report_id} not found"
                    }), 404
                
                # Construct file path
                filename = report_record.get("filename")
                file_path = DATA_DIR / "reports" / filename
                
                if not file_path.exists():
                    return jsonify({
                        "success": False,
                        "error": f"Report file not found: {filename}"
                    }), 404
                    
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "Invalid report_id format"
                }), 400
        
        # If direct file upload provided, save it temporarily
        elif report_file_data:
            try:
                # Decode base64 file
                file_content = base64.b64decode(
                    report_file_data.split(',')[1] if ',' in report_file_data else report_file_data
                )
                
                # Create temporary file
                reports_dir = DATA_DIR / "reports"
                reports_dir.mkdir(exist_ok=True)
                
                temp_filename = f"temp_report_{datetime.now().timestamp()}"
                file_path = reports_dir / temp_filename
                
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Failed to process uploaded file: {str(e)}"
                }), 400
        
        # Analyze the report
        try:
            analysis_result = analyze_medical_report(str(file_path))
            
            # Clean up temporary file if it was created
            if report_file_data and file_path.exists():
                try:
                    file_path.unlink()
                except:
                    pass
            
            # Add additional metadata
            if report_id:
                reports_data = _load_patient_reports()
                for report in reports_data.get("patient_reports", []):
                    if report.get("id") == report_id:
                        analysis_result["report_metadata"] = {
                            "report_id": report_id,
                            "report_type": report.get("report_type"),
                            "uploaded_at": report.get("uploaded_at"),
                            "user_id": report.get("user_id")
                        }
                        break
            
            return jsonify(analysis_result), 200
            
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
                "message": "Failed to analyze report"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "An error occurred while processing your request"
        }), 500


@app.route("/patient-reports", methods=["GET", "OPTIONS"])
def get_patient_reports():
    """Get patient reports for a specific user."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    user_id = request.args.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id is required."}), 400
    
    reports_data = _load_patient_reports()
    user_reports = [r for r in reports_data["patient_reports"] if str(r["user_id"]) == str(user_id)]
    
    return jsonify({
        "success": True,
        "reports": user_reports,
        "total": len(user_reports)
    }), 200


@app.route("/download-report/<int:report_id>", methods=["GET", "OPTIONS"])
def download_report(report_id):
    """Download a patient medical report file."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    print(f"[DOWNLOAD] Request to download report ID: {report_id}")
    
    try:
        # Load patient reports
        reports_data = _load_patient_reports()
        
        # Find report by ID
        report = None
        for r in reports_data.get("patient_reports", []):
            if r["id"] == report_id:
                report = r
                break
        
        if not report:
            print(f"[DOWNLOAD] Report {report_id} not found")
            return jsonify({"error": "Report not found"}), 404
        
        # Get file path
        reports_dir = DATA_DIR / "reports"
        file_path = reports_dir / report["filename"]
        
        print(f"[DOWNLOAD] File path: {file_path}")
        print(f"[DOWNLOAD] File exists: {file_path.exists()}")
        
        if not file_path.exists():
            print(f"[DOWNLOAD] File does not exist at {file_path}")
            return jsonify({"error": "Report file not found on server"}), 404
        
        # Send file
        print(f"[DOWNLOAD] Sending file: {report['report_name']}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=report['report_name'],
            mimetype='application/octet-stream'
        )
    
    except Exception as e:
        print(f"[DOWNLOAD] Error downloading report: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to download report: {str(e)}"}), 500


@app.route("/delete-report/<int:report_id>", methods=["DELETE", "OPTIONS"])
def delete_report(report_id):
    """Delete a patient report."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        print(f"[DELETE] Processing delete request for report ID: {report_id}")
        reports_data = _load_patient_reports()
        print(f"[DELETE] Loaded {len(reports_data.get('patient_reports', []))} reports from JSON")
        
        # Find and remove report
        report_to_delete = None
        report_index = -1
        for i, report in enumerate(reports_data.get("patient_reports", [])):
            if report.get("id") == report_id:
                report_to_delete = report
                report_index = i
                print(f"[DELETE] Found report at index {i}: {report.get('report_name')}")
                break
        
        if not report_to_delete:
            print(f"[DELETE] Report {report_id} not found in JSON")
            return jsonify({
                "success": False,
                "error": "Report not found."
            }), 404
        
        # Delete file from disk
        if "filename" in report_to_delete and report_to_delete["filename"]:
            try:
                file_path = DATA_DIR / "reports" / report_to_delete["filename"]
                if file_path.exists():
                    file_path.unlink()
                    print(f"[DELETE] Deleted file: {file_path}")
                else:
                    print(f"[DELETE] File does not exist: {file_path}")
            except Exception as e:
                print(f"[DELETE] Error deleting file: {e}")
                # Continue - don't fail if file deletion fails
        
        # Remove from list and save
        if report_index >= 0:
            deleted = reports_data["patient_reports"].pop(report_index)
            print(f"[DELETE] Removed report from list: {deleted.get('report_name')}")
            
            # Save updated reports
            _save_patient_reports(reports_data)
            print(f"[DELETE] Saved updated reports JSON")
        else:
            print(f"[DELETE] Warning: report_index not >= 0, but report was found!")
        
        print(f"[DELETE] Report {report_id} deleted successfully")
        return jsonify({
            "success": True,
            "message": "Report deleted successfully."
        }), 200
        
    except Exception as e:
        print(f"[DELETE] Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error deleting report: {str(e)}"
        }), 500


# ======================== OPENSTREETMAP INTEGRATION ========================

@app.route("/reverse-geocode", methods=["POST", "OPTIONS"])
def reverse_geocode():
    """Convert coordinates to address using OpenStreetMap Nominatim API."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    
    if latitude is None or longitude is None:
        return jsonify({"error": "Latitude and longitude are required."}), 400
    
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid coordinate values."}), 400
    
    try:
        # OpenStreetMap Nominatim API for reverse geocoding
        nominatim_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=18"
        
        req = urllib.request.Request(nominatim_url, headers={'User-Agent': 'HealthAI'})
        with urllib.request.urlopen(req, timeout=5) as response:
            location_data = json.loads(response.read())
        
        return jsonify({
            "success": True,
            "latitude": latitude,
            "longitude": longitude,
            "address": location_data.get("address", {}),
            "display_name": location_data.get("display_name", "Location not found")
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Could not reverse geocode location"
        }), 500


@app.route("/search-location", methods=["POST", "OPTIONS"])
def search_location():
    """Search for location using OpenStreetMap Nominatim API."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    limit = data.get("limit", 5)
    
    if not query:
        return jsonify({"error": "Search query is required."}), 400
    
    try:
        # OpenStreetMap Nominatim API for forward geocoding
        params = urllib.parse.urlencode({
            'q': query,
            'format': 'json',
            'limit': min(int(limit), 10)
        })
        nominatim_url = f"https://nominatim.openstreetmap.org/search?{params}"
        
        req = urllib.request.Request(nominatim_url, headers={'User-Agent': 'HealthAI'})
        with urllib.request.urlopen(req, timeout=5) as response:
            results = json.loads(response.read())
        
        # Format results
        locations = [
            {
                "name": result.get("display_name", ""),
                "latitude": float(result.get("lat", 0)),
                "longitude": float(result.get("lon", 0)),
                "type": result.get("type", "unknown"),
                "importance": float(result.get("importance", 0))
            }
            for result in results
        ]
        
        return jsonify({
            "success": True,
            "query": query,
            "results": locations,
            "total": len(locations)
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Could not search location"
        }), 500


@app.route("/osm-hospitals", methods=["POST", "OPTIONS"])
def osm_hospitals():
    """Query hospitals from OpenStreetMap - uses /nearby-hospitals for better handling."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    # Simply delegate to nearby_hospitals which has better error handling and fallback
    return nearby_hospitals()


if __name__ == "__main__":
    app.run(debug=True)


# ======================== EMERGENCY RESPONSE PANEL ENDPOINTS ========================

@app.route("/send-advisory", methods=["POST", "OPTIONS"])
def send_advisory():
    """Send medical advisory from doctor to patient."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    alert_id = data.get("alert_id")
    user_id = data.get("user_id")
    advisory = data.get("advisory", "").strip()
    doctor = data.get("doctor", "Unknown Doctor")
    
    if not all([alert_id, user_id, advisory]):
        return jsonify({"error": "alert_id, user_id, and advisory are required."}), 400
    
    # Store advisory (in production, send to patient dashboard)
    advisory_record = {
        "id": int(datetime.now().timestamp()),
        "alert_id": alert_id,
        "user_id": user_id,
        "doctor": doctor,
        "advisory": advisory,
        "timestamp": datetime.now().isoformat(),
        "type": "medical_advisory"
    }
    
    print(f"[ADVISORY] Doctor {doctor} sent advisory to user {user_id}: {advisory[:50]}...")
    
    return jsonify({
        "success": True,
        "message": "Medical advisory sent successfully.",
        "advisory_id": advisory_record["id"]
    }), 201


@app.route("/send-emergency-message", methods=["POST", "OPTIONS"])
def send_emergency_message():
    """Send emergency message from doctor to patient."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    alert_id = data.get("alert_id")
    user_id = data.get("user_id")
    message = data.get("message", "").strip()
    doctor = data.get("doctor", "Unknown Doctor")
    
    if not all([alert_id, user_id, message]):
        return jsonify({"error": "alert_id, user_id, and message are required."}), 400
    
    # Store message (in production, send to patient dashboard)
    message_record = {
        "id": int(datetime.now().timestamp()),
        "alert_id": alert_id,
        "user_id": user_id,
        "doctor": doctor,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "type": "emergency_message"
    }
    
    print(f"[MESSAGE] Doctor {doctor} sent message to user {user_id}: {message[:50]}...")
    
    return jsonify({
        "success": True,
        "message": "Emergency message sent successfully.",
        "message_id": message_record["id"]
    }), 201


@app.route("/request-ambulance", methods=["POST", "OPTIONS"])
def request_ambulance():
    """Request ambulance for emergency case."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    alert_id = data.get("alert_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    patient_name = data.get("patient_name", "Unknown Patient")
    
    if not all([alert_id, latitude, longitude]):
        return jsonify({"error": "alert_id, latitude, and longitude are required."}), 400
    
    # Create ambulance request
    ambulance_request = {
        "id": int(datetime.now().timestamp()),
        "alert_id": alert_id,
        "patient_name": patient_name,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": datetime.now().isoformat(),
        "status": "dispatched"
    }
    
    print(f"[AMBULANCE] Ambulance requested for {patient_name} at ({latitude}, {longitude})")
    
    # Update alert status
    try:
        alerts_data = _load_emergency_alerts()
        for alert in alerts_data["alerts"]:
            if alert["id"] == alert_id:
                alert["status"] = "ambulance_requested"
                alert["ambulance_requested_at"] = datetime.now().isoformat()
                break
        _save_emergency_alerts(alerts_data)
    except Exception as e:
        print(f"[AMBULANCE] Error updating alert status: {e}")
    
    return jsonify({
        "success": True,
        "message": "Ambulance requested successfully.",
        "ambulance_request_id": ambulance_request["id"],
        "estimated_arrival": "10-15 minutes"
    }), 201


@app.route("/update-emergency-status", methods=["POST", "OPTIONS"])
def update_emergency_status():
    """Update emergency case status."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    alert_id = data.get("alert_id")
    status = data.get("status", "").strip()
    
    if not alert_id or not status:
        return jsonify({"error": "alert_id and status are required."}), 400
    
    if status not in ["pending", "responding", "resolved", "ambulance_requested"]:
        return jsonify({"error": "Invalid status. Must be: pending, responding, resolved, or ambulance_requested."}), 400
    
    try:
        alerts_data = _load_emergency_alerts()
        alert_found = False
        
        for alert in alerts_data["alerts"]:
            if alert["id"] == alert_id:
                alert["status"] = status
                alert["updated_at"] = datetime.now().isoformat()
                alert_found = True
                print(f"[STATUS] Alert {alert_id} status updated to: {status}")
                break
        
        if not alert_found:
            return jsonify({"error": "Alert not found."}), 404
        
        _save_emergency_alerts(alerts_data)
        
        return jsonify({
            "success": True,
            "message": "Emergency status updated successfully.",
            "alert_id": alert_id,
            "new_status": status
        }), 200
        
    except Exception as e:
        print(f"[STATUS] Error updating status: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# ======================== EXERCISE TRACKING ENDPOINTS ========================

def _load_exercise_activity():
    """Load exercise activity from JSON file"""
    exercise_file = DATA_DIR / "exercise_activity.json"
    if not exercise_file.exists():
        exercise_file.write_text(json.dumps({"exercise_activity": []}, indent=2))
    return json.loads(exercise_file.read_text())

def _save_exercise_activity(data):
    """Save exercise activity to JSON file"""
    exercise_file = DATA_DIR / "exercise_activity.json"
    exercise_file.write_text(json.dumps(data, indent=2))

@app.route("/api/exercise/start", methods=["POST", "OPTIONS"])
def start_exercise():
    """Start exercise activity tracking"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId")
    exercise_type = data.get("exerciseType", "Morning Yoga")
    
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    
    # Load exercise data
    exercise_data = _load_exercise_activity()
    
    # Create new exercise record
    exercise_record = {
        "id": len(exercise_data["exercise_activity"]) + 1,
        "user_id": user_id,
        "exercise_type": exercise_type,
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "duration": None,
        "status": "started",
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    
    exercise_data["exercise_activity"].append(exercise_record)
    _save_exercise_activity(exercise_data)
    
    print(f"[EXERCISE] User {user_id} started {exercise_type}")
    
    return jsonify({
        "success": True,
        "message": "Exercise started successfully",
        "exercise_id": exercise_record["id"],
        "exercise": exercise_record
    }), 201

@app.route("/api/exercise/complete", methods=["POST", "OPTIONS"])
def complete_exercise():
    """Complete exercise activity and calculate duration"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId")
    exercise_id = data.get("exerciseId")
    
    if not user_id or not exercise_id:
        return jsonify({"error": "userId and exerciseId are required"}), 400
    
    # Load exercise data
    exercise_data = _load_exercise_activity()
    
    # Find exercise record
    exercise_record = None
    for exercise in exercise_data["exercise_activity"]:
        if exercise["id"] == exercise_id and exercise["user_id"] == user_id:
            exercise_record = exercise
            break
    
    if not exercise_record:
        return jsonify({"error": "Exercise not found"}), 404
    
    if exercise_record["status"] == "completed":
        return jsonify({"error": "Exercise already completed"}), 400
    
    # Update exercise record
    end_time = datetime.now()
    start_time = datetime.fromisoformat(exercise_record["start_time"])
    duration_seconds = (end_time - start_time).total_seconds()
    duration_minutes = int(duration_seconds / 60)
    
    exercise_record["end_time"] = end_time.isoformat()
    exercise_record["duration"] = f"{duration_minutes} min"
    exercise_record["status"] = "completed"
    
    _save_exercise_activity(exercise_data)
    
    print(f"[EXERCISE] User {user_id} completed {exercise_record['exercise_type']} - Duration: {duration_minutes} min")
    
    return jsonify({
        "success": True,
        "message": "Exercise completed successfully",
        "exercise": exercise_record
    }), 200

@app.route("/api/exercise/user/<int:user_id>", methods=["GET", "OPTIONS"])
def get_user_exercises(user_id):
    """Get user's exercise data including today's activity and weekly stats"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    # Load exercise data
    exercise_data = _load_exercise_activity()
    
    # Get user's exercises
    user_exercises = [ex for ex in exercise_data["exercise_activity"] if ex["user_id"] == user_id]
    
    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Find today's exercise
    today_exercise = None
    for exercise in user_exercises:
        if exercise["date"] == today:
            today_exercise = exercise
            break
    
    # Calculate weekly stats (last 7 days)
    weekly_stats = []
    for i in range(6, -1, -1):
        day_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_name = (datetime.now() - timedelta(days=i)).strftime("%a")
        
        completed = any(ex["date"] == day_date and ex["status"] == "completed" for ex in user_exercises)
        
        weekly_stats.append({
            "day": day_name,
            "date": day_date,
            "completed": completed
        })
    
    # Calculate weekly completion count
    completed_days = sum(1 for stat in weekly_stats if stat["completed"])
    
    return jsonify({
        "success": True,
        "todayExercise": today_exercise,
        "weeklyStats": weekly_stats,
        "weeklyCompletion": {
            "completed": completed_days,
            "total": 7
        },
        "totalExercises": len(user_exercises),
        "completedExercises": len([ex for ex in user_exercises if ex["status"] == "completed"])
    }), 200

from datetime import datetime, timedelta

if __name__ == "__main__":
    print("\n[INFO] Starting Flask server on http://127.0.0.1:5000")
    print("[INFO] Exercise endpoints registered:")
    print("  - POST /api/exercise/start")
    print("  - POST /api/exercise/complete")
    print("  - GET  /api/exercise/user/<user_id>")
    print("\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
