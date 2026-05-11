from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "dogmatch_db"
    db_user: str = "root"
    db_password: str = "root"

    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    allowed_origins: str = "http://localhost:3000"

    model: str = "gpt-4o"
    max_tokens: int = 1024
    max_tool_iterations: int = 5

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
