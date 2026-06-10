# database.py
import aiosqlite
import asyncio
from datetime import datetime, timedelta
from config import RATING_SESSION_DAYS

DB_PATH = "esg_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                name          TEXT,
                gender        TEXT CHECK(gender IN ('M', 'F')),
                age           INTEGER,
                current_day   INTEGER DEFAULT 0,
                current_step  INTEGER DEFAULT 0,
                day_scores    TEXT DEFAULT '{}',
                quiz_score    INTEGER DEFAULT 0,
                quiz_start_ts REAL,
                quiz_end_ts   REAL,
                registered_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rating (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                name          TEXT,
                quiz_score    INTEGER,
                time_seconds  REAL,
                place         INTEGER,
                session_id    TEXT,
                achieved_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rating_sessions (
                session_id    TEXT PRIMARY KEY,
                started_at    TEXT,
                ends_at       TEXT
            )
        """)
        await db.commit()

# ── Пользователи ───────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()

async def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {fields} WHERE user_id = ?", values
        )
        await db.commit()

# ── Прогресс ───────────────────────────────────────────────────────────────────

async def advance_step(user_id: int):
    """Увеличить current_step на 1."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET current_step = current_step + 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

async def set_day(user_id: int, day: int):
    await update_user(user_id, current_day=day, current_step=0)

# ── Рейтинг ────────────────────────────────────────────────────────────────────

async def get_or_create_session() -> str:
    """Возвращает ID текущей активной сессии, создаёт новую если истекла."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now()
        async with db.execute(
            "SELECT * FROM rating_sessions WHERE ends_at > ? ORDER BY started_at DESC LIMIT 1",
            (now.isoformat(),)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row["session_id"]
        session_id = now.strftime("session_%Y%m%d_%H%M%S")
        ends_at = (now + timedelta(days=RATING_SESSION_DAYS)).isoformat()
        await db.execute(
            "INSERT INTO rating_sessions (session_id, started_at, ends_at) VALUES (?,?,?)",
            (session_id, now.isoformat(), ends_at)
        )
        await db.commit()
        return session_id

async def save_result(user_id: int, name: str, score: int, time_seconds: float):
    """Сохраняет результат теста и рассчитывает место."""
    session_id = await get_or_create_session()
    place = None
    if score == 100:
        place = 1
    elif 91 <= score <= 98:
        place = 2

    # Проверяем: если уже есть запись с 1-м местом — сравниваем время
    if place == 1:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM rating WHERE session_id=? AND place=1 ORDER BY time_seconds ASC LIMIT 1",
                (session_id,)
            ) as cur:
                existing = await cur.fetchone()
            if existing and existing["time_seconds"] < time_seconds:
                place = 2  # уступаем 1 место по времени

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO rating (user_id, name, quiz_score, time_seconds, place, session_id)
               VALUES (?,?,?,?,?,?)""",
            (user_id, name, score, time_seconds, place, session_id)
        )
        await db.commit()
    return place

async def get_top_rating(limit: int = 20) -> list[dict]:
    session_id = await get_or_create_session()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT name, quiz_score, time_seconds, place
               FROM rating
               WHERE session_id = ?
               ORDER BY quiz_score DESC, time_seconds ASC
               LIMIT ?""",
            (session_id, limit)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
