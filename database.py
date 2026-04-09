import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
import time
import secrets

DB = "classes.db"


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            telegram_id TEXT UNIQUE,
            discord_id  TEXT UNIQUE,
            timezone    TEXT DEFAULT 'UTC'
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS classes(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_name TEXT,
            lesson_day  TEXT,
            lesson_time TEXT,
            telegram_id TEXT,
            discord_id  TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS temp_moves(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            original_class_id INTEGER,
            lesson_name TEXT,
            temp_day    TEXT,
            temp_time   TEXT,
            telegram_id TEXT,
            discord_id  TEXT,
            week_start  TEXT,
            FOREIGN KEY (original_class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS share_codes(
            code        TEXT PRIMARY KEY,
            owner_tg    TEXT,
            owner_dc    TEXT,
            lesson_name TEXT,
            created_at  REAL,
            expires_at  REAL
        )
        """)
        
        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_temp_moves_week ON temp_moves(week_start)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_share_codes_expires ON share_codes(expires_at)")


def link_user(tg: str, dc: str):
    tg, dc = str(tg), str(dc)
    
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT telegram_id, discord_id FROM users WHERE telegram_id = ? OR discord_id = ?",
            (tg, dc)
        )
        existing = cur.fetchone()
        
        if existing:
            cur.execute(
                "UPDATE users SET telegram_id = ?, discord_id = ? WHERE telegram_id = ? OR discord_id = ?",
                (tg, dc, tg, dc)
            )
        else:
            cur.execute(
                "INSERT INTO users (telegram_id, discord_id) VALUES (?, ?)",
                (tg, dc)
            )

        # Back-fill classes
        for id_field, id_value in [('telegram_id', tg), ('discord_id', dc)]:
            other_field = 'discord_id' if id_field == 'telegram_id' else 'telegram_id'
            other_value = dc if id_field == 'telegram_id' else tg
            
            cur.execute(
                f"UPDATE classes SET {other_field}=? WHERE {id_field}=? AND ({other_field} IS NULL OR {other_field}='none' OR {other_field}='')",
                (other_value, id_value)
            )


def get_linked_ids(tg=None, dc=None):
    if not tg and not dc:
        return None
        
    with get_db() as conn:
        cur = conn.cursor()
        
        if tg:
            cur.execute("SELECT telegram_id, discord_id FROM users WHERE telegram_id=?", (str(tg),))
        else:
            cur.execute("SELECT telegram_id, discord_id FROM users WHERE discord_id=?", (str(dc),))
            
        row = cur.fetchone()
        return (row['telegram_id'], row['discord_id']) if row else None


def get_user_timezone(tg=None, dc=None):
    """Get user's timezone, default UTC if not set"""
    with get_db() as conn:
        cur = conn.cursor()
        if tg:
            cur.execute("SELECT timezone FROM users WHERE telegram_id=?", (str(tg),))
        elif dc:
            cur.execute("SELECT timezone FROM users WHERE discord_id=?", (str(dc),))
        else:
            return "UTC"
        row = cur.fetchone()
        return row['timezone'] if row else "UTC"


def set_user_timezone(tg=None, dc=None, tz="UTC"):
    with get_db() as conn:
        cur = conn.cursor()
        if tg:
            cur.execute("UPDATE users SET timezone=? WHERE telegram_id=?", (tz, str(tg)))
        elif dc:
            cur.execute("UPDATE users SET timezone=? WHERE discord_id=?", (tz, str(dc)))


def add_class(lesson: str, day: str, time: str, tg: str, dc: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO classes (lesson_name, lesson_day, lesson_time, telegram_id, discord_id) VALUES (?,?,?,?,?)",
            (lesson, day, time, str(tg), str(dc))
        )
        return cur.lastrowid


def get_user_classes(tg, dc, include_temp=True):
    with get_db() as conn:
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT id, lesson_name, lesson_day, lesson_time, 'permanent' as type
            FROM classes
            WHERE telegram_id=? OR discord_id=?
            """,
            (str(tg), str(dc))
        )
        regular = cur.fetchall()
        
        temp = []
        if include_temp:
            current_week = get_current_week_start()
            cur.execute(
                """
                SELECT id, lesson_name, temp_day, temp_time, 'temp' as type
                FROM temp_moves
                WHERE (telegram_id=? OR discord_id=?) AND week_start=?
                """,
                (str(tg), str(dc), current_week)
            )
            temp = cur.fetchall()
        
        result = []
        for row in regular:
            result.append((row['id'], row['lesson_name'], row['lesson_day'], row['lesson_time'], row['type']))
        for row in temp:
            result.append((row['id'], row['lesson_name'], row['temp_day'], row['temp_time'], row['type']))
        
        return result


def get_current_week_start():
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    return start_of_week.strftime("%Y-%m-%d")


def move_class_temp(lesson_name: str, new_day: str, new_time: str, tg: str, dc: str):
    with get_db() as conn:
        cur = conn.cursor()
        
        cur.execute(
            "SELECT id FROM classes WHERE lesson_name=? AND (telegram_id=? OR discord_id=?)",
            (lesson_name, str(tg), str(dc))
        )
        class_row = cur.fetchone()
        
        if not class_row:
            return False
        
        class_id = class_row['id']
        current_week = get_current_week_start()
        
        cur.execute(
            "DELETE FROM temp_moves WHERE original_class_id=? AND week_start=?",
            (class_id, current_week)
        )
        
        cur.execute(
            """INSERT INTO temp_moves 
               (original_class_id, lesson_name, temp_day, temp_time, telegram_id, discord_id, week_start)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (class_id, lesson_name, str(new_day), new_time, str(tg), str(dc), current_week)
        )
        
        return True


def clear_temp_moves(tg=None, dc=None):
    with get_db() as conn:
        cur = conn.cursor()
        current_week = get_current_week_start()
        
        if tg:
            cur.execute(
                "DELETE FROM temp_moves WHERE telegram_id=? AND week_start=?",
                (str(tg), current_week)
            )
        elif dc:
            cur.execute(
                "DELETE FROM temp_moves WHERE discord_id=? AND week_start=?",
                (str(dc), current_week)
            )


def get_class_by_name(lesson_name: str, tg: str = None, dc: str = None):
    if not tg and not dc:
        return None
        
    with get_db() as conn:
        cur = conn.cursor()
        
        if tg:
            cur.execute(
                "SELECT id, lesson_name, lesson_day, lesson_time FROM classes WHERE lesson_name=? AND telegram_id=?",
                (lesson_name, str(tg))
            )
        else:
            cur.execute(
                "SELECT id, lesson_name, lesson_day, lesson_time FROM classes WHERE lesson_name=? AND discord_id=?",
                (lesson_name, str(dc))
            )
        
        row = cur.fetchone()
        return (row['id'], row['lesson_name'], row['lesson_day'], row['lesson_time']) if row else None


def get_all_classes():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT lesson_name, lesson_day, lesson_time, telegram_id, discord_id FROM classes"
        )
        return cur.fetchall()


def get_all_classes_by_owner(owner_tg: str = None, owner_dc: str = None):
    """
    Fetch all classes (name, day, time) owned by a user.
    Returns list of (lesson_name, lesson_day, lesson_time)
    """
    with get_db() as conn:
        cur = conn.cursor()
        if owner_tg and owner_tg != "none":
            cur.execute(
                "SELECT lesson_name, lesson_day, lesson_time FROM classes WHERE telegram_id = ?",
                (str(owner_tg),)
            )
        elif owner_dc and owner_dc != "none":
            cur.execute(
                "SELECT lesson_name, lesson_day, lesson_time FROM classes WHERE discord_id = ?",
                (str(owner_dc),)
            )
        else:
            return []
        return cur.fetchall()


def delete_class(lesson: str, tg=None, dc=None):
    with get_db() as conn:
        cur = conn.cursor()
        
        if tg:
            cur.execute(
                "DELETE FROM classes WHERE lesson_name=? AND telegram_id=?",
                (lesson, str(tg))
            )
        elif dc:
            cur.execute(
                "DELETE FROM classes WHERE lesson_name=? AND discord_id=?",
                (lesson, str(dc))
            )


def create_share_code(owner_tg: str, owner_dc: str, lesson_name: str, expires_in_hours: int = 24):
    code = secrets.token_hex(4).upper()
    created_at = time.time()
    expires_at = created_at + (expires_in_hours * 3600)
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO share_codes (code, owner_tg, owner_dc, lesson_name, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, str(owner_tg), str(owner_dc), lesson_name, created_at, expires_at)
        )
    
    return code


def consume_share_code(code: str):
    with get_db() as conn:
        cur = conn.cursor()
        
        cur.execute(
            "SELECT owner_tg, owner_dc, lesson_name FROM share_codes WHERE code=? AND expires_at > ?",
            (code.upper(), time.time())
        )
        row = cur.fetchone()
        
        if row:
            cur.execute("DELETE FROM share_codes WHERE code=?", (code.upper(),))
            return {"owner_tg": row['owner_tg'], "owner_dc": row['owner_dc'], "lesson_name": row['lesson_name']}
    
    return None


def cleanup_expired_codes():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM share_codes WHERE expires_at <= ?", (time.time(),))
        return cur.rowcount