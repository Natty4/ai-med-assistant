# src/indexing/vector_store.py

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from config.settings import INDEX_DIR, EMBEDDING_MODEL
from src.chunking.chunker import create_intent_chunks
import shutil
import os
import pickle

def build_vector_store():
    """Vector store optimized for Object-as-a-Doc retrieval"""
    docs = create_intent_chunks()
    if not docs:
        raise ValueError("No documents to index!")
    
    # Clear old index
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"   → Building FAISS index with {len(docs)} full-context documents...")
    
    # Use better embeddings model
    # Note: ensure EMBEDDING_MODEL in settings is something like "BAAI/bge-small-en-v1.5" 
    # for best results with medical summaries.
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        cache_folder="./models/embeddings_cache",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True} # Essential for Cosine Similarity
    )
    
    # Create vector store
    vectorstore = FAISS.from_documents(documents=docs, embedding=embeddings)
    
    # Save FAISS index
    vectorstore.save_local(str(INDEX_DIR))
    
    # Updated metadata extraction to match the Object-as-a-Doc structure
    metadata = {
        "total_documents": len(docs),
        "conditions": list(set(doc.metadata.get("condition", "Unknown") for doc in docs)),
        "risk_levels": list(set(doc.metadata.get("risk_level", "LOW") for doc in docs)),
        # page_type is useful for filtering symptom vs condition pages
        "page_types": list(set(doc.metadata.get("page_type", "") for doc in docs))
    }
    
    with open(INDEX_DIR / "metadata.pkl", "wb") as f:
        pickle.dump(metadata, f)
    
    print(f"✅ FAISS index built with {len(docs)} documents")
    return vectorstore