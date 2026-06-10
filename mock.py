# mock.py
"""
Наполняет БД мок-данными для демонстрации на защите.

Что создаётся:
  • 8 пользователей с разными именами, полом, прогрессом
  • Активная рейтинговая сессия
  • 8 записей в рейтинге с разными баллами и временем
  • 1 «живой» пользователь на середине Дня 2 (имитация текущего стажёра)

Запуск:
  python mock.py            — добавить данные (не трогает существующих)
  python mock.py --reset    — сначала очистить таблицы, потом добавить
  python mock.py --show     — показать содержимое таблиц без изменений
"""

import asyncio
import argparse
import random
import time
from datetime import datetime, timedelta

import aiosqlite

DB_PATH = "esg_bot.db"

# ── Мок-данные ────────────────────────────────────────────────────────────────

MOCK_USERS = [
    # (user_id, name,       gender, age, current_day, current_step, quiz_score, time_offset_sec)
    # time_offset_sec — насколько секунд назад «начал» тест (для времени прохождения)
    (100000001, "Арина",    "F",    21,  7, 0,  96,  847),   # завершила, высокий балл
    (100000002, "Максим",   "M",    23,  7, 0, 100,  612),   # завершил, 100 баллов, быстрее всех
    (100000003, "Соня",     "F",    20,  7, 0,  78, 1203),   # завершила, средний балл
    (100000004, "Кирилл",   "M",    22,  7, 0,  85,  934),   # завершил
    (100000005, "Дарья",    "F",    19,  7, 0,  63, 1540),   # завершила, слабый балл
    (100000006, "Тимур",    "M",    24,  7, 0,  96,  901),   # завершил, 96 но медленнее Арины
    (100000007, "Полина",   "F",    21,  7, 0,  89,  776),   # завершила
    (100000008, "Никита",   "M",    22,  2, 4,   0,    0),   # «живой» — на дне 2, шаг 4
]

# Стартовый user_id чтобы не пересекаться с реальными Telegram-id
# (реальные id > 100_000_000, но мок-ы начинаются с 1xxxxxxx — практически безопасно)


# ── Цвета ─────────────────────────────────────────────────────────────────────

G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"; R = "\033[91m"; D = "\033[2m"; RESET = "\033[0m"
def g(t): return f"{G}{t}{RESET}"
def y(t): return f"{Y}{t}{RESET}"
def c(t): return f"{C}{t}{RESET}"
def r(t): return f"{R}{t}{RESET}"
def d(t): return f"{D}{t}{RESET}"


# ── БД-операции ───────────────────────────────────────────────────────────────

async def ensure_tables(db: aiosqlite.Connection):
    """Создаём таблицы если их ещё нет (повторяет init_db из database.py)."""
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


async def reset_mock_data(db: aiosqlite.Connection):
    """Удаляет только мок-записи (user_id в диапазоне 100000001–100000099)."""
    await db.execute("DELETE FROM users WHERE user_id BETWEEN 100000001 AND 100000099")
    await db.execute("DELETE FROM rating WHERE user_id BETWEEN 100000001 AND 100000099")
    # Сессию не трогаем — оставляем активную
    await db.commit()
    print(y("  ↺  Старые мок-данные удалены"))


async def get_or_create_session(db: aiosqlite.Connection) -> str:
    """Возвращает активную сессию или создаёт новую."""
    db.row_factory = aiosqlite.Row
    now = datetime.now()
    async with db.execute(
        "SELECT * FROM rating_sessions WHERE ends_at > ? ORDER BY started_at DESC LIMIT 1",
        (now.isoformat(),)
    ) as cur:
        row = await cur.fetchone()
    if row:
        return row["session_id"]
    # Создаём новую на 30 дней
    session_id = now.strftime("session_%Y%m%d_%H%M%S")
    ends_at = (now + timedelta(days=30)).isoformat()
    await db.execute(
        "INSERT INTO rating_sessions (session_id, started_at, ends_at) VALUES (?,?,?)",
        (session_id, now.isoformat(), ends_at)
    )
    await db.commit()
    print(g(f"  ✓  Создана рейтинговая сессия: {session_id}"))
    return session_id


async def insert_users(db: aiosqlite.Connection):
    now = datetime.now()
    for user_id, name, gender, age, day, step, quiz_score, time_offset in MOCK_USERS:
        # Проверяем — вдруг уже есть
        async with db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)) as cur:
            if await cur.fetchone():
                print(d(f"  –  {name} уже существует, пропускаем"))
                continue

        # registered_at — случайно от 1 до 7 дней назад
        reg_days_ago = random.randint(1, 7)
        registered_at = (now - timedelta(days=reg_days_ago)).isoformat(timespec="seconds")

        quiz_start_ts = None
        quiz_end_ts = None
        if day >= 6 and time_offset > 0:
            quiz_end_ts = time.time() - random.randint(0, 3600)   # закончил до часа назад
            quiz_start_ts = quiz_end_ts - time_offset

        await db.execute("""
            INSERT INTO users
              (user_id, name, gender, age, current_day, current_step,
               day_scores, quiz_score, quiz_start_ts, quiz_end_ts, registered_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, name, gender, age, day, step,
            "{}",
            quiz_score if day >= 6 else 0,
            quiz_start_ts, quiz_end_ts,
            registered_at
        ))
        status = f"день {day}, шаг {step}" if day < 6 else f"завершил{'а' if gender == 'F' else ''}, {quiz_score}/100"
        print(g(f"  ✓  {name:<10} ({gender}, {age} лет) — {status}"))

    await db.commit()


async def insert_rating(db: aiosqlite.Connection, session_id: str):
    for user_id, name, gender, age, day, step, quiz_score, time_offset in MOCK_USERS:
        if day < 7 or quiz_score == 0:
            continue  # «живой» пользователь — в рейтинг не добавляем

        # Проверяем — вдруг уже есть в рейтинге
        async with db.execute(
            "SELECT 1 FROM rating WHERE user_id=? AND session_id=?", (user_id, session_id)
        ) as cur:
            if await cur.fetchone():
                print(d(f"  –  {name} уже в рейтинге, пропускаем"))
                continue

        # Место: 100 → 1-е, 96 → 2-е (по времени), остальные → None
        if quiz_score == 100:
            place = 1
        elif quiz_score >= 91:
            place = 2
        else:
            place = None

        achieved_at = (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(timespec="seconds")

        await db.execute("""
            INSERT INTO rating (user_id, name, quiz_score, time_seconds, place, session_id, achieved_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user_id, name, quiz_score, float(time_offset), place, session_id, achieved_at))

        place_str = f"🥇 1-е" if place == 1 else f"🥈 2-е" if place == 2 else "—"
        print(g(f"  ✓  Рейтинг: {name:<10} {quiz_score}/100  {time_offset}с  место: {place_str}"))

    await db.commit()


async def show_tables(db: aiosqlite.Connection):
    """Выводит содержимое обеих таблиц."""
    db.row_factory = aiosqlite.Row

    print(c("\n👤 USERS:"))
    print(f"  {'ID':<12} {'Имя':<10} {'Пол'} {'Возраст'} {'День'} {'Шаг'} {'Балл'} {'Registered'}")
    print("  " + "─" * 70)
    async with db.execute("SELECT * FROM users ORDER BY user_id") as cur:
        rows = await cur.fetchall()
    if not rows:
        print(d("  (пусто)"))
    for row in rows:
        row = dict(row)
        reg = row.get("registered_at", "")[:10]
        print(f"  {row['user_id']:<12} {(row['name'] or '?'):<10} "
              f"{row['gender'] or '?':^3} "
              f"{str(row['age'] or '?'):^7} "
              f"{str(row['current_day']):^4} "
              f"{str(row['current_step']):^3} "
              f"{str(row['quiz_score']):^4} "
              f"{reg}")

    print(c("\n🏆 RATING (текущая сессия):"))
    session_id = await get_or_create_session(db)
    print(f"  {'Имя':<10} {'Балл':>5} {'Время':>8} {'Место':>6}  {'Когда'}")
    print("  " + "─" * 55)
    async with db.execute(
        "SELECT * FROM rating WHERE session_id=? ORDER BY quiz_score DESC, time_seconds ASC",
        (session_id,)
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        print(d("  (пусто)"))
    for row in rows:
        row = dict(row)
        place = row.get("place")
        place_str = "🥇" if place == 1 else "🥈" if place == 2 else " —"
        achieved = (row.get("achieved_at") or "")[:16]
        mins = int(row["time_seconds"] // 60)
        secs = int(row["time_seconds"] % 60)
        print(f"  {row['name']:<10} {row['quiz_score']:>5}/100 "
              f"  {mins}м {secs:02d}с  {place_str:>4}   {achieved}")
    print()


# ── Точка входа ───────────────────────────────────────────────────────────────

async def main(reset: bool, show_only: bool):
    print(c("\n╔══════════════════════════════════════╗"))
    print(c("║      ESG Bot — Mock Data Seeder      ║"))
    print(c("╚══════════════════════════════════════╝\n"))

    async with aiosqlite.connect(DB_PATH) as db:
        await ensure_tables(db)

        if show_only:
            await show_tables(db)
            return

        if reset:
            await reset_mock_data(db)

        print(c("📋 Добавляем пользователей:"))
        await insert_users(db)

        print(c("\n🏆 Добавляем записи в рейтинг:"))
        session_id = await get_or_create_session(db)
        await insert_rating(db, session_id)

        print(c("\n📊 Итог:"))
        await show_tables(db)

    print(c("✅ Готово! Запускай бота: python bot.py\n"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESG Bot mock data seeder")
    parser.add_argument("--reset", action="store_true",
                        help="Удалить старые мок-данные перед вставкой")
    parser.add_argument("--show",  action="store_true",
                        help="Только показать содержимое таблиц")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset, show_only=args.show))
    