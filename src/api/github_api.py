import httpx
from PySide6.QtCore import QThread, Signal

API_BASE = "https://api.github.com"


class FetchStarsThread(QThread):
    """后台拉取所有 starred repos，支持分页"""
    progress = Signal(int, int)  # current_page, total_estimated
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, token, since_starred_at="", parent=None):
        super().__init__(parent)
        self.token = token
        self.since_starred_at = since_starred_at or ""

    def run(self):
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3.star+json",
        }
        stars = []
        page = 1
        try:
            while True:
                if self.isInterruptionRequested():
                    return
                resp = httpx.get(
                    f"{API_BASE}/user/starred",
                    params={"per_page": 100, "page": page},
                    headers=headers, timeout=30
                )
                if self.isInterruptionRequested():
                    return
                if resp.status_code == 401:
                    self.error.emit("Token 已失效，请重新登录")
                    return
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                should_stop = False
                for item in data:
                    starred_at = item.get("starred_at", "")
                    if self.since_starred_at and starred_at and starred_at <= self.since_starred_at:
                        should_stop = True
                        continue
                    repo = item["repo"]
                    stars.append({
                        "id": repo["id"],
                        "full_name": repo["full_name"],
                        "description": repo.get("description") or "",
                        "language": repo.get("language") or "",
                        "url": repo["html_url"],
                        "starred_at": starred_at,
                        "topics": repo.get("topics", []),
                    })
                self.progress.emit(page, -1)
                if should_stop:
                    break
                page += 1
            self.finished.emit(stars)
        except Exception as e:
            self.error.emit(str(e))


class UnstarRepoThread(QThread):
    """后台取消 GitHub Star。"""
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
            if resp.status_code not in (204, 404):
                resp.raise_for_status()
            self.finished.emit(self.full_name)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(self.full_name, str(e))


def fetch_user_info(token):
    """获取当前用户信息"""
    resp = httpx.get(f"{API_BASE}/user", headers={
        "Authorization": f"token {token}", "Accept": "application/json"
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()
