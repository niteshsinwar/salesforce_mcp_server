"""Configuration management for both local and cloud deployment."""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Project info
    PROJECT_NAME: str = "Salesforce MCP Server"
    VERSION: str = "1.0.0"
    
    # API Configuration
    API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    # Salesforce Configuration
    
    # Server Configuration
    PORT: int = 8000
    DEBUG: bool = True
    
    # Environment detection
    @property
    def is_local(self) -> bool:
        return os.getenv("RENDER") is None
    
    @property
    def is_cloud(self) -> bool:
        return not self.is_local
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()
