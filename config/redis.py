import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# TTLs (seconds)
USER_PROFILE_TTL = 60 * 60 * 24 * 30      # 30 days
QUERY_HISTORY_TTL = 60 * 60 * 24 * 90    # 90 days
SESSION_TTL = 60 * 60 * 24                # 24 hours
NHS_CACHE_TTL = 60 * 60 * 24 * 7          # 7 days