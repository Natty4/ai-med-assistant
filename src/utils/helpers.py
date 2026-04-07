# src/utils/helpers.py

import re
from bs4 import BeautifulSoup
import json
from datetime import datetime

def clean_text(text: str) -> str:
    """text cleaning with better normalization"""
    if not text:
        return ""
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text.strip())
    # Fix common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    # Remove bullet points and special characters
    text = re.sub(r'[•●■]', '-', text)
    return text

def clean_html(soup: BeautifulSoup):
    """HTML cleaning"""
    # Remove all unnecessary elements
    for tag in soup.find_all(['nav', 'footer', 'aside', 'script', 'style', 'header', 'iframe']):
        tag.decompose()
    
    # Remove common boilerplate
    for a in soup.find_all('a', string=re.compile(r'Skip to|Back to top|Cookies|Privacy', re.I)):
        a.decompose()
    
    return soup

def infer_risk_level(text: str) -> str:
    """risk inference with better pattern matching"""
    text_lower = text.lower()
    
    # High risk patterns
    high_risk_patterns = [
        "999", "a&e", "emergency", "heart attack", "stroke", 
        "chest pain", "difficulty breathing", "severe bleeding",
        "loss of consciousness", "seizure", "meningitis"
    ]
    
    # Medium risk patterns  
    medium_risk_patterns = [
        "111", "gp", "urgent", "call your doctor",
        "persistent", "worsening", "not improving"
    ]
    
    if any(pattern in text_lower for pattern in high_risk_patterns):
        return "HIGH"
    elif any(pattern in text_lower for pattern in medium_risk_patterns):
        return "MEDIUM"
    return "LOW"

def extract_metadata(soup: BeautifulSoup) -> dict:
    """Extract metadata from NHS pages"""
    metadata = {}
    
    # Find review dates
    for p in soup.find_all("p"):
        text = p.get_text()
        if "Page last reviewed:" in text:
            match = re.search(r"Page last reviewed:\s*(\d{1,2}\s+\w+\s+\d{4})", text)
            if match:
                metadata["last_reviewed"] = match.group(1)
        if "Next review due:" in text:
            match = re.search(r"Next review due:\s*(\d{1,2}\s+\w+\s+\d{4})", text)
            if match:
                metadata["next_review_due"] = match.group(1)
    
    return metadata

def categorize_severity(symptoms, context: str = "") -> str:
    """Robust severity categorization (handles all input types safely)"""

    # Normalize symptoms → ALWAYS string
    if isinstance(symptoms, list):
        symptoms_text = " ".join(map(str, symptoms))
    elif isinstance(symptoms, str):
        symptoms_text = symptoms
    else:
        symptoms_text = str(symptoms or "")

    text = (symptoms_text + " " + (context or "")).lower()

    severe_keywords = ["severe", "unbearable", "worst", "intense", "excruciating"]
    moderate_keywords = ["moderate", "annoying", "persistent", "ongoing"]
    mild_keywords = ["mild", "slight", "minor", "little"]

    if any(word in text for word in severe_keywords):
        return "SEVERE"
    elif any(word in text for word in moderate_keywords):
        return "MODERATE"
    return "MILD"