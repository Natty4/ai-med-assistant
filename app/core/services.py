# app/core/services.py

import os
import httpx
from dotenv import load_dotenv
from google import genai

load_dotenv()
LLM = os.getenv('LLMODEL')

class MedicalService:
    def __init__(self, icd_id, icd_secret, gemini_key):
        self.icd_id = icd_id
        self.icd_secret = icd_secret
        self.client = genai.Client(api_key=gemini_key)
        self.token = None

    async def get_token(self):
        # In production, cache this in Redis for 50 mins
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://icdaccessmanagement.who.int/connect/token",
                data={'client_id': self.icd_id, 'client_secret': self.icd_secret, 
                      'scope': 'icdapi_access', 'grant_type': 'client_credentials'}
            )
            self.token = resp.json()['access_token']
            return self.token

    async def get_grounded_response(self, user_text):
        token = await self.get_token()
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'API-Version': 'v2'}
        
        async with httpx.AsyncClient() as client:
            # 1. Semantic Search
            search = await client.get("https://id.who.int/icd/entity/search", 
                                      headers=headers, params={'q': user_text, 'useFoundation': 'true'})
            data = search.json()
            if not data.get('destinationEntities'):
                return "I couldn't find a clinical match. Could you describe the symptoms differently?"

            # 2. Detail Fetch
            entity_url = data['destinationEntities'][0]['id']
            detail = (await client.get(entity_url, headers=headers)).json()
            
            # 3. Gemini Synthesis
            prompt = f"System: Use ICD-11 Data: {detail}. User said: {user_text}. Briefly explain and ask about follow-up axes. Include a disclaimer."
            response = self.client.models.generate_content(model=LLM, contents=prompt)
            return response.text
        

medical_service = MedicalService()