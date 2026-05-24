import os
from pathlib import Path
from dotenv import load_dotenv

env_file = f".env.{os.getenv('APP_ENV', 'development')}"
load_dotenv(Path(__file__).parent / env_file)
load_dotenv(Path(__file__).parent / ".env", override=False)

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/speakup-dev")
PORT = int(os.getenv("PORT", "3001"))
