import os
from pathlib import Path
from dotenv import load_dotenv

env_file = f".env.{os.getenv('APP_ENV', 'development')}"
load_dotenv(Path(__file__).parent / env_file)
load_dotenv(Path(__file__).parent / ".env", override=False)

# 文字/对话 LLM：与运营商解耦，只认 CHAT_*。现接火山方舟 Coding Plan（glm-5.2，开 thinking），
# 将来换 Deepseek/其它只改 .env 的值，不动代码。火山 base 必须走 /api/coding/v3
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "")
CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
CHAT_MODEL = os.getenv("CHAT_MODEL", "glm-5.2")
CHAT_THINKING = os.getenv("CHAT_THINKING", "true").lower() in ("1", "true", "yes")

# 图片生成：现接阿里云通义万相。成本高，默认关闭（IMAGE_ENABLED=false 时跳过生成，imageKey 置空）
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://dashscope.aliyuncs.com")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "wanx2.1-t2i-turbo")  # 便宜款(~¥0.14/张)，wanx.py 自动走异步 endpoint
IMAGE_ENABLED = os.getenv("IMAGE_ENABLED", "false").lower() in ("1", "true", "yes")

# 语音 ASR + TTS：现接阿里云 DashScope（与图片同厂但独立配置，可各自切换）
VOICE_API_KEY = os.getenv("VOICE_API_KEY", "")
VOICE_BASE_URL = os.getenv("VOICE_BASE_URL", "https://dashscope.aliyuncs.com")
ASR_MODEL = os.getenv("ASR_MODEL", "qwen3-asr-flash")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/speakup")
PORT = int(os.getenv("PORT", "3001"))

# Alibaba Cloud OSS
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com")
OSS_BUCKET = os.getenv("OSS_BUCKET", "speakup-dev")
