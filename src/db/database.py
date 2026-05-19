import json
import sqlite3
from src.utils.config import DB_PATH

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    star_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stars)").fetchall()}
    if "topics" not in star_cols:
        conn.execute("ALTER TABLE stars ADD COLUMN topics TEXT DEFAULT '[]'")
    tag_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tags)").fetchall()}
    if "sort_order" not in tag_cols:
        conn.execute("ALTER TABLE tags ADD COLUMN sort_order INTEGER DEFAULT 0")
        rows = conn.execute("SELECT id FROM tags ORDER BY name").fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE tags SET sort_order = ? WHERE id = ?", (index, row["id"]))
    conn.commit()
    conn.close()


def upsert_stars(stars):
    # 用 UPSERT 而非 INSERT OR REPLACE:后者会先 DELETE 旧行,触发 star_tags 外键 NO ACTION 报错。
    conn = get_conn()
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
    """删除已经不在 GitHub Stars 中、且本地没有标签和备注的仓库。"""
    conn = get_conn()
    try:
        current_rows = [(int(star_id),) for star_id in current_star_ids]
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS current_sync_stars (id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM current_sync_stars")
        conn.executemany("INSERT OR IGNORE INTO current_sync_stars (id) VALUES (?)", current_rows)

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
            # 清掉空备注记录,避免外键阻止删除 stars。
            conn.execute("DELETE FROM notes WHERE star_id IN (SELECT id FROM stale_unorganized_stars)")
            conn.execute("DELETE FROM stars WHERE id IN (SELECT id FROM stale_unorganized_stars)")
        conn.commit()
        return deleted_count
    finally:
        conn.close()


def is_star_organized(star_id):
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
    if is_star_organized(star_id):
        return False
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE star_id = ?", (star_id,))
    conn.execute("DELETE FROM stars WHERE id = ?", (star_id,))
    conn.commit()
    conn.close()
    return True


def _row_to_star(row):
    d = dict(row)
    raw = d.get("topics") or "[]"
    try:
        d["topics"] = json.loads(raw) if isinstance(raw, str) else []
    except (json.JSONDecodeError, TypeError):
        d["topics"] = []
    return d


def get_all_stars(search="", language="", tag_id=None):
    conn = get_conn()
    query = "SELECT s.* FROM stars s"
    params = []
    if tag_id:
        query += " JOIN star_tags st ON s.id = st.star_id WHERE st.tag_id = ?"
        params.append(tag_id)
    elif tag_id == 0:  # 未分类
        query += " LEFT JOIN star_tags st ON s.id = st.star_id WHERE st.star_id IS NULL"
    else:
        query += " WHERE 1=1"
    if search:
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
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT language FROM stars WHERE language != '' ORDER BY language"
    ).fetchall()
    conn.close()
    return [r["language"] for r in rows]


def get_latest_starred_at():
    conn = get_conn()
    row = conn.execute("SELECT MAX(starred_at) AS latest FROM stars").fetchone()
    conn.close()
    return row["latest"] if row else ""


# --- Tags ---
def get_all_tags():
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.*, COUNT(st.star_id) as count FROM tags t "
        "LEFT JOIN star_tags st ON t.id = st.tag_id GROUP BY t.id ORDER BY t.sort_order, t.name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_tag(name):
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM tags").fetchone()
    next_order = row["next_order"] if row else 0
    conn.execute("INSERT OR IGNORE INTO tags (name, sort_order) VALUES (?, ?)", (name, next_order))
    conn.commit()
    conn.close()


def update_tag_order(tag_ids):
    conn = get_conn()
    conn.executemany(
        "UPDATE tags SET sort_order = ? WHERE id = ?",
        [(index, tag_id) for index, tag_id in enumerate(tag_ids)]
    )
    conn.commit()
    conn.close()


def rename_tag(tag_id, new_name):
    conn = get_conn()
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
    conn.commit()
    conn.close()


def delete_tag(tag_id):
    conn = get_conn()
    conn.execute("DELETE FROM star_tags WHERE tag_id = ?", (tag_id,))
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def set_star_tags(star_id, tag_ids):
    conn = get_conn()
    conn.execute("DELETE FROM star_tags WHERE star_id = ?", (star_id,))
    conn.executemany(
        "INSERT INTO star_tags (star_id, tag_id) VALUES (?, ?)",
        [(star_id, tid) for tid in tag_ids]
    )
    conn.commit()
    conn.close()


def get_star_tags(star_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.* FROM tags t JOIN star_tags st ON t.id = st.tag_id WHERE st.star_id = ?",
        (star_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_star_tag(star_id, tag_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM star_tags WHERE star_id = ? AND tag_id = ?",
        (star_id, tag_id)
    )
    conn.commit()
    conn.close()


# --- Notes ---
def get_note(star_id):
    conn = get_conn()
    row = conn.execute("SELECT content FROM notes WHERE star_id = ?", (star_id,)).fetchone()
    conn.close()
    return row["content"] if row else ""


def save_note(star_id, content):
    conn = get_conn()
    if content.strip():
        conn.execute(
            "INSERT OR REPLACE INTO notes (star_id, content) VALUES (?, ?)",
            (star_id, content)
        )
    else:
        conn.execute("DELETE FROM notes WHERE star_id = ?", (star_id,))
    conn.commit()
    conn.close()
