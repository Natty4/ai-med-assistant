# src/indexing/vector_store.py

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from config.settings import INDEX_DIR, EMBEDDING_MODEL
from src.chunking.chunker import create_intent_chunks
import shutil
import pickle

def build_vector_store():
    """Builds a ChromaDB index with metadata persistence."""
    docs = create_intent_chunks()
    if not docs:
        raise ValueError("No documents to index!")
    
    # Refresh Directory
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"   → Building ChromaDB with {len(docs)} docs...")
    
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        cache_folder="./models/embeddings_cache",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    
    # Initialize Chroma and add documents
    # LangChain's Chroma wrapper handles the persistence automatically
    vectorstore = Chroma.from_documents(
        documents=docs, 
        embedding=embeddings,
        persist_directory=str(INDEX_DIR),
        collection_name="nhs_medical_data"
    )
    
    # Save a metadata snapshot for debugging/UI purposes
    metadata_summary = {
        "total_documents": len(docs),
        "conditions": list(set(doc.metadata.get("condition", "Unknown") for doc in docs)),
        "page_types": list(set(doc.metadata.get("page_type", "") for doc in docs))
    }
    
    with open(INDEX_DIR / "metadata_summary.pkl", "wb") as f:
        pickle.dump(metadata_summary, f)
    
    print(f"✅ ChromaDB index built successfully at {INDEX_DIR}")
    return vectorstore