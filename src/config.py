from dataclasses import dataclass
import os
from dotenv import load_dotenv

@dataclass
class Settings:
    PEXELS_API_KEY: str
    PIXABAY_API_KEY: str
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str

    @staticmethod
    def load():
        load_dotenv()
        return Settings(
            PEXELS_API_KEY=os.getenv("PEXELS_API_KEY", ""),
            PIXABAY_API_KEY=os.getenv("PIXABAY_API_KEY", ""),
            OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            OLLAMA_MODEL=os.getenv("OLLAMA_MODEL", "llama3.1"),
            OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
            OPENAI_MODEL=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )