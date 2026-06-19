import os
from pathlib import Path
from dotenv import load_dotenv

env_file = f".env.{os.getenv('APP_ENV', 'development')}"
load_dotenv(Path(__file__).parent / env_file)
load_dotenv(Path(__file__).parent / ".env", override=False)

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3.7-plus")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "wanx2.1-t2i-turbo")  # 便宜款(~¥0.14/张)，wanx.py 自动走异步 endpoint
ASR_MODEL = os.getenv("ASR_MODEL", "qwen3-asr-flash")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/speakup")
PORT = int(os.getenv("PORT", "3001"))

# Alibaba Cloud OSS
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com")
OSS_BUCKET = os.getenv("OSS_BUCKET", "speakup-dev")
