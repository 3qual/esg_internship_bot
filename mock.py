# mock.py
"""
Наполняет БД мок-данными для демонстрации на защите.

Что создаётся:
  ПОЛЬЗОВАТЕЛИ (8 человек):
    Завершили стажировку (current_day=7):
      • Максим   — М, 23 года, 100/100, 10м 12с  🥇 1-е место
      • Арина    — Ж, 21 год,   96/100, 14м 07с  🥈 2-е место
      • Тимур    — М, 24 года,  96/100, 15м 01с  🥈 2-е место
      • Полина   — Ж, 21 год,   89/100, 12м 56с
      • Кирилл   — М, 22 года,  85/100, 15м 34с

    В процессе обучения (имитация живых стажёров):
      • Соня     — Ж, 20 лет,  День 3, шаг 2  (изучает декарбонизацию)
      • Дарья    — Ж, 19 лет,  День 2, шаг 5  (изучает нефин. отчётность)
      • Никита   — М, 22 года, День 4, шаг 3  (изучает зелёные облигации)

  РЕЙТИНГ:
    Активная сессия на 30 дней.
    5 записей — только за тех, кто завершил финальный тест.
    Места: Максим (1-е), Арина и Тимур (2-е по времени), остальные без места.

Запуск:
  python mock.py            — добавить данные (не трогает существующих)
  python mock.py --reset    — сначала очистить мок-данные, потом добавить
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
# (user_id, name, gender, age, current_day, current_step, quiz_score, time_offset_sec)
# current_day=7  → стажировка полностью завершена
# current_day=2..5 → в процессе (time_offset=0, quiz_score=0)

MOCK_USERS = [
    # ── Завершили ──────────────────────────────────────────────────────────────
    (100000001, "Максим",  "M", 23,  7, 0, 100,  612),   # 🥇 100 баллов
    (100000002, "Арина",   "F", 21,  7, 0,  96,  847),   # 🥈 96, быстрее Тимура
    (100000003, "Тимур",   "M", 24,  7, 0,  96,  901),   # 🥈 96, чуть медленнее
    (100000004, "Полина",  "F", 21,  7, 0,  89,  776),
    (100000005, "Кирилл",  "M", 22,  7, 0,  85,  934),
    # ── В процессе ────────────────────────────────────────────────────────────
    (100000006, "Соня",    "F", 20,  3, 2,    0,    0),  # День 3, шаг 2
    (100000007, "Дарья",   "F", 19,  2, 5,    0,    0),  # День 2, шаг 5
    (100000008, "Никита",  "M", 22,  4, 3,    0,    0),  # День 4, шаг 3
]

# ── ANSI-цвета ────────────────────────────────────────────────────────────────

G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"; R = "\033[91m"
D = "\033[2m";  B = "\033[1m";  RESET = "\033[0m"

def g(t): return f"{G}{t}{RESET}"
def y(t): return f"{Y}{t}{RESET}"
def c(t): return f"{C}{t}{RESET}"
def d(t): return f"{D}{t}{RESET}"
def b(t): return f"{B}{t}{RESET}"


# ── БД-операции ───────────────────────────────────────────────────────────────

async def ensure_tables(db: aiosqlite.Connection):
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
    await db.execute("DELETE FROM users  WHERE user_id BETWEEN 100000001 AND 100000099")
    await db.execute("DELETE FROM rating WHERE user_id BETWEEN 100000001 AND 100000099")
    await db.commit()
    print(y("  ↺  Старые мок-данные удалены"))


async def get_or_create_session(db: aiosqlite.Connection) -> str:
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
        async with db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)) as cur:
            if await cur.fetchone():
                print(d(f"  –  {name} уже существует, пропускаем"))
                continue

        reg_days_ago = random.randint(1, 7)
        registered_at = (now - timedelta(days=reg_days_ago)).isoformat(timespec="seconds")

        quiz_start_ts = None
        quiz_end_ts = None
        if day >= 7 and time_offset > 0:
            quiz_end_ts   = time.time() - random.randint(300, 7200)
            quiz_start_ts = quiz_end_ts - time_offset

        await db.execute("""
            INSERT INTO users
              (user_id, name, gender, age, current_day, current_step,
               day_scores, quiz_score, quiz_start_ts, quiz_end_ts, registered_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id, name, gender, age, day, step,
            "{}",
            quiz_score if day >= 7 else 0,
            quiz_start_ts, quiz_end_ts,
            registered_at
        ))

        if day >= 7:
            mins = time_offset // 60
            secs = time_offset % 60
            suffix = "а" if gender == "F" else ""
            status = f"завершил{suffix} — {quiz_score}/100  ({mins}м {secs:02d}с)"
        else:
            status = f"в процессе — день {day}, шаг {step}"

        gender_label = "Ж" if gender == "F" else "М"
        print(g(f"  ✓  {name:<10} ({gender_label}, {age} лет) — {status}"))

    await db.commit()


async def insert_rating(db: aiosqlite.Connection, session_id: str):
    for user_id, name, gender, age, day, step, quiz_score, time_offset in MOCK_USERS:
        if day < 7 or quiz_score == 0:
            continue

        async with db.execute(
            "SELECT 1 FROM rating WHERE user_id=? AND session_id=?", (user_id, session_id)
        ) as cur:
            if await cur.fetchone():
                print(d(f"  –  {name} уже в рейтинге, пропускаем"))
                continue

        if quiz_score == 100:
            place = 1
        elif quiz_score >= 91:
            place = 2
        else:
            place = None

        achieved_at = (
            datetime.now() - timedelta(hours=random.randint(1, 48))
        ).isoformat(timespec="seconds")

        await db.execute("""
            INSERT INTO rating
              (user_id, name, quiz_score, time_seconds, place, session_id, achieved_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user_id, name, quiz_score, float(time_offset), place, session_id, achieved_at))

        place_str = "🥇 1-е" if place == 1 else "🥈 2-е" if place == 2 else " —"
        mins = time_offset // 60
        secs = time_offset % 60
        print(g(f"  ✓  {name:<10}  {quiz_score}/100  {mins}м {secs:02d}с  {place_str}"))

    await db.commit()


async def show_tables(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row

    # ── Users ─────────────────────────────────────────────────────────────────
    print(c(b("\n👤 USERS:")))
    header = f"  {'ID':<12} {'Имя':<10} {'П':^3} {'Лет':^5} {'День':^5} {'Шаг':^4} {'Балл':^6} {'Зарегистрирован'}"
    print(header)
    print("  " + "─" * 65)

    async with db.execute("SELECT * FROM users ORDER BY current_day DESC, quiz_score DESC") as cur:
        rows = await cur.fetchall()

    if not rows:
        print(d("  (пусто)"))
    else:
        finished = [r for r in rows if dict(r)["current_day"] >= 7]
        in_progress = [r for r in rows if dict(r)["current_day"] < 7]

        if finished:
            print(d("  — завершили —"))
        for row in finished:
            row = dict(row)
            reg = (row.get("registered_at") or "")[:10]
            print(f"  {row['user_id']:<12} {(row['name'] or '?'):<10} "
                  f"{'Ж' if row['gender']=='F' else 'М':^3} "
                  f"{str(row['age'] or '?'):^5} "
                  f"{str(row['current_day']):^5} "
                  f"{str(row['current_step']):^4} "
                  f"{str(row['quiz_score']):^6} "
                  f"{reg}")
        if in_progress:
            print(d("  — в процессе —"))
        for row in in_progress:
            row = dict(row)
            reg = (row.get("registered_at") or "")[:10]
            print(f"  {row['user_id']:<12} {(row['name'] or '?'):<10} "
                  f"{'Ж' if row['gender']=='F' else 'М':^3} "
                  f"{str(row['age'] or '?'):^5} "
                  f"{str(row['current_day']):^5} "
                  f"{str(row['current_step']):^4} "
                  f"{'—':^6} "
                  f"{reg}")

    # ── Rating ────────────────────────────────────────────────────────────────
    print(c(b("\n🏆 RATING (текущая сессия):")))
    print(f"  {'#':^4} {'Имя':<10} {'Балл':>6} {'Время':>8} {'Место':>6}  {'Когда'}")
    print("  " + "─" * 55)

    session_id = await get_or_create_session(db)
    async with db.execute(
        "SELECT * FROM rating WHERE session_id=? ORDER BY quiz_score DESC, time_seconds ASC",
        (session_id,)
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        print(d("  (пусто)"))
    else:
        for i, row in enumerate(rows, 1):
            row = dict(row)
            place = row.get("place")
            place_str = "🥇" if place == 1 else "🥈" if place == 2 else " —"
            achieved = (row.get("achieved_at") or "")[:16]
            mins = int(row["time_seconds"] // 60)
            secs = int(row["time_seconds"] % 60)
            print(f"  {i:^4} {row['name']:<10} {row['quiz_score']:>5}/100"
                  f"  {mins}м {secs:02d}с  {place_str:>4}   {achieved}")
    print()


# ── Точка входа ───────────────────────────────────────────────────────────────

async def main(reset: bool, show_only: bool):
    print(c(b("\n╔══════════════════════════════════════════╗")))
    print(c(b("║       ESG Bot — Mock Data Seeder         ║")))
    print(c(b("╚══════════════════════════════════════════╝\n")))

    async with aiosqlite.connect(DB_PATH) as db:
        await ensure_tables(db)

        if show_only:
            await show_tables(db)
            return

        if reset:
            await reset_mock_data(db)

        print(c(b("📋 Пользователи:")))
        await insert_users(db)

        print(c(b("\n🏆 Рейтинг:")))
        session_id = await get_or_create_session(db)
        await insert_rating(db, session_id)

        print(c(b("\n📊 Текущее состояние БД:")))
        await show_tables(db)

    print(c(g(b("✅ Готово! Запускай бота: python bot.py\n"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="mock.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=c(b("ESG Bot — Mock Data Seeder\n")) + "Наполняет БД демо-данными для показа на защите.",
        epilog=f"""
{b('ЧТО ЗАНОСИТСЯ В БД:')}

  {b('Таблица users')} — 8 пользователей:

    Завершили стажировку (current_day = 7):
      Максим   М  23 года   100/100  10м 12с  🥇 1-е место
      Арина    Ж  21 год     96/100  14м 07с  🥈 2-е место
      Тимур    М  24 года    96/100  15м 01с  🥈 2-е место
      Полина   Ж  21 год     89/100  12м 56с
      Кирилл   М  22 года    85/100  15м 34с

    В процессе обучения:
      Соня     Ж  20 лет   День 3, шаг 2  (декарбонизация)
      Дарья    Ж  19 лет   День 2, шаг 5  (нефин. отчётность)
      Никита   М  22 года  День 4, шаг 3  (зелёные облигации)

  {b('Таблица rating')} — 5 записей (только завершившие тест):
    Сортировка: балл DESC, время ASC
    1. Максим   100/100  10м 12с  🥇
    2. Арина     96/100  14м 07с  🥈
    3. Тимур     96/100  15м 01с  🥈
    4. Полина    89/100  12м 56с
    5. Кирилл    85/100  15м 34с

  {b('Таблица rating_sessions')} — активная сессия на 30 дней.

  Все мок-записи используют user_id в диапазоне 100000001–100000099.
  Реальные пользователи бота {b('не затрагиваются')}.

{b('ПРИМЕРЫ:')}
  python mock.py              # добавить данные (пропустит уже существующих)
  python mock.py --reset      # удалить старые мок-данные и залить заново
  python mock.py --show       # только посмотреть таблицы, ничего не менять
"""
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Удалить существующие мок-данные (user_id 100000001–100000099) перед вставкой"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Только вывести содержимое таблиц users и rating, без изменений"
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset, show_only=args.show))
    