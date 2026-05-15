from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://allocio:allocio@localhost:5432/allocio"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
