# src/utils/symptom_extractor.py

import json
from pathlib import Path
import numpy as np
from langchain_huggingface import HuggingFaceEmbeddings
from config.settings import SYMPTOM_LEXICON_PATH, EMBEDDING_MODEL

class SymptomExtractor:
    """Robust symptom extractor with auto-fallback."""
    
    def __init__(self, embeddings: HuggingFaceEmbeddings = None):
        self.embeddings = embeddings or HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        self.lexicon: list[str] = []
        self.lexicon_emb_np = np.array([])

        if not SYMPTOM_LEXICON_PATH.exists():
            print("⚠️ Symptom lexicon not found. Attempting to build from nhs_structured.json...")
            self._build_fallback_lexicon()
        else:
            self._load_lexicon()

    def _load_lexicon(self):
        """Safe load."""
        try:
            with open(SYMPTOM_LEXICON_PATH, "r", encoding="utf-8") as f:
                self.lexicon = json.load(f)
            
            print(f"   → Loaded {len(self.lexicon)} symptoms from lexicon.")
            
            if self.lexicon:
                self.lexicon_embeddings = self.embeddings.embed_documents(self.lexicon)
                self.lexicon_emb_np = np.array(self.lexicon_embeddings)
        except Exception as e:
            print(f"⚠️ Failed to load lexicon: {e}. Using fallback.")
            self._build_fallback_lexicon()

    def _build_fallback_lexicon(self):
        """Create a basic lexicon from structured data if file is missing."""
        structured_path = Path("data/processed/nhs_structured.json")
        if structured_path.exists():
            try:
                with open(structured_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                symptoms_set = set()
                for entry in data:
                    for sym in entry.get("symptoms", []):
                        if isinstance(sym, str) and len(sym.strip()) > 3:
                            symptoms_set.add(sym.strip())
                self.lexicon = sorted(list(symptoms_set))
                print(f"   → Built fallback lexicon with {len(self.lexicon)} symptoms.")
                
                # Save it for next time
                SYMPTOM_LEXICON_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(SYMPTOM_LEXICON_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.lexicon, f, ensure_ascii=False)
            except:
                self.lexicon = ["headache", "pain", "fever", "cough", "nausea", "vomiting", "fatigue"]
                print("   → Using minimal fallback symptom list.")
        else:
            self.lexicon = ["headache", "pain", "fever", "cough", "nausea", "vomiting", "fatigue"]
            print("   → Using minimal fallback symptom list (no structured data found).")

        if self.lexicon:
            self.lexicon_embeddings = self.embeddings.embed_documents(self.lexicon)
            self.lexicon_emb_np = np.array(self.lexicon_embeddings)

    def extract(self, query: str, top_k: int = 8, threshold: float = 0.58) -> list[str]:
        """Always safe — never returns None or raises."""
        if not query or not query.strip():
            return []
        if len(self.lexicon) == 0:
            return [query.strip()]

        try:
            query_emb = np.array(self.embeddings.embed_query(query))
            similarities = np.dot(self.lexicon_emb_np, query_emb)
            top_indices = np.argsort(similarities)[::-1][:top_k * 2]

            extracted = []
            for idx in top_indices:
                if similarities[idx] >= threshold:
                    extracted.append(self.lexicon[idx])
                if len(extracted) >= top_k:
                    break
            return extracted
        except:
            return [query.strip()]  # Ultimate fallback