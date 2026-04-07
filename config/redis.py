# config/redis.py


import os
from dotenv import load_dotenv

load_dotenv()

# Get individual pieces
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379)) # Force integer here
REDIS_PASS = os.getenv("REDIS_PASSWORD")
# Leapcell usually requires SSL for external connections
REDIS_SSL = os.getenv("REDIS_SSL", "true").lower() == "true" 

# TTLs stay the same
USER_PROFILE_TTL = 60 * 60 * 24 * 30
QUERY_HISTORY_TTL = 60 * 60 * 24 * 90
SESSION_TTL = 60 * 60 * 24
NHS_CACHE_TTL = 60 * 60 * 24 * 7