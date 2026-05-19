"""应用配置管理模块：负责读写用户配置文件及定义全局路径常量。"""

import os
import json
from json import JSONDecodeError

APP_NAME = "StarHelper"
# 优先使用 Windows 的 APPDATA 目录，非 Windows 环境下回退到用户主目录
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
DB_PATH = os.path.join(CONFIG_DIR, "stars.db")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# GitHub OAuth App - 用户需替换为自己的 Client ID
# 公开的 Client ID 不属于敏感信息，可以安全地提交到代码仓库
GITHUB_CLIENT_ID = "1232131231231"

# 模块导入时即确保配置目录存在，避免后续读写时报错
os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    """加载用户配置；文件缺失或损坏时返回空字典，保证调用方始终拿到可用的 dict。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 防御性检查：若文件被手动改成非字典结构（如列表），同样视为无效配置
                return data if isinstance(data, dict) else {}
        except (OSError, JSONDecodeError):
            # 静默吞掉错误以避免首次启动或配置损坏时阻塞应用
            return {}
    return {}


def save_config(data):
    """将配置写入磁盘；使用 ensure_ascii=False 以保留中文等非 ASCII 字符的可读性。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
