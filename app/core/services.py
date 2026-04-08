# app/core/services.py

import os
import re
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

    def _is_valid_query(self, text: str) -> bool:
        """Determines if the query is substantive enough to process."""
        clean_text = text.lower().strip()
        
        # Check if it's just a greeting
        if clean_text in self.greetings or len(clean_text) < 3:
            return False
            
        # Check if it has at least one 'medical' indicator or enough length
        # You can expand this list or use a regex for symptoms
        return True

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
        # --- GATEKEEPER STEP ---
        if not self._is_valid_query(user_text):
            return (
                "<b>I'm ready to help!</b>\n\n"
                "Please describe your symptoms or a medical condition \n"
                "<i>(e.g., 'I have a sharp pain in my lower back' or 'Tell me about diabetes').</i>\n "
                "This helps me provide accurate ICD-11 information."
            )

        # Pythonic Cleaning (No LLM used here)
        search_query = self._clean_query(user_text)
        logger.info(f"Cleaned Query for ICD: {search_query}")
        
        try:
            token = await self.get_token()
            headers = {
                'Authorization': f'Bearer {token}', 
                'Accept': 'application/json', 
                'API-Version': 'v2'
            }
            
            # ICD-11 Search
            async with httpx.AsyncClient() as client:
                search_resp = await client.get(
                    "https://id.who.int/icd/entity/search", 
                    headers=headers, 
                    params={'q': search_query, 'useFoundation': 'true'},
                    timeout=10.0
                )
                
                icd_context = "No specific match found."
                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    if search_data.get('destinationEntities'):
                        entity_url = search_data['destinationEntities'][0]['id']
                        detail_resp = await client.get(entity_url, headers=headers)
                        if detail_resp.status_code == 200:
                            icd_context = detail_resp.json()

            # Single LLM Call with HTML Instructions
            final_prompt = f"""
            SYSTEM ROLE: Professional Medical Assistant.
            CONTEXT (ICD-11 Data): {icd_context}
            USER INPUT: {user_text}
            
            TASK:
            - Provide a structured response using Telegram (<b>, <i>, <u>, <code>).
            - Use bolding for headers.
            - Structure: 
              1. A brief empathetic acknowledgment.
              2. "Potential Classification" (Based on ICD-11 data).
              3. "Insights" (Simple explanation).
              4. "Follow-up" (One question if only in the ICD-11 data or applicable).
              5. End with a Disclaimer <i>(Small text).</i> in a separate paragraph.
            
            IMPORTANT: Do not use Markdown symbols. Use ONLY HTML.
            """
            
            response = self.client.models.generate_content(
                model=settings.LLMODEL, 
                contents=final_prompt
            )
            return response.text

        except Exception as e:
            logger.error(f"Error in service: {e}")
            return "I encountered a technical hiccup. Please try again in a moment."

# Singleton Instance
medical_service = MedicalService(
    settings.ICD_CLIENT_ID,
    settings.ICD_CLIENT_SECRET,
    settings.GEMINI_API_KEY
)