"""GitHub OAuth Device Flow 实现及 access token 持久化。

设备流(Device Flow)适用于没有可控回调地址的桌面应用:
1. 应用向 GitHub 申请 device_code 与 user_code;
2. 用户在浏览器输入 user_code 完成授权;
3. 应用按 interval 轮询 token 端点,授权成功即拿到 access_token。

Token 优先存入操作系统 keyring(Windows 凭据管理器 / macOS Keychain 等);
keyring 不可用时降级写入明文 config.json。
"""

import httpx
import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from PySide6.QtCore import QThread, Signal

from src.utils.config import GITHUB_CLIENT_ID, load_config, save_config

# GitHub Device Flow 官方端点
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
# 申请的权限范围:读取用户信息 + 操作公开仓库(取消 star 等)
SCOPE = "read:user public_repo"
# Keyring 中保存 token 时使用的命名空间
KEYRING_SERVICE = "StarHelper"
KEYRING_ACCOUNT = "github_access_token"


class DeviceFlowThread(QThread):
    """后台线程:轮询 GitHub 等待用户授权。

    放在独立 QThread 中是为了避免阻塞 Qt 主事件循环 —— 设备流轮询本身要持续数十秒。
    通过 signal 把状态回传给 UI 线程。
    """
    code_received = Signal(str, str)  # user_code, verification_uri
    token_received = Signal(str)
    error = Signal(str)

    def run(self):
        # Accept: application/json 强制 GitHub 返回 JSON 而非默认的 form 编码
        headers = {"Accept": "application/json"}
        try:
            # 第一步:申请 device_code 和 user_code
            resp = httpx.post(DEVICE_CODE_URL, data={
                "client_id": GITHUB_CLIENT_ID, "scope": SCOPE
            }, headers=headers)
            data = resp.json()
            if "device_code" not in data:
                # 优先使用 GitHub 返回的可读错误描述,便于排查 client_id 等配置问题
                err_msg = data.get("error_description") or data.get("error") or f"请求失败: {data}"
                self.error.emit(err_msg)
                return
            device_code = data["device_code"]
            # GitHub 返回建议的轮询间隔(秒),低于此值会被服务端要求 slow_down
            interval = data.get("interval", 5)
            # 把 user_code 与跳转地址回传给 UI,让用户在浏览器中完成授权
            self.code_received.emit(data["user_code"], data["verification_uri"])

            # 第二步:按 interval 轮询 token 端点直到授权完成 / 超时 / 拒绝
            while True:
                # 拆成 1 秒一次的小睡眠,以便随时响应 UI 的中断请求
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
                    # 被服务端要求降低频率;按其建议或退化的间隔继续
                    interval = result.get("interval", interval + 5)
                elif result.get("error") == "expired_token":
                    # device_code 默认 15 分钟过期,需要重新发起整个流程
                    self.error.emit("授权超时，请重试")
                    return
                elif result.get("error") == "access_denied":
                    self.error.emit("用户拒绝授权")
                    return
                # 其余 error(如 authorization_pending)直接进入下一轮轮询
        except Exception as e:
            # 网络异常或 JSON 解析错误统一上报,避免线程静默退出
            self.error.emit(str(e))


def get_saved_token():
    """优先从 keyring 读取 token;否则尝试从 config.json 读取,并迁移到 keyring。"""
    token = get_keyring_token()
    if token:
        return token

    cfg = load_config()
    token = cfg.get("access_token")
    if token:
        # 老用户的 token 还在 config 里,顺手迁移到 keyring 以获得更好的安全性
        save_token(token)
    return token


def save_token(token):
    """优先保存到 keyring;失败时降级写入 config.json 以保证可用性。"""
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, token)
        # keyring 成功后清理 config 中的明文 token,避免两处不一致
        remove_config_token()
    except KeyringError:
        # 如某些 Linux 容器内没有可用的 keyring backend,退化到配置文件方案
        cfg = load_config()
        cfg["access_token"] = token
        save_config(cfg)


def get_keyring_token():
    """安全读取 keyring;后端不可用时返回 None,由上层走 fallback 分支。"""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except KeyringError:
        return None


def remove_config_token():
    """清除 config.json 中残留的 token 字段(仅在迁移或登出时调用)。"""
    cfg = load_config()
    if "access_token" in cfg:
        cfg.pop("access_token", None)
        save_config(cfg)


def logout():
    """登出:同时清除 keyring 与 config 中的 token,确保任意来源都失效。"""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except (KeyringError, PasswordDeleteError):
        # token 不存在或后端故障都不视为错误,登出操作需保持幂等
        pass
    remove_config_token()
