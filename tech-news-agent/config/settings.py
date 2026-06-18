from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure OpenAI
    azure_openai_endpoint: str = "https://YOUR-RESOURCE.openai.azure.com/"
    azure_openai_api_key: str = "your-api-key-here"
    azure_openai_deployment_name: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-02-01"

    # Agent behavior
    recency_days: int = 7
    max_articles_output: int = 20
    min_relevance_score: float = 6.0

    # Scraping
    request_timeout: int = 15
    max_retries: int = 3


# singleton — import this everywhere
settings = Settings()