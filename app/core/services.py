# app/core/services.py

import os
import re
import json
import httpx
import logging
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)

class MedicalService:
    def __init__(self, icd_id, icd_secret, gemini_key):
        self.icd_id = icd_id
        self.icd_secret = icd_secret
        self.client = genai.Client(api_key=gemini_key)
        self.token = None
        self.load_local_keywords()
        
        # Phrases that don't need processing
        self.greetings = {
            "hi", "hello", "hey", "good morning", "good evening", 
            "who are you", "what can you do", "start", "help"
        }
        
        # Stop words for cleaning queries
        self.stop_words = {
            "i", "have", "a", "the", "feel", "like", "am", "suffering", 
            "from", "pain", "my", "is", "it", "with", "and", "in", "on", "was"
        }

    def load_local_keywords(self):
        try:
            with open("icd_keywords.json", "r") as f:
                data = json.load(f)
                # We use a set for O(1) lookup speed
                self.medical_vocabulary = set(data["keywords"])
        except FileNotFoundError:
            self.medical_vocabulary = set()

    def _is_valid_query(self, text: str) -> bool:
        clean_text = text.lower()
        
        # Check greetings
        if any(greet in clean_text for greet in self.greetings):
            return False

        # Check against official ICD keywords
        user_words = set(re.findall(r'\b[a-z]{4,}\b', clean_text))
        
        # If the user has at least one word matching the ICD-11 MMS table
        has_medical_term = any(word in self.medical_vocabulary for word in user_words)
        
        return has_medical_term

    def _clean_query(self, text: str) -> str:
        """Removes common words to improve ICD-11 search accuracy."""
        words = re.findall(r'\w+', text.lower())
        filtered = [w for w in words if w not in self.stop_words]
        return " ".join(filtered) if filtered else text

    async def get_token(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://icdaccessmanagement.who.int/connect/token",
                data={
                    'client_id': self.icd_id, 
                    'client_secret': self.icd_secret, 
                    'scope': 'icdapi_access', 
                    'grant_type': 'client_credentials'
                },
                timeout=10.0
            )
            resp.raise_for_status()
            self.token = resp.json()['access_token']
            return self.token
        
    async def get_grounded_response(self, user_text):
        if not self._is_valid_query(user_text):
            return ("<b>I'm ready to help!</b>\n\n"
                    "Please describe your symptoms briefly. This helps me "
                    "provide accurate information.")

        search_query = self._clean_query(user_text)
        icd_context = None
        error_flag = False

        try:
            token = await self.get_token()
            headers = {
                'Authorization': f'Bearer {token}', 
                'Accept': 'application/json', 
                'API-Version': 'v2'
            }
            
            async with httpx.AsyncClient() as client:
                # Search with Error Handling
                search_resp = await client.get(
                    "https://id.who.int/icd/entity/search", 
                    headers=headers, 
                    params={'q': search_query, 'useFoundation': 'true'},
                    timeout=8.0
                )
                
                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    if search_data.get('destinationEntities'):
                        entity_url = search_data['destinationEntities'][0]['id']
                        # 2. Detail Fetch with Error Handling
                        detail_resp = await client.get(entity_url, headers=headers, timeout=5.0)
                        if detail_resp.status_code == 200:
                            icd_context = detail_resp.json()
                elif search_resp.status_code != 404:
                    # Log unexpected status codes (500, 401, etc)
                    logger.warning(f"ICD API returned status: {search_resp.status_code}")
                    error_flag = True

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(f"Network error accessing ICD API: {e}")
            error_flag = True
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            error_flag = True

        # --- REFINED PROMPT FOR ERRORS ---
        # We tell the LLM if the database was unreachable so it can pivot gracefully.
        db_status = "UNAVAILABLE" if error_flag else "AVAILABLE"
        context_data = icd_context if icd_context else "No specific match in database."

        final_prompt = f"""
            SYSTEM ROLE: Professional Medical Assistant.
            DATABASE_STATUS: {db_status}
            CONTEXT (ICD-11 Data): {context_data}
            USER INPUT: {user_text}
            
            TASK:
            - Provide a structured response using Telegram (<b>, <i>, <code>).
            - Use bolding for headers.
            - Structure: 
              1. A brief empathetic acknowledgment.
              2. "Classification/Potential Condition" (Based on ICD-11 data).
              3. "Insights" (Simple explanation).
              4. "Follow-up" (One question if only in the ICD-11 data or applicable).
              5. End with <blockquote expandable>DISCLAIMER: ...</blockquote>
            
            IMPORTANT: Do not use Markdown symbols. Use ONLY HTML.
            """
            
        try:
            response = self.client.models.generate_content(
                model=settings.LLMODEL, 
                contents=final_prompt
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            return "⚠️ <b>humm</b>\nI'm currently experiencing high demand. Please wait and try again in a few minutes."

# Singleton Instance
medical_service = MedicalService(
    settings.ICD_CLIENT_ID,
    settings.ICD_CLIENT_SECRET,
    settings.GEMINI_API_KEY
)