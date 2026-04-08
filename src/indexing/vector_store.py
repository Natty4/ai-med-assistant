# src/indexing/vector_store.py
import os
import shutil
import pickle
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from config.settings import INDEX_DIR
from src.chunking.chunker import create_intent_chunks

load_dotenv()  # Ensure GOOGLE_API_KEY is available during build

def build_vector_store():
    """Builds ChromaDB index using Gemini embeddings (API-based, no local model)."""
    docs = create_intent_chunks()
    if not docs:
        raise ValueError("No documents to index!")

    # Refresh directory (force clean rebuild after embedding change)
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print(f"   → Building ChromaDB with {len(docs)} docs using Gemini embeddings...")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        # No device / cache_folder needed for API model
    )

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(INDEX_DIR),
        collection_name="nhs_medical_data"
    )

    # Metadata snapshot
    metadata_summary = {
        "total_documents": len(docs),
        "conditions": list(set(doc.metadata.get("condition", "Unknown") for doc in docs)),
        "page_types": list(set(doc.metadata.get("page_type", "") for doc in docs)),
        "embedding_model": "gemini-embedding-001"
    }

    with open(INDEX_DIR / "metadata_summary.pkl", "wb") as f:
        pickle.dump(metadata_summary, f)

    print(f"✅ ChromaDB index built successfully with Gemini embeddings at {INDEX_DIR}")
    return vectorstore