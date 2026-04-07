# src/retrieval/retriever.py

import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from config.settings import INDEX_DIR, EMBEDDING_MODEL, RETRIEVER_K
from langchain_google_genai import GoogleGenerativeAIEmbeddings



class MedicalRetriever:
    def __init__(self):
        print("   → Loading embeddings model...")
        # self.embeddings = HuggingFaceEmbeddings(
        #     model_name=EMBEDDING_MODEL,
        #     cache_folder="./models/embeddings_cache",
        #     model_kwargs={'device': 'cpu'},
        #     encode_kwargs={'normalize_embeddings': True}
        # )
        self.embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        
        print(f"   → Connecting to ChromaDB at {INDEX_DIR}...")
        self.vectorstore = Chroma(
            persist_directory=str(INDEX_DIR),
            embedding_function=self.embeddings,
            collection_name="nhs_medical_data"
        )
        
        # Retrieval counts
        self.k_symptom = 4
        self.k_condition = 4

    def get_embeddings(self):
        return self.embeddings
        
    def retrieve_with_personalization(self, query: str, profile: dict = None, 
                                      symptoms: List[str] = None) -> Dict[str, List[Document]]:
        """
        Retrieves documents using native ChromaDB metadata filtering.
        """
        search_query = query
        if symptoms:
            search_query += " " + " ".join(symptoms)

        # 1. Native Metadata Filtering: Retrieve Symptoms
        symptom_docs = self.vectorstore.similarity_search(
            search_query, 
            k=self.k_symptom,
            filter={"page_type": "symptom"}
        )

        # 2. Native Metadata Filtering: Retrieve Conditions
        condition_docs = self.vectorstore.similarity_search(
            search_query, 
            k=self.k_condition,
            filter={"page_type": "condition"}
        )

        # 3. Optional: Personalization Reranking
        # We can still apply your custom scoring to the filtered results
        all_retrieved = symptom_docs + condition_docs
        final_results = self._rerank_results(all_retrieved, search_query, profile, symptoms)

        return final_results

    def _rerank_results(self, docs, query, profile, symptoms):
        """Applies your custom business logic/boosts to the filtered subset."""
        scored_docs = []
        for doc in docs:
            score = 1.0
            content_lower = doc.page_content.lower()
            condition_name = doc.metadata.get("condition", "").lower()

            if condition_name in query.lower(): score += 5.0
            if symptoms:
                match_count = sum(1 for s in symptoms if s.lower() in content_lower)
                score += (match_count * 2.0)
            
            if profile:
                # Age-based risk boosting
                age = profile.get("age", 0)
                if (age > 65 or age < 12) and doc.metadata.get("risk_level") == "HIGH":
                    score += 3.0

            scored_docs.append((doc, score))

        # Sort and return categorized dictionary
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        return {
            "symptom_docs": [d for d, s in scored_docs if d.metadata.get("page_type") == "symptom"],
            "condition_docs": [d for d, s in scored_docs if d.metadata.get("page_type") == "condition"]
        }

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