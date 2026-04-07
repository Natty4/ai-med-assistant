# src/retrieval/retriever.py

import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from config.settings import INDEX_DIR, EMBEDDING_MODEL, RETRIEVER_K

class MedicalRetriever:
    def __init__(self):
        print("   → Loading embeddings model...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            cache_folder="./models/embeddings_cache",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        print("   → Loading FAISS index...")
        self.vectorstore = FAISS.load_local(
            str(INDEX_DIR),
            self.embeddings,
            allow_dangerous_deserialization=True
        )
        # For Object-as-a-Doc, K should be small (e.g., 3-5)
        self.k = 5 
        print(f"   → Retriever ready (Object-as-a-Doc mode, k={self.k})")

    def get_embeddings(self):
        return self.embeddings
    
    def retrieve_with_personalization(self, query: str, profile: dict = None, 
                                     severity: str = "LOW", symptoms: List[str] = None) -> Dict[str, List[Document]]:
        """Simplified retrieval for full-context documents"""
        
        # 1. Build an augmented query
        search_query = query
        if symptoms:
            search_query += " " + " ".join(symptoms)
        
        # 2. Initial retrieval (get more than K to allow for scoring/filtering)
        raw_docs = self.vectorstore.similarity_search(search_query, k=10)
        
        # 3. Score and Rank
        scored_docs = []
        for doc in raw_docs:
            score = 1.0
            content_lower = doc.page_content.lower()
            
            # Boost if the specific condition name is in the query
            condition_name = doc.metadata.get("condition", "").lower()
            if condition_name in search_query.lower():
                score += 5.0
            
            # Boost based on keyword overlap (Symptoms)
            if symptoms:
                match_count = sum(1 for s in symptoms if s.lower() in content_lower)
                score += (match_count * 2.0)

            # Personalization Boost
            if profile:
                # Boost if user has a chronic condition that matches this document
                chronic = profile.get("chronic_conditions", [])
                if any(c.lower() in condition_name for c in chronic):
                    score += 3.0
                
                # Age-based risk boosting
                age = profile.get("age", 0)
                if (age > 65 or age < 12) and doc.metadata.get("risk_level") == "HIGH":
                    score += 2.0

            scored_docs.append((doc, score))
        
        # Sort by the new calculated score
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # 4. Final Selection
        # We split them into categories just to maintain compatibility with your LLM prompt
        final_docs = [d for d, s in scored_docs[:self.k]]
        
        result = {
            "symptom_docs": [d for d in final_docs if d.metadata.get("page_type") == "symptom"],
            "condition_docs": [d for d in final_docs if d.metadata.get("page_type") == "condition"]
        }
        
        self._log_retrieval(query, symptoms, result, scored_docs[:10])
        return result

    def _log_retrieval(self, query, symptoms, result, top_scored):
        now = datetime.now()
        log_date = now.strftime("%Y-%m-%d")
        log_file = Path("logs") / f"retrieval_{log_date}.jsonl"
        Path("logs").mkdir(exist_ok=True)
        
        log_entry = {
            "timestamp": now.isoformat(),
            "query": query,
            "top_scored_results": [
                {
                    "condition": d.metadata.get("condition"),
                    "score": round(s, 2),
                    "preview": d.page_content[:150]
                } for d, s in top_scored
            ]
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")