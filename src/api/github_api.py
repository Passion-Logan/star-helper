"""GitHub REST API 封装:拉取 starred 仓库列表、取消 star 以及获取用户信息。

涉及网络 I/O 的操作都放在 QThread 中,避免阻塞 UI;同步调用仅用于必须及时拿到结果
的轻量请求(如登录后立即查询用户名)。
"""

import httpx
from PySide6.QtCore import QThread, Signal

API_BASE = "https://api.github.com"


class FetchStarsThread(QThread):
    """后台拉取所有 starred repos,支持分页与增量同步。

    通过 since_starred_at 参数实现增量:遇到比本地最新 starred_at 更早的条目即停止,
    避免每次都全量拉取数千条记录浪费配额。
    """
    progress = Signal(int, int)  # current_page, total_estimated(-1 表示未知)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, token, since_starred_at="", parent=None):
        super().__init__(parent)
        self.token = token
        # since_starred_at 为空表示首次同步(全量拉取)
        self.since_starred_at = since_starred_at or ""

    def run(self):
        headers = {
            "Authorization": f"token {self.token}",
            # star+json 媒体类型会让响应额外包含 starred_at 字段(用于排序与增量)
            "Accept": "application/vnd.github.v3.star+json",
        }
        stars = []
        page = 1
        try:
            while True:
                # 在每次网络往返前后都检查中断请求,以便用户随时取消
                if self.isInterruptionRequested():
                    return
                resp = httpx.get(
                    f"{API_BASE}/user/starred",
                    # per_page 取上限 100,减少分页次数
                    params={"per_page": 100, "page": page},
                    headers=headers, timeout=30
                )
                if self.isInterruptionRequested():
                    return
                if resp.status_code == 401:
                    # token 失效需要 UI 引导用户重新登录,而非笼统地报错
                    self.error.emit("Token 已失效，请重新登录")
                    return
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    # 空数组表示已到末页,正常退出
                    break
                should_stop = False
                for item in data:
                    starred_at = item.get("starred_at", "")
                    # 增量同步:遇到老于本地最新时间的条目就标记可以收工
                    # 仍需 continue 完成当前页解析,避免遗漏同页中更新的项
                    if self.since_starred_at and starred_at and starred_at <= self.since_starred_at:
                        should_stop = True
                        continue
                    repo = item["repo"]
                    # 只挑数据库实际需要的字段,丢弃 owner/license 等大量元数据
                    stars.append({
                        "id": repo["id"],
                        "full_name": repo["full_name"],
                        "description": repo.get("description") or "",
                        "language": repo.get("language") or "",
                        "url": repo["html_url"],
                        "starred_at": starred_at,
                        "topics": repo.get("topics", []),
                    })
                # total 未知时传 -1,让 UI 自行决定进度条样式
                self.progress.emit(page, -1)
                if should_stop:
                    break
                page += 1
            self.finished.emit(stars)
        except Exception as e:
            self.error.emit(str(e))


class UnstarRepoThread(QThread):
    """后台取消 GitHub Star。

    放在线程里是因为单次取消也会发起一次 HTTPS 请求,在网络较慢时仍会卡 UI。
    """
    finished = Signal(str)
    error = Signal(str, str)  # full_name, msg

    def __init__(self, token, full_name, parent=None):
        super().__init__(parent)
        self.token = token
        self.full_name = full_name

    def run(self):
        try:
            resp = httpx.delete(
                f"{API_BASE}/user/starred/{self.full_name}",
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15,
            )
            if self.isInterruptionRequested():
                return
            if resp.status_code == 401:
                self.error.emit(self.full_name, "Token 已失效，请重新登录")
                return
            # 204 = 已成功取消;404 = 已经不是 starred 状态,本地视为成功
            if resp.status_code not in (204, 404):
                resp.raise_for_status()
            self.finished.emit(self.full_name)
        except Exception as e:
            # 中断态下抛出的异常往往是 socket 被关掉导致,不应再展示给用户
            if not self.isInterruptionRequested():
                self.error.emit(self.full_name, str(e))


def fetch_user_info(token):
    """同步获取当前 token 对应的用户信息(用户名、头像、邮箱等)。"""
    resp = httpx.get(f"{API_BASE}/user", headers={
        "Authorization": f"token {token}", "Accept": "application/json"
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()
