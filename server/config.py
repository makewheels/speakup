import os
from pathlib import Path
from dotenv import load_dotenv

env_file = f".env.{os.getenv('APP_ENV', 'development')}"
load_dotenv(Path(__file__).parent / env_file)
load_dotenv(Path(__file__).parent / ".env", override=False)

# 文字/对话 LLM：与运营商解耦，只认 CHAT_*。现接火山方舟 Agent Plan。
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "")
CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
CHAT_MODEL = os.getenv("CHAT_MODEL", "ark-code-latest")
CHAT_THINKING = os.getenv("CHAT_THINKING", "false").lower() in ("1", "true", "yes")

# 图片生成：火山方舟 Agent Plan Seedream。默认仍关闭，避免自动补题意外消耗额度。
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY") or CHAT_API_KEY
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "doubao-seedream-5.0-lite")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "2560x1440")
IMAGE_ENABLED = os.getenv("IMAGE_ENABLED", "false").lower() in ("1", "true", "yes")

# 语音 ASR + TTS：火山 openspeech Agent Plan 专属入口。
VOICE_API_KEY = os.getenv("VOICE_API_KEY") or CHAT_API_KEY
VOICE_APP_KEY = os.getenv("VOICE_APP_KEY", "plan")
VOICE_BASE_URL = os.getenv("VOICE_BASE_URL", "https://openspeech.bytedance.com/api/v3/plan")
VOICE_WS_BASE_URL = os.getenv("VOICE_WS_BASE_URL", "wss://openspeech.bytedance.com/api/v3/plan")
VOICE_TTS_URL = os.getenv("VOICE_TTS_URL", f"{VOICE_BASE_URL}/tts/unidirectional")
VOICE_ASR_URL = os.getenv("VOICE_ASR_URL", f"{VOICE_WS_BASE_URL}/sauc/bigmodel_nostream")
TTS_MODEL = os.getenv("TTS_MODEL", "seed-tts-2.0")
TTS_RESOURCE_ID = os.getenv("TTS_RESOURCE_ID", "seed-tts-2.0")
TTS_VOICE = os.getenv("TTS_VOICE", "zh_female_vv_uranus_bigtts")
ASR_MODEL = os.getenv("ASR_MODEL", "bigmodel")
ASR_RESOURCE_ID = os.getenv("ASR_RESOURCE_ID", "volc.seedasr.sauc.duration")

# 视频生成：当前产品没入口，保留 service/脚本可用配置。Medium 套餐暂不默认 Seedance 2.0。
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY") or CHAT_API_KEY
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "doubao-seedance-1.5-pro")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/speakup")
PORT = int(os.getenv("PORT", "3001"))

# Alibaba Cloud OSS
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com")
OSS_BUCKET = os.getenv("OSS_BUCKET", "speakup-dev")
