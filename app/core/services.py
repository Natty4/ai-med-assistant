# app/core/services.py

# app/core/services.py

import os
import httpx
import logging
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)

LLM = os.getenv('LLMODEL', 'gemini-2.5-flash')

class MedicalService:
    def __init__(self, icd_id, icd_secret, gemini_key):
        self.icd_id = icd_id
        self.icd_secret = icd_secret
        self.client = genai.Client(api_key=gemini_key)
        self.token = None

    async def get_token(self):
        """Fetch OAuth2 token with 10s timeout."""
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
        """Empathic, grounded processing of medical concerns."""
        
        # 1. Clean Keyword Extraction (Technical grounding)
        extract_prompt = (
            f"Extract medical keywords from: '{user_text}'. "
            "Return only the keywords for database search."
        )
        extraction = self.client.models.generate_content(model=LLM, contents=extract_prompt)
        search_query = extraction.text.strip()
        
        logger.info(f"ICD Search Query: {search_query}")

        token = await self.get_token()
        headers = {
            'Authorization': f'Bearer {token}', 
            'Accept': 'application/json', 
            'API-Version': 'v2'
        }
        
        async with httpx.AsyncClient() as client:
            # ICD-11 Search
            search_resp = await client.get(
                "https://id.who.int/icd/entity/search", 
                headers=headers, 
                params={'q': search_query, 'useFoundation': 'true'},
                timeout=10.0
            )
            
            icd_context = "No specific match found."
            
            # Guard against non-JSON responses
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                if isinstance(search_data, dict) and search_data.get('destinationEntities'):
                    entity_url = search_data['destinationEntities'][0]['id']
                    detail_resp = await client.get(entity_url, headers=headers)
                    if detail_resp.status_code == 200:
                        icd_context = detail_resp.json()

                # Empathetic Synthesis
                final_prompt = f"""
                SYSTEM ROLE: You are a professional, empathetic, and grounded Medical Assistant.
                
                CONTEXT (ICD-11): {icd_context}
                USER INPUT: {user_text}
                
                TASK:
                1. Acknowledge the user's concern with a supportive, professional tone.
                2. Explain the most likely medical condition based on the ICD-11 data provided.
                3. Ask one relevant follow-up question (location, duration, or severity).
                4. End with a clear medical disclaimer: "DISCLAIMER: This tool provides AI-generated info for educational purposes and is not a substitute for professional medical advice."
                """
                
                response = self.client.models.generate_content(model=LLM, contents=final_prompt)
                return response.text
            else:
                return "Hmm, I didn’t quite understand that. Could you rephrase or give me a bit more detail so I can help?"

# Singleton Instance
medical_service = MedicalService(
    settings.ICD_CLIENT_ID,
    settings.ICD_CLIENT_SECRET,
    settings.GEMINI_API_KEY
)