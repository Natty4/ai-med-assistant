# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    ICD_CLIENT_ID: str
    ICD_CLIENT_SECRET: str
    BOT_TOKEN: str
    WEBHOOK_URL: str
    LLMODEL: str
    
    # Redis Configuration
    REDIS_URL: str
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )
    
    ADMIN_IDS: str = ""

    @property
    def admin_list(self) -> list[int]:
        return [int(x) for x in self.ADMIN_IDS.split(",") if x]

settings = Settings()