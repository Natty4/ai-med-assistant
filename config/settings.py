# config/settings.py

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent


LLM_MODELS = os.getenv("LLM_MODELS", "gemini-2.5-flash").split(",")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))


NHS_SYMPTOM_BASE_URL = "https://www.nhs.uk/symptoms/"
NHS_CONDITIONS_BASE_URL = "https://www.nhs.uk/conditions/"
DATA_RAW_SYMPTOM_DIR = BASE_DIR / "data/raw/nhs_symptoms"
DATA_RAW_CONDITIONS_DIR = BASE_DIR / "data/raw/nhs_conditions"
DATA_PROCESSED_DIR = BASE_DIR / "data/processed"
INDEX_DIR = BASE_DIR / "data/indexes/faiss_index"
SYMPTOM_LEXICON_PATH = DATA_PROCESSED_DIR / "symptom_lexicon.json"


# Retrieval & chunking
RETRIEVER_K = 8  # Increased for better context
RETRIEVER_K_SYMPTOM = 8
RETRIEVER_K_CONDITION = 6
MAX_SELF_CARE_ITEMS = 15
MAX_LIFESTYLE_ITEMS = 10
SCRAP_SYMPTOM_LIMIT = 1000
SCRAP_CONDITIONS_LIMIT = 1000


# Safety keywords for risk inference
RISK_HIGH_KEYWORDS = [
    "999", "a&e", "emergency", "heart attack", "stroke", 
    "chest pain", "difficulty breathing", "severe bleeding",
    "loss of consciousness", "seizure", "meningitis"
]
RISK_MED_KEYWORDS = [
    "111", "see a gp", "urgent", "contact your doctor",
    "persistent", "worsening", "not improving"
]

# Personalization settings
DEFAULT_PROFILE = {
    "age": 29,
    "chronic_conditions": [],
    "recent_symptoms": [],
    "history": [],
    "allergies": [],
    "medications": [],
    "lifestyle": {
        "smoking": False,
        "alcohol": False,
        "exercise_frequency": "",
        "diet_restrictions": []
    }
}

# Logging
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 7