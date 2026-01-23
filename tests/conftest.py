
import os
import sys
from pathlib import Path

# Add project root to python path to allow importing modules from src
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set dummy env vars for testing
os.environ["GEMINI_API_KEY"] = "test_gemini_key"
os.environ["FEISHU_WEBHOOK"] = "https://open.feishu.cn/open-apis/bot/v2/hook/test_hook"
