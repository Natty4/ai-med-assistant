# app/core/services.py

import os
import re
import json
import httpx
import logging
import asyncio
import redis.asyncio as redis
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)


try:
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=5.0,
        health_check_interval=30,
        retry_on_timeout=True
    )
except Exception as e:
    logger.error(f"⚠️ Redis Initialization Failed: {e}")
    redis_client = None

class MedicalService:
    def __init__(self, icd_id, icd_secret, gemini_key):
        self.icd_id = icd_id
        self.icd_secret = icd_secret
        self.client = genai.Client(api_key=gemini_key)
        self.token = None
        self.load_local_keywords()
        self._memory_cache = {}
        self.models = settings.model_list
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

    async def get_user_profile(self, user_id: int) -> dict:
        """Retrieves or initializes a medical profile for the user."""
        profile_key = f"profile:{user_id}"
        if not redis_client:
            return {}
        
        try:
            data = await redis_client.get(profile_key)
            return json.loads(data) if data else {
                "demographics": {},
                "chronic_conditions": [],
                "medications": [],
                "vitals": {}, # Space for IoT data (Heart rate, etc)
                "history": [] # Last 3 key medical summaries
            }
        except:
            return {}

    async def update_user_profile(self, user_id: int, new_data: dict):
        """Merges new extracted info into the existing profile."""
        if not redis_client: return
        
        current = await self.get_user_profile(user_id)
        # Deep merge logic (simplified)
        for key in ["demographics", "vitals"]:
            current[key].update(new_data.get(key, {}))
        
        for key in ["chronic_conditions", "medications"]:
            items = new_data.get(key, [])
            current[key] = list(set(current[key] + items)) # Deduplicate
            
        await redis_client.set(f"profile:{user_id}", json.dumps(current))
        
        
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

    async def get_grounded_response(self, user_text, user_id: int):
        if not self._is_valid_query(user_text):
            return "<b>I'm ready to help!</b>\n\nPlease describe your symptoms briefly."

        search_query = self._clean_query(user_text)
        cache_key = f"icd_cache:{search_query.replace(' ', '_')}"
        icd_context = None

        # 1. Try Redis Cache
        if redis_client:
            try:
                cached_res = await redis_client.get(cache_key)
                if cached_res:
                    icd_context = json.loads(cached_res)
                    logger.info(f"⚡ Redis Cache Hit: {search_query}")
            except Exception as e:
                logger.warning(f"Redis lookup failed, falling back to memory: {e}")

        # 2. Try Memory Cache (If Redis failed or returned nothing)
        if not icd_context and cache_key in self._memory_cache:
            icd_context = self._memory_cache[cache_key]
            logger.info(f"🧠 Memory Cache Hit: {search_query}")

        # 3. Fetch from API if still no context
        if not icd_context:
            icd_context = await self._fetch_icd_data(search_query)
            if icd_context:
                # Save to Memory
                self._memory_cache[cache_key] = icd_context
                # Try saving to Redis
                if redis_client:
                    try:
                        # await redis_client.setex(cache_key, 86400, json.dumps(icd_context))
                        await redis_client.set(cache_key, json.dumps(icd_context), ex=86400)
                    except:
                        pass

        context_str = json.dumps(icd_context) if icd_context else "No specific match found."
        
        # final_prompt = f"""System: Use this ICD data: {context_str}. 
        #                 User said: {user_text}. 
        #                 Explain the condition simply.
        #                 Provide a structured response using Telegram HTML (<b>, <i>, <code>).
        #                 End with <blockquote expandable><b>DISCLAIMER</b>\n\n ...</blockquote>
                        
        #                 IMPORTANT: Do not use Markdown symbols. Use ONLY HTML.
        #                 """
        # Fetch the patient profile
        profile = await self.get_user_profile(user_id)
        profile_summary = json.dumps(profile)

        final_prompt = f"""System: You are a Medical Assistant. 
                        Patient Profile: {profile_summary}.
                        Reference ICD Data: {context_str}. 
                        User said: {user_text}. 
                        
                        TASK:
                        1. Respond to the user using the ICD data and their history.
                        2. If the user mentioned new personal info (age, weight, existing disease, meds), 
                           wrap that info in a JSON block at the end like this:
                           JSON_UPDATE: {{"demographics": {{"age": 30}}, "chronic_conditions": ["Diabetes"]}}
                        
                        IMPORTANT: Do not use Markdown symbols. Use ONLY HTML.
                        """
        
        last_error = None
        for model_name in self.models:
            try:
                logger.info(f"🤖 Attempting response with model: {model_name}")
                response = self.client.models.generate_content(
                    model=model_name, 
                    contents=final_prompt
                )
                return self._process_response_and_update_profile(response.text, user_id)
            except Exception as e:
                last_error = e
                # Check if error is related to Quota (429) or Server (503/500)
                err_msg = str(e).lower()
                if "429" in err_msg or "503" in err_msg or "500" in err_msg:
                    logger.warning(f"⚠️ Model {model_name} failed ({e}). Trying next fallback...")
                    continue 
                else:
                    # If it's a different error (e.g., safety block), might want to stop
                    logger.error(f"❌ Fatal LLM Error with {model_name}: {e}")
                    break
        
        logger.error(f"All models exhausted. Last error: {last_error}")
        return "⚠️ <b>Service currently unavailable.</b>\nPlease try again in a moment."

    def _process_response_and_update_profile(self, raw_text, user_id):
        # Extract JSON_UPDATE using regex
        match = re.search(r"JSON_UPDATE:\s*(\{.*?\})", raw_text, re.DOTALL)
        if match:
            try:
                new_data = json.loads(match.group(1))
                # Trigger background update (don't await to keep response fast)
                asyncio.create_task(self.update_user_profile(user_id, new_data))
                # Clean the JSON from the text shown to user
                return raw_text.replace(match.group(0), "").strip()
            except: pass
        return raw_text
    
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
        if redis_client:
            await redis_client.close()
        
# Singleton Instance
medical_service = MedicalService(
    settings.ICD_CLIENT_ID,
    settings.ICD_CLIENT_SECRET,
    settings.GEMINI_API_KEY
)