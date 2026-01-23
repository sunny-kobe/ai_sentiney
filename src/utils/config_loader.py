import yaml
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from src.utils.logger import logger

# 自动加载 .env 文件中的环境变量
load_dotenv()

class ConfigLoader:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Loads configuration from config.yaml with env var substitution."""
        config_path = Path("config.yaml")
        if not config_path.exists():
            logger.critical("config.yaml not found!")
            raise FileNotFoundError("config.yaml not found")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Basic env var substitution specific for the known keys
            # For a more robust solution, we might leverage specific libraries, 
            # but simple string replacement works for our defined keys.
            gemini_key = os.getenv("GEMINI_API_KEY", "")
            feishu_webhook = os.getenv("FEISHU_WEBHOOK", "")
            
            content = content.replace("${GEMINI_API_KEY}", gemini_key)
            content = content.replace("${FEISHU_WEBHOOK}", feishu_webhook)
            
            self._config: Dict[str, Any] = {}
            self._config.update(yaml.safe_load(content))
            logger.info("Configuration loaded successfully.")
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @staticmethod
    def get_portfolio():
        return ConfigLoader().config.get('portfolio', [])

    @staticmethod
    def get_system_config():
        return ConfigLoader().config.get('system', {})

    @staticmethod
    def get_api_keys():
        return ConfigLoader().config.get('api_keys', {})
