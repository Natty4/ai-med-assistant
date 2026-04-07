import os
import logging

from src.ingestion.structurer import run_structuring
from src.indexing.vector_store import build_vector_store
from config.settings import INDEX_DIR

logger = logging.getLogger(__name__)


def bootstrap_pipeline():
    """Run ingestion + indexing only if needed"""

    # Check if index already exists
    if INDEX_DIR.exists() and any(INDEX_DIR.iterdir()):
        logger.info("✅ Index already exists — skipping ingestion & indexing")
        return

    logger.info("⚙️ Running ingestion pipeline...")
    run_structuring()

    logger.info("⚙️ Building vector store...")
    build_vector_store()

    logger.info("✅ Bootstrap complete")