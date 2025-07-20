from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Load settings from a .env file
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Application Settings
    PROJECT_NAME: str = "Salesforce AI Agent Server"

    # Security: A secret key required to access the server's endpoints
    API_KEY: str

    # Gemini API
    GEMINI_API_KEY: str

    # Salesforce Credentials (Username-Password Flow)
    SALESFORCE_USERNAME: str
    SALESFORCE_PASSWORD: str
    SALESFORCE_SECURITY_TOKEN: str
    SALESFORCE_INSTANCE_URL: str

# Create a single, importable settings instance
settings = Settings()
