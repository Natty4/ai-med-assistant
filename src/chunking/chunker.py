# src/chunking/chunker.py

from langchain_core.documents import Document
import json
from pathlib import Path
from typing import List
from config.settings import DATA_PROCESSED_DIR

def create_intent_chunks() -> List[Document]:
    """
    IMPLEMENTS: Object-as-a-Doc Approach.
    Each JSONL line becomes exactly ONE Document for maximum context retention.
    """
    processed_file = DATA_PROCESSED_DIR / "nhs_structured.jsonl"
    docs = []
    
    if not processed_file.exists():
        print("Warning: No structured file found.")
        return docs
    
    with open(processed_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            
            entry = json.loads(line)
            condition = entry.get("condition", "Unknown")
            
            # 1. Start building the single Markdown "Fact Sheet"
            content_parts = [f"# Condition: {condition}"]
            
            # Add Overview if it exists
            if entry.get("overview"):
                content_parts.append(f"## Overview\n{entry['overview']}")

            # Define fields to include in the document body
            body_fields = {
                "symptoms": "Symptoms",
                "causes": "Causes",
                "self_care": "Self-Care Advice",
                "treatment": "Treatment",
                "prevention": "Prevention",
                "lifestyle_tips": "Lifestyle Tips",
                "when_to_seek_help": "When to Seek Help"
            }

            for field, title in body_fields.items():
                items = entry.get(field, [])
                if items and any(str(i).strip() for i in items):
                    # Clean and format list items
                    formatted_list = "\n".join([f"• {i.strip()}" for i in items if str(i).strip()])
                    content_parts.append(f"## {title}\n{formatted_list}")

            # 2. Join all parts into one cohesive text block
            full_content = "\n\n".join(content_parts)

            # 3. Create a single Document with full context and metadata
            doc = Document(
                page_content=full_content,
                metadata={
                    "condition": condition,
                    "page_type": entry.get("page_type", "symptom"),
                    "risk_level": entry.get("risk_level", "LOW"),
                    "source_url": entry.get("source_url", ""),
                    "last_reviewed": entry.get("last_reviewed", ""),
                    "next_review_due": entry.get("next_review_due", ""),
                }
            )
            docs.append(doc)
    
    print(f"✅ Created {len(docs)} full-context documents (Object-as-a-Doc)")
    return docs