# app/core/services.py

import os
import re
import json
import httpx
import logging
import redis.asyncio as redis
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)


redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    # FIX FOR CROSS-PROVIDER CONNECTION:
    socket_timeout=5.0,            # Don't wait forever for a response
    socket_connect_timeout=5.0,    # Timeout if connection takes too long
    socket_keepalive=True,         # Keep the TCP socket open
    health_check_interval=30,      # Ping the server every 30s to keep connection alive
    retry_on_timeout=True          # Automatically retry once if connection drops
)

class MedicalService:
    def __init__(self, icd_id, icd_secret, gemini_key):
        self.icd_id = icd_id
        self.icd_secret = icd_secret
        self.client = genai.Client(api_key=gemini_key)
        self.token = None
        self.load_local_keywords()
        
        # Stop words for cleaning queries
        self.stop_words = {
            "i", "have", "a", "the", "feel", "like", "am", "suffering", 
            "from", "pain", "my", "is", "it", "with", "and", "in", "on", "was"
        }
        # FIX: Persistent client with connection pooling
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"Connection": "keep-alive"}
        )

    def load_local_keywords(self):
        try:
            with open("icd_keywords.json", "r") as f:
                data = json.load(f)
                self.medical_vocabulary = set(data["keywords"])
        except FileNotFoundError:
            logger.error("icd_keywords.json not found!")
            self.medical_vocabulary = set()

    def _is_valid_query(self, text: str) -> bool:
        user_words = set(re.findall(r'\b[a-z]{4,}\b', text.lower()))
        return any(word in self.medical_vocabulary for word in user_words)

    def _clean_query(self, text: str) -> str:
        words = re.findall(r'\w+', text.lower())
        filtered = [w for w in words if w not in self.stop_words]
        return " ".join(filtered) if filtered else text

    async def get_token(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://icdaccessmanagement.who.int/connect/token",
                data={'client_id': self.icd_id, 'client_secret': self.icd_secret, 'scope': 'icdapi_access', 'grant_type': 'client_credentials'},
                timeout=10.0
            )
            resp.raise_for_status()
            return resp.json()['access_token']

    async def get_grounded_response(self, user_text):
        if not self._is_valid_query(user_text):
            return "<b>I'm ready to help!</b>\n\nPlease describe your symptoms briefly."

        search_query = self._clean_query(user_text)
        cache_key = f"icd_cache:{search_query.replace(' ', '_')}"
        
        try:
            # FIX: Check Redis with a local try/except to prevent total crash
            cached_res = await redis_client.get(cache_key)
        except Exception as e:
            logger.error(f"Redis link failed: {e}")
            cached_res = None

        if cached_res:
            icd_context = json.loads(cached_res)
        else:
            icd_context = await self._fetch_icd_data(search_query)
            if icd_context:
                try:
                    await redis_client.setex(cache_key, 86400, json.dumps(icd_context))
                except: pass

        context_str = json.dumps(icd_context) if icd_context else "No specific match found."
        
        final_prompt = f"""System: Use this ICD data: {context_str}. 
                        User said: {user_text}. 
                        Explain the condition simply.
                        Provide a structured response using Telegram HTML (<b>, <i>).
                        Include <blockquote expandable><b>DISCLAIMER</b>\n...</blockquote>
                        """
        try:
            response = self.client.models.generate_content(model=settings.LLMODEL, contents=final_prompt)
            return response.text
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return "⚠️ Service busy. Please try again."

    async def _fetch_icd_data(self, query):
        try:
            token = await self.get_token()
            headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Accept-Language': 'en', 'API-Version': 'v2'}
            search_resp = await self.http_client.get(
                "https://id.who.int/icd/entity/search", 
                headers=headers, 
                params={'q': query, 'useFoundation': 'true'}
            )
            
            if search_resp.status_code == 200:
                data = search_resp.json()
                if data.get('destinationEntities'):
                    detail_resp = await self.http_client.get(
                        data['destinationEntities'][0]['id'], 
                        headers=headers
                    )
                    return detail_resp.json() if detail_resp.status_code == 200 else None
            return None
        except Exception as e:
            logger.error(f"ICD Fetch Error: {e}")
            return None
        
    # Cleanup method for when the bot shuts down
    async def close_connections(self):
        await self.http_client.aclose()
        
# Singleton Instance
medical_service = MedicalService(
    settings.ICD_CLIENT_ID,
    settings.ICD_CLIENT_SECRET,
    settings.GEMINI_API_KEY
)