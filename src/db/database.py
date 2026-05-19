"""SQLite 数据访问层:封装 stars / tags / notes 表的全部 CRUD 操作。

设计要点:
- stars 表的主键直接采用 GitHub 仓库 id,便于按 id UPSERT 实现增量同步。
- topics 以 JSON 字符串形式存放在单列中,避免引入额外多对多表。
- tags 与 stars 之间通过 star_tags 关联表实现多对多关系。
"""

import json
import sqlite3
from src.utils.config import DB_PATH

# 表结构定义:使用 IF NOT EXISTS 保证脚本在已建库的环境下幂等执行
SCHEMA = """
CREATE TABLE IF NOT EXISTS stars (
    id INTEGER PRIMARY KEY,
    full_name TEXT UNIQUE,
    description TEXT,
    language TEXT,
    url TEXT,
    starred_at TEXT,
    topics TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    sort_order INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS star_tags (
    star_id INTEGER REFERENCES stars(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (star_id, tag_id)
);
CREATE TABLE IF NOT EXISTS notes (
    star_id INTEGER PRIMARY KEY REFERENCES stars(id),
    content TEXT
);
"""


def get_conn():
    """统一获取数据库连接;开启 Row 工厂方便按列名访问,以及强制启用外键约束。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite 默认关闭外键约束,需在每个连接上显式打开
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库并执行轻量级 schema 迁移,兼容旧版本的本地库文件。"""
    conn = get_conn()
    conn.executescript(SCHEMA)
    # 旧版本数据库缺少 topics 列,这里通过 PRAGMA 探测后补齐
    star_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stars)").fetchall()}
    if "topics" not in star_cols:
        conn.execute("ALTER TABLE stars ADD COLUMN topics TEXT DEFAULT '[]'")
    # 旧版本 tags 表缺少 sort_order,补列后按名称初始化一份默认顺序
    tag_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tags)").fetchall()}
    if "sort_order" not in tag_cols:
        conn.execute("ALTER TABLE tags ADD COLUMN sort_order INTEGER DEFAULT 0")
        rows = conn.execute("SELECT id FROM tags ORDER BY name").fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE tags SET sort_order = ? WHERE id = ?", (index, row["id"]))
    conn.commit()
    conn.close()


def upsert_stars(stars):
    """批量写入或更新 stars 行。

    使用 UPSERT 而非 INSERT OR REPLACE:后者会先 DELETE 旧行,触发 star_tags 外键
    NO ACTION 报错,导致用户先前打的标签丢失。
    """
    conn = get_conn()
    # topics 是列表,这里序列化成 JSON 字符串以适配单列存储
    rows = [
        {**s, "topics": json.dumps(s.get("topics") or [])}
        for s in stars
    ]
    conn.executemany(
        "INSERT INTO stars (id, full_name, description, language, url, starred_at, topics) "
        "VALUES (:id, :full_name, :description, :language, :url, :starred_at, :topics) "
        "ON CONFLICT(id) DO UPDATE SET "
        "full_name = excluded.full_name, "
        "description = excluded.description, "
        "language = excluded.language, "
        "url = excluded.url, "
        "starred_at = excluded.starred_at, "
        "topics = excluded.topics",
        rows
    )
    conn.commit()
    conn.close()


def prune_unstarred_unorganized_stars(current_star_ids):
    """删除已经不在 GitHub Stars 中、且本地没有标签和备注的仓库。

    保留打过标签或写过备注的"已整理"仓库,避免用户的本地整理成果因取消 star 而丢失。
    通过两张临时表分两步定位待删行,再级联清理 notes,绕开外键约束。
    """
    conn = get_conn()
    try:
        # 临时表存放本次同步时仍在远端的 star id,便于在 SQL 内做集合差
        current_rows = [(int(star_id),) for star_id in current_star_ids]
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS current_sync_stars (id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM current_sync_stars")
        conn.executemany("INSERT OR IGNORE INTO current_sync_stars (id) VALUES (?)", current_rows)

        # 计算待删除集合:不在当前同步列表 && 无标签 && 无非空备注
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS stale_unorganized_stars (id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM stale_unorganized_stars")
        conn.execute(
            """
            INSERT INTO stale_unorganized_stars (id)
            SELECT s.id
            FROM stars s
            LEFT JOIN current_sync_stars css ON css.id = s.id
            WHERE css.id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM star_tags st WHERE st.star_id = s.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM notes n
                  WHERE n.star_id = s.id
                    AND TRIM(COALESCE(n.content, '')) != ''
              )
            """
        )
        row = conn.execute("SELECT COUNT(*) AS count FROM stale_unorganized_stars").fetchone()
        deleted_count = row["count"] if row else 0
        if deleted_count:
            # 先清掉空备注记录,避免外键阻止删除 stars。
            conn.execute("DELETE FROM notes WHERE star_id IN (SELECT id FROM stale_unorganized_stars)")
            conn.execute("DELETE FROM stars WHERE id IN (SELECT id FROM stale_unorganized_stars)")
        conn.commit()
        return deleted_count
    finally:
        # 即便中途异常也要保证连接释放,临时表会随连接关闭自动销毁
        conn.close()


def is_star_organized(star_id):
    """判断仓库是否有标签或非空备注,用于决定取消 star 后是否保留本地记录。"""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
            EXISTS(SELECT 1 FROM star_tags WHERE star_id = ?) AS has_tags,
            EXISTS(
                SELECT 1 FROM notes
                WHERE star_id = ?
                  AND TRIM(COALESCE(content, '')) != ''
            ) AS has_note
        """,
        (star_id, star_id),
    ).fetchone()
    conn.close()
    return bool(row["has_tags"] or row["has_note"]) if row else False


def delete_star_if_unorganized(star_id):
    """若仓库未被整理则删除并返回 True;否则保留并返回 False。"""
    if is_star_organized(star_id):
        return False
    conn = get_conn()
    # 同步清理 notes,避免外键阻止 stars 删除
    conn.execute("DELETE FROM notes WHERE star_id = ?", (star_id,))
    conn.execute("DELETE FROM stars WHERE id = ?", (star_id,))
    conn.commit()
    conn.close()
    return True


def _row_to_star(row):
    """将 sqlite Row 转成普通 dict,并把 topics 从 JSON 字符串反序列化回列表。"""
    d = dict(row)
    raw = d.get("topics") or "[]"
    try:
        d["topics"] = json.loads(raw) if isinstance(raw, str) else []
    except (json.JSONDecodeError, TypeError):
        # 防御性兜底:历史数据可能含非法 JSON,统一回退为空列表而非抛错
        d["topics"] = []
    return d


def get_all_stars(search="", language="", tag_id=None):
    """按可选过滤条件返回 star 列表,统一按收藏时间倒序。

    tag_id 语义:
      - 非零整数:仅返回带该标签的仓库
      - 0:仅返回未打任何标签的仓库("未分类")
      - None:不按标签过滤
    """
    conn = get_conn()
    query = "SELECT s.* FROM stars s"
    params = []
    if tag_id:
        query += " JOIN star_tags st ON s.id = st.star_id WHERE st.tag_id = ?"
        params.append(tag_id)
    elif tag_id == 0:  # 未分类
        # 左连后筛 NULL,定位没有任何标签关联的仓库
        query += " LEFT JOIN star_tags st ON s.id = st.star_id WHERE st.star_id IS NULL"
    else:
        # 占位 1=1,后续条件统一用 AND 拼接
        query += " WHERE 1=1"
    if search:
        # 在仓库名、描述、topics(JSON 字符串)中做模糊匹配
        query += " AND (s.full_name LIKE ? OR s.description LIKE ? OR s.topics LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if language:
        query += " AND s.language = ?"
        params.append(language)
    query += " ORDER BY s.starred_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_star(r) for r in rows]


def get_languages():
    """返回当前已收藏仓库涉及的全部语言,用于侧边栏过滤下拉。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT language FROM stars WHERE language != '' ORDER BY language"
    ).fetchall()
    conn.close()
    return [r["language"] for r in rows]


def get_latest_starred_at():
    """获取最新 star 的时间戳,用于增量同步时确定截止点。"""
    conn = get_conn()
    row = conn.execute("SELECT MAX(starred_at) AS latest FROM stars").fetchone()
    conn.close()
    return row["latest"] if row else ""


# --- Tags ---
def get_all_tags():
    """返回全部标签及其下属仓库数,按用户自定义顺序排序。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.*, COUNT(st.star_id) as count FROM tags t "
        "LEFT JOIN star_tags st ON t.id = st.tag_id GROUP BY t.id ORDER BY t.sort_order, t.name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_tag(name):
    """创建新标签;若同名标签已存在则静默忽略以保持幂等。"""
    conn = get_conn()
    # 新标签追加到列表末尾(最大 sort_order + 1)
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM tags").fetchone()
    next_order = row["next_order"] if row else 0
    conn.execute("INSERT OR IGNORE INTO tags (name, sort_order) VALUES (?, ?)", (name, next_order))
    conn.commit()
    conn.close()


def update_tag_order(tag_ids):
    """按传入的 id 顺序整体更新标签的 sort_order,支持拖拽排序。"""
    conn = get_conn()
    conn.executemany(
        "UPDATE tags SET sort_order = ? WHERE id = ?",
        [(index, tag_id) for index, tag_id in enumerate(tag_ids)]
    )
    conn.commit()
    conn.close()


def rename_tag(tag_id, new_name):
    """重命名标签;标签的 name 上有 UNIQUE 约束,重名会抛 IntegrityError 让调用方处理。"""
    conn = get_conn()
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
    conn.commit()
    conn.close()


def delete_tag(tag_id):
    """删除标签:先清空 star_tags 中的关联,再删除 tags 行本身。"""
    conn = get_conn()
    # 必须先删关联,否则会被外键约束阻止
    conn.execute("DELETE FROM star_tags WHERE tag_id = ?", (tag_id,))
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def set_star_tags(star_id, tag_ids):
    """整体替换某仓库的标签集合;先全删旧关联再写入新关联,语义最直接。"""
    conn = get_conn()
    conn.execute("DELETE FROM star_tags WHERE star_id = ?", (star_id,))
    conn.executemany(
        "INSERT INTO star_tags (star_id, tag_id) VALUES (?, ?)",
        [(star_id, tid) for tid in tag_ids]
    )
    conn.commit()
    conn.close()


def get_star_tags(star_id):
    """返回某仓库当前关联的全部标签详情。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.* FROM tags t JOIN star_tags st ON t.id = st.tag_id WHERE st.star_id = ?",
        (star_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_star_tag(star_id, tag_id):
    """从某仓库上摘掉单个标签,用于卡片上点击 tag chip 的 X 按钮。"""
    conn = get_conn()
    conn.execute(
        "DELETE FROM star_tags WHERE star_id = ? AND tag_id = ?",
        (star_id, tag_id)
    )
    conn.commit()
    conn.close()


# --- Notes ---
def get_note(star_id):
    """读取仓库备注;不存在时返回空字符串而非 None,方便直接绑定到文本框。"""
    conn = get_conn()
    row = conn.execute("SELECT content FROM notes WHERE star_id = ?", (star_id,)).fetchone()
    conn.close()
    return row["content"] if row else ""


def save_note(star_id, content):
    """保存或清除仓库备注:空白内容视为清除,避免在表中留下无意义记录。"""
    conn = get_conn()
    if content.strip():
        conn.execute(
            "INSERT OR REPLACE INTO notes (star_id, content) VALUES (?, ?)",
            (star_id, content)
        )
    else:
        # 用户清空备注时主动删除行,保持"备注存在 == 内容非空"的不变式
        conn.execute("DELETE FROM notes WHERE star_id = ?", (star_id,))
    conn.commit()
    conn.close()
