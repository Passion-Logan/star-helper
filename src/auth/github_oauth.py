import httpx
import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from PySide6.QtCore import QThread, Signal

from src.utils.config import GITHUB_CLIENT_ID, load_config, save_config

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPE = "read:user public_repo"
KEYRING_SERVICE = "StarHelper"
KEYRING_ACCOUNT = "github_access_token"


class DeviceFlowThread(QThread):
    """后台线程：轮询 GitHub 等待用户授权"""
    code_received = Signal(str, str)  # user_code, verification_uri
    token_received = Signal(str)
    error = Signal(str)

    def run(self):
        headers = {"Accept": "application/json"}
        try:
            resp = httpx.post(DEVICE_CODE_URL, data={
                "client_id": GITHUB_CLIENT_ID, "scope": SCOPE
            }, headers=headers)
            data = resp.json()
            if "device_code" not in data:
                err_msg = data.get("error_description") or data.get("error") or f"请求失败: {data}"
                self.error.emit(err_msg)
                return
            device_code = data["device_code"]
            interval = data.get("interval", 5)
            self.code_received.emit(data["user_code"], data["verification_uri"])

            # 轮询等待授权
            while True:
                for _ in range(interval):
                    if self.isInterruptionRequested():
                        return
                    self.sleep(1)
                if self.isInterruptionRequested():
                    return
                resp = httpx.post(ACCESS_TOKEN_URL, data={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                }, headers=headers)
                result = resp.json()
                if "access_token" in result:
                    token = result["access_token"]
                    save_token(token)
                    self.token_received.emit(token)
                    return
                elif result.get("error") == "slow_down":
                    interval = result.get("interval", interval + 5)
                elif result.get("error") == "expired_token":
                    self.error.emit("授权超时，请重试")
                    return
                elif result.get("error") == "access_denied":
                    self.error.emit("用户拒绝授权")
                    return
        except Exception as e:
            self.error.emit(str(e))


def get_saved_token():
    token = get_keyring_token()
    if token:
        return token

    cfg = load_config()
    token = cfg.get("access_token")
    if token:
        save_token(token)
    return token


def save_token(token):
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, token)
        remove_config_token()
    except KeyringError:
        cfg = load_config()
        cfg["access_token"] = token
        save_config(cfg)


def get_keyring_token():
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except KeyringError:
        return None


def remove_config_token():
    cfg = load_config()
    if "access_token" in cfg:
        cfg.pop("access_token", None)
        save_config(cfg)


def logout():
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except (KeyringError, PasswordDeleteError):
        pass
    remove_config_token()
