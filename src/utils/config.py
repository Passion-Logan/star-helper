import os
import json
from json import JSONDecodeError

APP_NAME = "StarHelper"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
DB_PATH = os.path.join(CONFIG_DIR, "stars.db")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# GitHub OAuth App - 用户需替换为自己的 Client ID
GITHUB_CLIENT_ID = "12312312312"

os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, JSONDecodeError):
            return {}
    return {}


def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
