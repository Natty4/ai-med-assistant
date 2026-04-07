# config/redis.py


import os
from dotenv import load_dotenv

load_dotenv()

# Build the URL from individual pieces to be safer
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASS = os.getenv("REDIS_PASSWORD", "")

if REDIS_PASS:
    # Notice the : before the password
    REDIS_URL = f"redis://:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    

# TTLs (seconds)
USER_PROFILE_TTL = 60 * 60 * 24 * 30      # 30 days
QUERY_HISTORY_TTL = 60 * 60 * 24 * 90    # 90 days
SESSION_TTL = 60 * 60 * 24                # 24 hours
NHS_CACHE_TTL = 60 * 60 * 24 * 7          # 7 days