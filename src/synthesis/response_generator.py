# src/synthesis/response_generator.py


import os
import re
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv
from rich.console import Console
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

from config.settings import LLM_MODELS, TEMPERATURE, MAX_TOKENS, DEFAULT_PROFILE
from src.retrieval.retriever import MedicalRetriever
from src.utils.symptom_extractor import SymptomExtractor
from src.utils.logging_config import get_logger
from src.utils.helpers import categorize_severity

load_dotenv()
console = Console()
logger = get_logger()

PROFILE_PATH = Path("data/processed/user_profile.json")
HISTORY_PATH = Path("data/processed/query_history.json")
STRUCTURED_JSON = Path("data/processed/nhs_structured.json")

RED_FLAG_KEYWORDS = [
    "chest pain", "difficulty breathing", "shortness of breath",
    "severe headache", "sudden vision loss", "unable to speak",
    "loss of consciousness", "seizure", "severe bleeding",
    "head injury", "stiff neck", "rash that doesn't fade",
    "confusion", "slurred speech", "weakness in arm or leg"
]

_global_instance: Optional["ResponseGenerator"] = None
_global_initialized = False


class LLMManager:
    def __init__(self):
        self.models = LLM_MODELS
        self.current_idx = 0
        self.clients = {}

    def get_llm(self):
        model_name = self.models[self.current_idx]
        if model_name not in self.clients:
            self.clients[model_name] = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                google_api_key=os.getenv("GOOGLE_API_KEY"),
            )
        return self.clients[model_name]

    def rotate(self):
        self.current_idx = (self.current_idx + 1) % len(self.models)
        logger.info(f"🔄 Rotated to model: {self.models[self.current_idx]}")


class ResponseGenerator:
    def __init__(self):
        global _global_instance
        if _global_instance is None:
            _global_instance = self
            self._initialize_components()
        else:
            # Reuse the already initialized global instance
            self.__dict__ = _global_instance.__dict__

    def _initialize_components(self):
        """Internal method called only once"""
        self.llm_manager = LLMManager()
        self.retriever = None
        self.symptom_extractor = None
        self.profile = self.load_profile()
        self.history = self.load_history()
        self.structured_db: Dict[str, dict] = {}
        self.session_id = str(uuid.uuid4())[:8]

    @classmethod
    def initialize(cls):
        """Call once at startup"""
        global _global_initialized, _global_instance
        if _global_initialized:
            return

        console.print("[dim]🔄 Pre-loading Medical Assistant...[/dim]")
        logger.info("System pre-initialization started")

        # Create and fully load the global instance
        instance = cls()  # This triggers _initialize_components
        instance.retriever = MedicalRetriever()
        instance.symptom_extractor = SymptomExtractor(
            embeddings=instance.retriever.get_embeddings()
        )
        instance.structured_db = instance.load_structured_db()

        _global_initialized = True
        console.print("[green]✅ Medical Assistant fully pre-loaded[/green]")
        logger.info("System pre-initialized successfully")


    def load_structured_db(self) -> Dict[str, dict]:
        if not STRUCTURED_JSON.exists():
            logger.warning("nhs_structured.json not found")
            return {}
        try:
            with open(STRUCTURED_JSON, encoding="utf-8") as f:
                data = json.load(f)
            return {entry["condition"].lower(): entry for entry in data}
        except Exception as e:
            logger.error(f"Failed to load structured DB: {e}")
            return {}

    def load_profile(self) -> dict:
        if PROFILE_PATH.exists():
            try:
                with open(PROFILE_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load profile", extra={"error": str(e)})
        return DEFAULT_PROFILE.copy()

    def load_history(self) -> List[Dict]:
        if HISTORY_PATH.exists():
            try:
                with open(HISTORY_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_profile(self):
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save profile", extra={"error": str(e)})

    def save_history(self):
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(self.history[-100:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save history", extra={"error": str(e)})
            
            
    def generate(self, user_query: str) -> str:
        start_time = time.time()
        user_query = user_query.strip()
        

        # === EARLY GUARD: Non-medical / invalid queries (before any retrieval or LLM) ===
        if self._is_non_medical_query(user_query):
            response = (
                "Hi! 👋 I'm a specialized medical assistant focused on Health (WHO) information "
                "about symptoms, conditions, causes, self-care, and prevention.\n\n"
                "I can help you understand health concerns, suggest when to see a GP, or give "
                "general self-care advice based on reliable sources.\n\n"
                "How can I assist with your symptoms or health question today?"
            )
            # Still log the interaction
            logger.info("Non-medical query handled early", extra={
                "session_id": self.session_id,
                "query": user_query[:200],
                "intent": "non_medical"
            })
            return response

       # Use the helpers
        symptoms = self.symptom_extractor.extract(user_query) or [user_query]
        retrieval = self.retriever.retrieve_with_personalization(user_query, self.profile, symptoms=symptoms)
        
        context = self._prepare_context(retrieval)
        prompt_text = self._build_prompt(user_query, symptoms, context)

        # Sync Invoke
        response_obj = self.llm.invoke(prompt_text)
        return response_obj.content if isinstance(response_obj, AIMessage) else str(response_obj)

        # except Exception as e:
        #     logger.error("Generation failed", extra={"error": str(e)})
        #     return f"⚠️ I encountered an error processing your request. Please try again."

    async def stream_generate(self, user_query: str):
        """Async generator that yields tokens from Gemini"""
        start_time = time.time()
        user_query = user_query.strip()
        
        # 1. Reuse your existing symptom extraction & retrieval logic
        symptoms = self.symptom_extractor.extract(user_query) or [user_query]
        import asyncio
        retrieval = await asyncio.to_thread(
            self.retriever.retrieve_with_personalization(
                user_query,
                self.profile, 
                symptoms=symptoms
                )
            )
        # 2. Build the context string (same as before)
        context = self._prepare_context(retrieval) # Move your context logic to a helper
        
        # 3. Create the prompt
        refined_prompt = self._build_prompt(user_query, symptoms, context)

        # 4. Use .astream for token-by-token delivery
        # Ensure you are using the langchain-google-genai library
        async for chunk in self.llm.astream(refined_prompt):
            yield chunk
    
    def generate_structured(self, user_query: str) -> dict:
        """Main structured response"""
        start_time = time.time()
        user_query = user_query.strip()

        if self._is_non_medical_query(user_query):
            return {
                "query_id": str(uuid.uuid4())[:12],
                "summary": "Hi! 👋 I'm a specialized medical assistant. Describe your symptoms or health concern.",
                "urgency_friendly": "",
                "condition": "General",
                "urgency_level": "LOW",
                "available_sections": [],
                "sections": {},
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            }

        # This line was failing before — now guaranteed safe
        symptoms = self.symptom_extractor.extract(user_query) or [user_query]
        retrieval = self.retriever.retrieve_with_personalization(user_query, self.profile, symptoms=symptoms)
        
        all_docs = retrieval.get("symptom_docs", []) + retrieval.get("condition_docs", [])
        main_condition = all_docs[0].metadata.get("condition", "Unknown") if all_docs else "Unknown"
        structured = self.structured_db.get(main_condition.lower(), {})

        has_red_flags = self._detect_red_flags(user_query, symptoms)
        severity = categorize_severity(symptoms)
        urgency_level = self._determine_urgency(symptoms, severity, has_red_flags, all_docs)

        urgency_friendly = {
            "HIGH": "🔴 – Please seek medical help right away or call 991.",
            "MEDIUM": "🟡 – Speak with a GP or pharmacist soon.",
            "LOW": "🟢 – This can usually be managed at home."
        }[urgency_level]

        # LLM Summary with rotation
        llm = self.llm_manager.get_llm()
        try:
            summary_prompt = f"""
                You are a friendly medical assistant.
                User query: {user_query}
                Possible condition: {main_condition}
                Key facts: {', '.join(structured.get('symptoms', [])[:4])}

                Write a short (2-4 sentence), empathetic summary. Never diagnose.
                Summary:"""
            response_obj = llm.invoke(summary_prompt)
            summary_text = response_obj.content if isinstance(response_obj, AIMessage) else str(response_obj)

        except (ResourceExhausted, TooManyRequests, Exception) as e:
            logger.warning(f"Model error: {e} → rotating")
            self.llm_manager.rotate()
            llm = self.llm_manager.get_llm()
            response_obj = llm.invoke(summary_prompt)
            summary_text = response_obj.content if isinstance(response_obj, AIMessage) else str(response_obj)            
        # Build available buttons
        section_map = {
            "overview": "Condition",
            "symptoms": "Symptoms",
            "causes": "Causes",
            "self_care": "Self-Care (Do's & Don'ts)",
            "treatment": "Treatment",
            "prevention": "Prevention",
            "lifestyle_tips": "Lifestyle Tips",
            "when_to_seek_help": "When to Seek Help",
            "images": "Images"
        }
        available = []
        for key, label in section_map.items():
            if key == "overview" and (structured.get("overview") or structured.get("condition")):
                available.append({"key": "overview", "label": label})
            elif key == "images" and structured.get("images"):
                available.append({"key": "images", "label": label})
            elif structured.get(key) and len([x for x in structured[key] if str(x).strip()]):
                available.append({"key": key, "label": label})

        if llm.model == "gemini-3.1-flash-lite-preview":
            summary_text = summary_text[0].get('text')
        return {
            "query_id": str(uuid.uuid4())[:12],
            "summary": summary_text.strip(),
            "urgency_friendly": urgency_friendly,
            "condition": main_condition,
            "urgency_level": urgency_level,
            "available_sections": available,
            "sections": structured,
            "latency_ms": round((time.time() - start_time) * 1000, 2)
        }
            
    def _detect_red_flags(self, query: str, symptoms: List[str]) -> bool:
        """Check for emergency red flags"""
        text = (query + " " + " ".join(symptoms)).lower()
        for flag in RED_FLAG_KEYWORDS:
            if flag in text:
                return True
        return False

    def _extract_symptoms(self, query: str) -> Tuple[List[str], str]:
        try:
            prompt = f"""Extract only real medical symptoms from this message as JSON.

                Message: "{query}"

                Format:
                {{"symptoms": ["symptom1"], "severity": "mild|moderate|severe"}}"""

            resp = self.llm.invoke(prompt)

            content = resp.content if isinstance(resp, AIMessage) else str(resp)

            try:
                data = json.loads(content)
                symptoms = data.get("symptoms", [])
                severity = data.get("severity", "mild")

                if not isinstance(symptoms, list):
                    symptoms = [str(symptoms)]

                return symptoms, severity

            except:
                words = re.findall(r'\b\w+\b', query.lower())
                symptoms = [w for w in words if len(w) > 3]
                return symptoms, "mild"

        except Exception as e:
            logger.error("Symptom extraction failed", extra={"error": str(e)})
            return [], "mild"

    def _determine_urgency(self, symptoms: List[str], severity: str, has_red_flags: bool, docs: List) -> str:
        """Determine urgency level based on multiple factors"""
        
        # Check for red flags first
        if has_red_flags:
            return "HIGH"
        
        # Check if any retrieved docs indicate HIGH risk
        for doc in docs:
            if doc.metadata.get('risk_level') == 'HIGH':
                return "HIGH"
        
        # Check severity
        if severity.lower() in ['severe', 'moderate']:
            return "MEDIUM"
        
        # Check if symptoms are persistent (from history)
        if len(self.history) > 0 and any(s in str(self.history[-1]) for s in symptoms):
            return "MEDIUM"
        
        return "LOW"

    def _update_history_and_profile(self, query, symptoms, severity, urgency, red_flags, matched_count):
        """Helper to keep the generate method clean"""
        symptoms_str = ", ".join(symptoms)
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "symptoms": symptoms_str,
            "urgency": urgency
        })
        self.save_history()
        
        if symptoms:
            current = self.profile.get("recent_symptoms", [])
            self.profile["recent_symptoms"] = list(dict.fromkeys(current + symptoms))[:20]
            self.save_profile()

    def _is_non_medical_query(self, query: str) -> bool:
        """Fast, zero-cost check for greetings, off-topic, or nonsense queries."""
        q = query.lower().strip()
        if len(q) < 2:
            return True
        non_medical_keywords = [
            "hi", "hello", "hey", "good morning", "good afternoon", "how are you",
            "thank you", "thanks", "bye", "goodbye", "weather", "joke", "news",
            "what's up", "how's it going", "who are you", "what can you do"
        ]
        
        
        # Very short or gibberish
        if len(q.split()) < 2 and not any(word in q for word in ["pain", "sick", "symptom", "baby", "skin", "head", "stomach"]):
            return True
        return False
    
    def _parse_to_blocks(self, raw_text: str) -> List[dict]:
        """
        Parses the mandatory Markdown template into structured UI blocks.
        """
        blocks = []
        # Split by Markdown headers (###)
        sections = re.split(r'###\s+', raw_text)
        
        for section in sections:
            if not section.strip():
                continue
                
            lines = section.strip().split('\n')
            header = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
            
            # Determine block type for UI styling
            block_type = "general"
            if "Summary" in header: block_type = "summary"
            elif "Urgency" in header: block_type = "urgency"
            elif "Do" in header or "Should" in header: block_type = "action"
            elif "Disclaimer" in header: block_type = "disclaimer"
            
            blocks.append({
                "header": header,
                "content": content,
                "type": block_type
            })
        return blocks
    
    def _prepare_context(self, retrieval: Dict) -> str:
        """Centralized logic to format retrieved docs into the prompt context."""
        all_docs = retrieval.get("symptom_docs", []) + retrieval.get("condition_docs", [])
        
        if not all_docs:
            return "No specific medical information found."

        context_parts = []
        seen_conditions = set()

        for doc in all_docs:
            cond = doc.metadata.get("condition", "Unknown")
            if cond not in seen_conditions:
                context_parts.append(f"SOURCE DATA FOR {cond.upper()}:\n{doc.page_content}")
                seen_conditions.add(cond)

        return "\n\n---\n\n".join(context_parts)

    def _build_prompt(self, query: str, symptoms: list, context: str, urgency: str = "UNKNOWN") -> str:
        """Centralized logic to build the XML-tagged prompt."""
        from config.prompts import SYSTEM_PROMPT
        
        return SYSTEM_PROMPT + f"""
            User Query: <query>{query}</query>
            Extracted Symptoms: {', '.join(symptoms)}
            Urgency: {urgency}

            MEDICAL KNOWLEDGE BASE CONTEXT:
            <context>{context}</context>

            Instructions:
            1. Use ONLY the provided context.
            2. Follow the response template EXACTLY.
            
            Response:"""
            
            
if __name__ == "__main__":
    assistant = ResponseGenerator()
    response = assistant.generate("I have a mild headache since this morning")
    print("\n" + "="*50)
    print("RESPONSE:")
    print("="*50)
    print(response)