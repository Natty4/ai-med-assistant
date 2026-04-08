# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    ICD_CLIENT_ID: str
    ICD_CLIENT_SECRET: str
    BOT_TOKEN: str
    WEBHOOK_URL: str
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()