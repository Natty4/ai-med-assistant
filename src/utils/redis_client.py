import json
import logging
from typing import Dict, Optional, Any
import redis.asyncio as aioredis
import redis

from config.redis import (
    REDIS_URL, USER_PROFILE_TTL, QUERY_HISTORY_TTL,
    SESSION_TTL, NHS_CACHE_TTL
)

logger = logging.getLogger(__name__)

class RedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def init(self):
        if self._initialized:
            return
        self.async_redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.sync_redis = redis.from_url(REDIS_URL, decode_responses=True)
        self._initialized = True
        logger.info("✅ Redis connected")

    # ==================== USER PROFILE ====================
    async def save_profile(self, user_id: int, profile: dict):
        key = f"user:profile:{user_id}"
        await self.async_redis.hset(key, mapping=profile)
        await self.async_redis.expire(key, USER_PROFILE_TTL)

    async def get_profile(self, user_id: int) -> dict:
        key = f"user:profile:{user_id}"
        data = await self.async_redis.hgetall(key)
        return data or {}

    # ==================== QUERY HISTORY ====================
    async def add_query_history(self, user_id: int, entry: dict):
        key = f"user:history:{user_id}"
        await self.async_redis.lpush(key, json.dumps(entry))
        await self.async_redis.ltrim(key, 0, 99)  # keep last 100
        await self.async_redis.expire(key, QUERY_HISTORY_TTL)

    # ==================== SESSION STORE ====================
    async def save_session(self, query_id: str, data: dict):
        key = f"session:{query_id}"
        await self.async_redis.set(key, json.dumps(data), ex=SESSION_TTL)

    async def get_session(self, query_id: str) -> Optional[dict]:
        key = f"session:{query_id}"
        data = await self.async_redis.get(key)
        return json.loads(data) if data else None

    # ==================== NHS CACHE ====================
    async def cache_nhs_data(self, condition: str, data: dict):
        key = f"nhs:condition:{condition.lower()}"
        await self.async_redis.set(key, json.dumps(data), ex=NHS_CACHE_TTL)

    async def get_cached_nhs_data(self, condition: str) -> Optional[dict]:
        key = f"nhs:condition:{condition.lower()}"
        data = await self.async_redis.get(key)
        return json.loads(data) if data else None

    async def close(self):
        if hasattr(self, 'async_redis'):
            await self.async_redis.aclose()


redis_client = RedisClient()