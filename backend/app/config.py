from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:localdev@localhost:5432/kb"

    embed_base_url: str = "http://192.168.0.241:8080/v1"
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024

    llm_base_url: str = "http://192.168.0.241:11434/v1"
    llm_model: str = "llama3.3:70b-instruct-q4_K_M"
    llm_api_key: str = "ollama"

    docs_chunk_size: int = 800
    docs_chunk_overlap: int = 100
    docs_top_k: int = 5

    max_agent_iterations: int = 8
    log_level: str = "INFO"


settings = Settings()
