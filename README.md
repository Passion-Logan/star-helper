# Star Helper

管理 GitHub Stars 的 Windows 桌面工具，目标是把 starred 仓库整理成可搜索、可打标签、可备注的本地知识库。

项目使用 Python + PySide6 构建，通过 GitHub OAuth Device Flow 登录，将 starred 仓库同步到本地 SQLite 数据库。灵感来源：[astralapp/astral](https://github.com/astralapp/astral)。

---

## 功能概览

- GitHub Device Flow 登录，token 优先保存到系统凭据管理器，失败时回退到本地配置文件。
- 全量同步 GitHub Stars，拉取仓库名称、描述、语言、star 时间和 GitHub topics。
- 增量同步，只拉取本地最新 `starred_at` 之后新增的 Stars。
- 本地搜索和筛选，支持按仓库名称、描述、topics 模糊搜索，按语言和标签过滤。
- 自定义标签管理，支持新建、重命名、删除、计数展示和拖拽排序。
- 详情面板展示仓库链接、描述、GitHub topics、自定义标签和备注。
- 详情里的 topic chip 可点击搜索，自定义标签 chip 可点击移除当前仓库的标签关联。
- 多选仓库后批量设置标签。
- 应用内取消 GitHub Star；无标签且无备注的仓库会从本地移除，有整理内容的仓库会保留本地记录。
- 标签关联和备注可导出为 JSON，也可从 JSON 导入恢复。
- 暗色/亮色主题切换，主题配置持久化保存。

---

## 目录结构

```text
star-helper/
├── src/
│   ├── main.py              # 应用入口，创建 QApplication、加载主题、启动主窗口
│   ├── __init__.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── github_oauth.py  # GitHub Device Flow OAuth 认证与 token 持久化
│   ├── api/
│   │   ├── __init__.py
│   │   └── github_api.py    # GitHub REST API：同步 Stars、取消 Star、获取用户信息
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py      # SQLite 表结构、标签、备注、搜索和清理策略
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py   # 主窗口、登录页、标签弹窗、同步和所有交互逻辑
│   │   ├── styles.py        # 暗色/亮色 QSS 主题
│   │   └── widgets.py       # FlowLayout 与 chip 标签组件
│   └── utils/
│       ├── __init__.py
│       └── config.py        # 配置目录、数据库路径、Client ID、config.json 读写
├── build.spec               # PyInstaller 打包配置
├── requirements.txt         # Python 依赖
├── LICENSE
├── .gitignore
└── README.md
```

---

## 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.10+ | 运行环境 |
| PySide6 6.6.1 | Qt 桌面 GUI |
| httpx 0.27.0 | 调用 GitHub API |
| keyring 25.0.0 | 系统凭据管理器，优先保存 GitHub access token |
| SQLite | 本地数据持久化，通过 Python 内置 `sqlite3` 使用 |
| PyInstaller 6.3.0 | 打包为 Windows 单文件 EXE |

---

## 快速开始

### 1. 安装依赖

建议先创建虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 创建 GitHub OAuth App

1. 打开 [GitHub Developer Settings](https://github.com/settings/developers)。
2. 点击 `New OAuth App`。
3. 填写信息：
   - `Application name`: `Star Helper`
   - `Homepage URL`: `http://localhost`
   - `Authorization callback URL`: `http://localhost`
4. 创建后复制 `Client ID`。
5. 打开 `src/utils/config.py`，将 `GITHUB_CLIENT_ID` 替换为你的 Client ID。
6. 在 OAuth App 设置页勾选 `Enable Device Flow`。

当前 OAuth scope 为 `read:user public_repo`。读取公开 Stars 通常不需要额外权限，但应用内取消公开仓库 Star 需要 `public_repo`。

### 3. 运行应用

```bash
python -m src.main
```

### 4. 打包 EXE

```bash
pyinstaller build.spec
```

生成文件位于 `dist/StarHelper.exe`。

---

## 使用流程

1. 启动应用，点击「使用 GitHub 登录」。
2. 浏览器会打开 GitHub 验证页面，在页面中输入应用显示的验证码。
3. 授权成功后进入主界面。
4. 点击「同步」拉取全部 starred 仓库；后续可点击「增量」只同步新增 Stars。
5. 左侧创建自定义标签，也可以拖拽自定义标签调整顺序。
6. 中间列表可搜索仓库名称、描述和 topics，也可以按语言筛选。
7. 右键仓库可设置标签、取消 Star、在浏览器中打开。
8. Ctrl/Shift 多选仓库后，可批量设置标签。
9. 右侧详情面板可查看 GitHub topics、自定义标签和备注；点击 topic chip 可快速搜索，点击自定义标签 chip 可从当前仓库移除该标签。
10. 左侧工具区可导入/导出 JSON，也可切换暗色/亮色主题或退出登录。

---

## 核心模块

### 应用入口：`src/main.py`

`main.py` 创建 `QApplication`，读取 `config.json` 中的主题配置，加载 QSS 后启动 `MainWindow`。

### 认证模块：`src/auth/github_oauth.py`

认证使用 GitHub Device Flow，适合桌面应用不提供固定回调地址的场景。

关键流程：

1. 请求 `https://github.com/login/device/code` 获取 `device_code` 和 `user_code`。
2. UI 展示 `user_code`，并打开 GitHub 验证页面。
3. `DeviceFlowThread` 后台轮询 `https://github.com/login/oauth/access_token`。
4. 获取 token 后调用 `save_token()` 持久化。

关键函数：

- `DeviceFlowThread`：后台轮询授权结果。
- `get_saved_token()`：优先从 keyring 读取 token，并兼容迁移旧版 `config.json` 里的 token。
- `save_token(token)`：优先写入系统凭据管理器，失败时写入 `config.json`。
- `logout()`：删除系统凭据和配置文件中的 token。

### API 模块：`src/api/github_api.py`

负责和 GitHub REST API 通信，耗时操作放在 `QThread` 中执行，避免阻塞 UI。

关键类/函数：

- `FetchStarsThread`：分页拉取 `/user/starred`。
  - 使用 `Accept: application/vnd.github.v3.star+json` 获取 `starred_at`。
  - 每页 100 条，直到返回空列表。
  - 支持 `since_starred_at`，用于增量同步。
  - 输出字段包括 `id`、`full_name`、`description`、`language`、`url`、`starred_at`、`topics`。
- `UnstarRepoThread`：调用 `DELETE /user/starred/{owner}/{repo}` 取消 GitHub Star。
- `fetch_user_info(token)`：获取当前登录用户信息，目前预留。

### 数据库模块：`src/db/database.py`

数据库文件位于 `%APPDATA%\StarHelper\stars.db`。

表结构：

```sql
CREATE TABLE stars (
    id INTEGER PRIMARY KEY,
    full_name TEXT UNIQUE,
    description TEXT,
    language TEXT,
    url TEXT,
    starred_at TEXT,
    topics TEXT DEFAULT '[]'
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE star_tags (
    star_id INTEGER REFERENCES stars(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (star_id, tag_id)
);

CREATE TABLE notes (
    star_id INTEGER PRIMARY KEY REFERENCES stars(id),
    content TEXT
);
```

关键行为：

- `init_db()` 会自动补齐旧库缺失的 `topics` 和 `sort_order` 字段。
- `upsert_stars(stars)` 使用 SQLite UPSERT 更新仓库，避免 `INSERT OR REPLACE` 先删除旧行导致外键问题。
- `get_all_stars(search, language, tag_id)` 支持全文搜索、语言筛选、标签筛选和未分类视图。
- `prune_unstarred_unorganized_stars(current_star_ids)` 只在全量同步后清理已不在 GitHub Stars 中、且本地没有标签和有效备注的仓库。
- `delete_star_if_unorganized(star_id)` 用于应用内取消 Star 后的本地清理。
- `save_note(star_id, content)` 保存非空备注；如果备注为空，会删除对应备注记录。

### UI 模块：`src/ui/`

主界面由 `MainWindow` 构建，登录页和主工作台通过 `QStackedWidget` 切换。

登录后主界面是三栏布局：

```text
QSplitter(Horizontal)
├── 左侧 Sidebar
│   ├── Star Helper 标题
│   ├── 标签列表：全部 / 未分类 / 自定义标签
│   ├── 新建标签
│   └── 工具：导入、导出、主题切换、退出登录
├── 中间 Content
│   ├── 仓库标题和数量
│   ├── 同步 / 增量
│   ├── 搜索框和语言筛选
│   ├── 多选批量操作栏
│   └── 仓库列表
└── 右侧 Detail
    ├── 仓库名称链接
    ├── 仓库描述
    ├── GitHub Topics chips
    ├── 自定义标签 chips
    └── 备注编辑和保存
```

`styles.py` 提供暗色和亮色两套 QSS。`widgets.py` 提供 `FlowLayout` 和 `make_chip()`，用于 topics 和标签的自动换行展示。

---

## 导入导出格式

导出 JSON 使用 `full_name` 关联仓库，不依赖 GitHub repo ID，因此更适合跨设备或跨账号迁移整理结果。

```json
{
  "tags": [
    {
      "name": "工具",
      "stars": ["owner/repo1", "owner/repo2"]
    }
  ],
  "notes": [
    {
      "full_name": "owner/repo1",
      "content": "我的备注"
    }
  ]
}
```

导入规则：

- 标签按 `name` 去重，已存在的标签会复用。
- 仓库必须已存在于本地数据库，否则标签关联和备注会跳过。
- 建议先同步 Stars，再导入 JSON。
- 备注导入使用覆盖写入，同一仓库已有备注会被替换。

---

## 数据存储位置

所有本地数据默认存储在 `%APPDATA%\StarHelper\`。

- `stars.db`：SQLite 数据库，保存仓库、标签、标签关联、备注和 topics。
- `config.json`：保存主题配置；当系统凭据管理器不可用时，也会回退保存 access token。
- 系统凭据管理器：优先保存 GitHub access token，服务名为 `StarHelper`。

卸载或彻底重置时，可以关闭应用后删除 `%APPDATA%\StarHelper\`。

---

## 开发验证

常用检查命令：

```bash
python -m compileall -q src
```

离屏初始化主窗口：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -c "from PySide6.QtWidgets import QApplication; from src.ui.main_window import MainWindow; app=QApplication([]); w=MainWindow(); print(w.windowTitle())"
```

## 已实现功能清单

- [x] GitHub Device Flow 登录
- [x] token 优先写入系统凭据管理器，兼容旧版 `config.json`
- [x] 全量同步 starred repos
- [x] 增量同步新增 Stars
- [x] 同步 GitHub topics
- [x] 自定义标签增删改查
- [x] 自定义标签拖拽排序
- [x] 标签计数展示
- [x] 全部 / 未分类 / 指定标签视图
- [x] 仓库名称、描述、topics 搜索
- [x] 编程语言筛选
- [x] 多选仓库批量设置标签
- [x] 详情面板展示 topics 和自定义标签
- [x] topic chip 点击搜索
- [x] 详情面板点击删除当前仓库标签关联
- [x] 备注编辑和持久化
- [x] 应用内取消 GitHub Star
- [x] 全量同步后清理已取消且未整理的本地仓库
- [x] 导入 / 导出标签关联和备注 JSON
- [x] 暗色 / 亮色主题切换
- [x] 关闭应用时等待后台线程退出，降低线程未结束导致的崩溃风险
