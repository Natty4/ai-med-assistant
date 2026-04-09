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
            "from", "pain", "my", "is", "it", "with", "and", "in", "on", "was",
            "what", "why"
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
        if redis_client:
            try:
                # Increment the global search counter for this specific term
                await redis_client.hincrby("stats:condition_searches", search_query, 1)
            except Exception as e:
                logger.warning(f"Failed to update global stats: {e}")
                
        cache_key = f"icd_cache:{search_query.replace(' ', '_')}"
        icd_context = None

        # Try Redis Cache
        if redis_client:
            try:
                cached_res = await redis_client.get(cache_key)
                if cached_res:
                    icd_context = json.loads(cached_res)
                    logger.info(f"⚡ Redis Cache Hit: {search_query}")
            except Exception as e:
                logger.warning(f"Redis lookup failed, falling back to memory: {e}")

        # Try Memory Cache (If Redis failed or returned nothing)
        if not icd_context and cache_key in self._memory_cache:
            icd_context = self._memory_cache[cache_key]
            logger.info(f"🧠 Memory Cache Hit: {search_query}")

        # Fetch from API if still no context
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
        context_str = json.dumps(icd_context) if icd_context else "General medical knowledge (No direct ICD-11 match)."

        # Fetch the patient profile
        profile = await self.get_user_profile(user_id)
        profile_summary = json.dumps(profile)

        final_prompt = f"""
            <SYSTEM_ROLE>
                You are a highly skilled Medical Triage Assistant (Persona: 2026 Digital Health Professional). 
                Your goal is to provide structured, safe, and helpful medical insights based on ICD-11 data and user history.
            </SYSTEM_ROLE>

            <CONTEXT>
                ICD-11 Data: {context_str}
                Patient Profile: {profile_summary}
                Current User Input: {user_text}
            </CONTEXT>

            <OPERATIONAL_RULES>
                1. SAFETY FIRST: If the user input indicates a life-threatening emergency (e.g., severe chest pain, stroke symptoms, difficulty breathing), STOP everything and provide an immediate, bolded EMERGENCY WARNING to call local emergency services.
                2. NON-DIAGNOSTIC TONE: Never say "You have X." Use clinical phrasing: "Your symptoms are consistent with...", "Possible considerations include...", or "Based on the data, this could be...".
                3. TRIAGE NURSE BEHAVIOR: If the user's description is vague, ask exactly 2-3 targeted follow-up questions regarding Duration, Severity (1-10), or Triggers.
                4. HISTORY AWARENESS: Fact-check the advice against the Patient Profile. If they have a condition (e.g., Hypertension), mention how it might relate to the current symptom.
            </OPERATIONAL_RULES>

            <OUTPUT_STRUCTURE>
                Respond ONLY using HTML tags (<b>, <i>, <code>). Do NOT use Markdown (no asterisks, no hashtags).

                1. <b>Condition Summary</b>: A brief, plain-English explanation.
                2. <b>Triage Level</b>: Clearly state if they should seek: EMERGENCY ROOM, URGENT CARE, or HOME CARE.
                3. <b>Management & Prevention</b>:
                - <i>Short-term</i>: Immediate steps for relief.
                - <i>Long-term</i>: Prevention strategies.
                4. <b>The Do's & Not to Do's</b>:
                - List positive actions and critical warnings.
            </OUTPUT_STRUCTURE>

            <DATA_EXTRACTION>
                If the user mentioned NEW personal info (age, weight, conditions, meds), you MUST append a JSON block at the very end.
                Format: JSON_UPDATE: {{"demographics": {{...}}, "chronic_conditions": [...], "medications": [...]}}
            </DATA_EXTRACTION>

                End your response with this exact disclaimer:
            <blockquote expandable><b>DISCLAIMER</b>\n\n This assistant provides information based on ICD-11 data for educational purposes only. It is NOT a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of your physician.</blockquote expandable>
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
            headers = {
                'Authorization': f'Bearer {token}', 
                'Accept': 'application/json', 
                'Accept-Language': 'en', 
                'API-Version': 'v2'
            }
            
            # Search for the query
            search_resp = await self.http_client.get(
                "https://id.who.int/icd/entity/search", 
                headers=headers, 
                params={'q': query, 'useFoundation': 'true'},
                follow_redirects=True
            )
            
            if search_resp.status_code != 200:
                return None

            results = search_resp.json().get('destinationEntities', [])
            if not results:
                return None

            # Fetch top 3 matches to build a "Knowledge Bundle"
            rich_bundle = []
            for entity in results[:3]:
                # The ID returned is often http://id.who.int/... 
                # follow_redirects=True handles the jump to https
                try:
                    detail_resp = await self.http_client.get(
                        entity['id'], 
                        headers=headers, 
                        timeout=10,
                        follow_redirects=True 
                    )
                    
                    if detail_resp.status_code == 200:
                        d = detail_resp.json()
                        rich_bundle.append({
                            "title": d.get("title", {}).get("@value"),
                            "definition": d.get("definition", {}).get("@value", "No definition available."),
                            "longDefinition": d.get("longDefinition", {}).get("@value", "No longDefinition available."),
                            "synonyms": [s.get("label", {}).get("@value") for s in d.get("synonym", [])],
                            "foundationChild": [c.get("label", {}).get("@value") for c in d.get("foundationChildEntities", [])[:5]]
                        })
                except Exception as e:
                    logger.error(f"Error fetching detail for {entity['id']}: {e}")

            return rich_bundle if rich_bundle else None

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