from dataclasses import dataclass
from dotenv import load_dotenv
import os

@dataclass
class Settings:
    PEXELS_API_KEY: str
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str
    ELEVENLABS_MODEL: str

    @staticmethod
    def load():
        load_dotenv()
        return Settings(
            PEXELS_API_KEY=os.getenv("PEXELS_API_KEY",""),
            OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL","http://localhost:11434"),
            OLLAMA_MODEL=os.getenv("OLLAMA_MODEL","llama3.1"),
            OPENAI_API_KEY=os.getenv("OPENAI_API_KEY",""),
            OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            ELEVENLABS_API_KEY=os.getenv("ELEVENLABS_API_KEY",""),
            ELEVENLABS_VOICE_ID=os.getenv("ELEVENLABS_VOICE_ID",""),
            ELEVENLABS_MODEL=os.getenv("ELEVENLABS_MODEL","eleven_multilingual_v2")
        )