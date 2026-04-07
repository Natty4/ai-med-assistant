# scripts/ingest.py

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# from src.ingestion.nhs_scraper import run_scrape
from src.ingestion.structurer import run_structuring
from src.indexing.vector_store import build_vector_store
from config.settings import SCRAP_SYMPTOM_LIMIT, SCRAP_CONDITIONS_LIMIT

from src.ingestion.nhs_scraper import run_scrape_symptoms, run_scrape_conditions

if __name__ == "__main__":
    run_scrape_symptoms(limit=SCRAP_SYMPTOM_LIMIT, overwrite=False)
    run_scrape_conditions(limit=SCRAP_CONDITIONS_LIMIT, overwrite=False)
    run_structuring()
    build_vector_store()