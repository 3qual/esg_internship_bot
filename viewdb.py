# viewdb.py
"""
Просмотр текущего состояния БД ESG-бота.

Запуск:
  python3 viewdb.py           — все таблицы
  python3 viewdb.py --users   — только пользователи
  python3 viewdb.py --rating  — только рейтинг
  python3 viewdb.py --certs   — только сертификаты
  python3 viewdb.py --stats   — сводная статистика
"""

import asyncio
import argparse
from datetime import datetime

import aiosqlite

DB_PATH = "esg_bot.db"

# ── ANSI-цвета ────────────────────────────────────────────────────────────────

G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"
R = "\033[91m"; D = "\033[2m";  B = "\033[1m"; RESET = "\033[0m"

def g(t): return f"{G}{t}{RESET}"
def y(t): return f"{Y}{t}{RESET}"
def c(t): return f"{C}{t}{RESET}"
def r(t): return f"{R}{t}{RESET}"
def d(t): return f"{D}{t}{RESET}"
def b(t): return f"{B}{t}{RESET}"

def divider(width=72): return "  " + "─" * width


# ── Прогресс-бар ──────────────────────────────────────────────────────────────

def progress_bar(current: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = round(current / total * width)
    return "█" * filled + "░" * (width - filled)


# ── Форматирование времени ─────────────────────────────────────────────────────

def fmt_time(seconds: float) -> str:
    if not seconds:
        return "—"
    m, s = divmod(int(seconds), 60)
    return f"{m}м {s:02d}с"


# ── Таблица пользователей ─────────────────────────────────────────────────────

async def show_users(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM users ORDER BY current_day DESC, quiz_score DESC") as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    total = len(rows)
    finished    = [r for r in rows if r["current_day"] >= 7]
    in_progress = [r for r in rows if 0 < r["current_day"] < 7]
    not_started = [r for r in rows if r["current_day"] == 0]

    print(c(b("\n┌─ 👤 ПОЛЬЗОВАТЕЛИ " + "─" * 53 + "┐")))
    print(f"  Всего: {b(str(total))}   "
          f"{g('✓ завершили: ' + str(len(finished)))}   "
          f"{y('⏳ в процессе: ' + str(len(in_progress)))}   "
          f"{d('○ не начали: ' + str(len(not_started)))}")
    print(divider())

    DAY_LABELS = {
        0: d("не начал"),
        1: y("День 1"),
        2: y("День 2"),
        3: y("День 3"),
        4: y("День 4"),
        5: y("День 5"),
        6: y("Финал. тест"),
        7: g("Завершён ✓"),
    }

    # ── Завершили ─────────────────────────────────────────────────────────────
    if finished:
        print(b(d("  — ЗАВЕРШИЛИ СТАЖИРОВКУ —")))
        print(f"  {'ID':<13} {'Имя':<12} {'П':^3} {'Лет':^5} "
              f"{'Балл':^8} {'Прогресс':^12} {'Сертификат':^12} {'Дата'}")
        print(divider())
        for row in finished:
            bar = progress_bar(row["quiz_score"], 100, 10)
            score_colored = g(f"{row['quiz_score']}/100") if row["quiz_score"] >= 80 \
                else y(f"{row['quiz_score']}/100") if row["quiz_score"] >= 60 \
                else r(f"{row['quiz_score']}/100")
            cert = str(row.get("certificate_number") or "—")
            reg  = (row.get("registered_at") or "")[:10]
            gender = "Ж" if row["gender"] == "F" else "М" if row["gender"] == "M" else "?"
            print(f"  {str(row['user_id']):<13} "
                  f"{(row['name'] or '?'):<12} "
                  f"{gender:^3} "
                  f"{str(row['age'] or '?'):^5} "
                  f"{score_colored:^8} "
                  f"[{bar}] "
                  f"{cert:^12} "
                  f"{reg}")

    # ── В процессе ────────────────────────────────────────────────────────────
    if in_progress:
        print()
        print(b(d("  — В ПРОЦЕССЕ ОБУЧЕНИЯ —")))
        print(f"  {'ID':<13} {'Имя':<12} {'П':^3} {'Лет':^5} "
              f"{'Статус':<16} {'Прогресс':^12} {'Зарегистрирован'}")
        print(divider())
        for row in in_progress:
            day   = row["current_day"]
            step  = row["current_step"]
            label = DAY_LABELS.get(day, y(f"День {day}"))
            bar   = progress_bar(day, 5, 10)
            reg   = (row.get("registered_at") or "")[:10]
            gender = "Ж" if row["gender"] == "F" else "М" if row["gender"] == "M" else "?"
            print(f"  {str(row['user_id']):<13} "
                  f"{(row['name'] or '?'):<12} "
                  f"{gender:^3} "
                  f"{str(row['age'] or '?'):^5} "
                  f"{label:<16} шаг {step:<3} "
                  f"[{bar}] "
                  f"{reg}")

    # ── Не начали ─────────────────────────────────────────────────────────────
    if not_started:
        print()
        print(b(d("  — НЕ НАЧАЛИ —")))
        print(f"  {'ID':<13} {'Имя':<12} {'Зарегистрирован'}")
        print(divider())
        for row in not_started:
            reg = (row.get("registered_at") or "")[:16]
            print(f"  {str(row['user_id']):<13} "
                  f"{(row['name'] or d('—')):<12} "
                  f"{reg}")

    if not rows:
        print(d("  (таблица пуста)"))

    print(c(b("└" + "─" * 71 + "┘")))


# ── Таблица рейтинга ──────────────────────────────────────────────────────────

async def show_rating(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row

    # Текущая сессия
    now = datetime.now()
    async with db.execute(
        "SELECT * FROM rating_sessions WHERE ends_at > ? ORDER BY started_at DESC LIMIT 1",
        (now.isoformat(),)
    ) as cur:
        session = await cur.fetchone()

    session_id = dict(session)["session_id"] if session else None

    async with db.execute(
        """SELECT * FROM rating
           WHERE session_id = ?
           ORDER BY quiz_score DESC, time_seconds ASC""",
        (session_id,)
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    # Все сессии для справки
    async with db.execute(
        "SELECT * FROM rating_sessions ORDER BY started_at DESC"
    ) as cur:
        sessions = [dict(r) for r in await cur.fetchall()]

    print(c(b("\n┌─ 🏆 РЕЙТИНГ " + "─" * 58 + "┐")))

    if sessions:
        print(f"  Сессий всего: {b(str(len(sessions)))}")
        for s in sessions:
            active = g(" ← активная") if s["session_id"] == session_id else ""
            ends   = (s.get("ends_at") or "")[:10]
            print(f"  {d(s['session_id'])}  до {ends}{active}")
    else:
        print(d("  Сессий нет"))

    print(divider())

    if not rows:
        print(d("  (рейтинг пуст)"))
    else:
        print(f"  {'#':^4} {'Имя':<12} {'Балл':>8} {'Время':>8} "
              f"{'Место':^8} {'Когда'}")
        print(divider())
        for i, row in enumerate(rows, 1):
            place = row.get("place")
            if place == 1:
                medal = g("🥇 1-е")
                name  = g(b(row["name"]))
            elif place == 2:
                medal = y("🥈 2-е")
                name  = y(row["name"])
            elif i == 3:
                medal = c("🥉 3-е")
                name  = c(row["name"])
            else:
                medal = d(f"   {i}-е")
                name  = row["name"]

            score_val = row["quiz_score"]
            score_str = g(f"{score_val}/100") if score_val >= 80 \
                else y(f"{score_val}/100") if score_val >= 60 \
                else r(f"{score_val}/100")

            achieved = (row.get("achieved_at") or "")[:16]
            time_str = fmt_time(row["time_seconds"])

            print(f"  {str(i):^4} {name:<12} "
                  f"{score_str:>8} "
                  f"{time_str:>8} "
                  f"{medal:<8} "
                  f"{achieved}")

    print(c(b("└" + "─" * 71 + "┘")))


# ── Таблица сертификатов ──────────────────────────────────────────────────────

async def show_certificates(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row
    async with db.execute("""
        SELECT user_id, name, quiz_score, certificate_number, certificate_issued_at
        FROM users
        WHERE certificate_number IS NOT NULL
        ORDER BY certificate_issued_at DESC
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    print(c(b("\n┌─ 🎓 СЕРТИФИКАТЫ " + "─" * 54 + "┐")))
    print(f"  Выдано сертификатов: {b(str(len(rows)))}")
    print(divider())

    if not rows:
        print(d("  (сертификатов нет)"))
    else:
        print(f"  {'Номер':^8} {'Имя':<14} {'Балл':>8} {'Дата выдачи'}")
        print(divider())
        for row in rows:
            score_val = row["quiz_score"]
            score_str = g(f"{score_val}/100") if score_val >= 80 \
                else y(f"{score_val}/100") if score_val >= 60 \
                else r(f"{score_val}/100")
            issued = (row.get("certificate_issued_at") or "")[:16]
            print(f"  {b(str(row['certificate_number'])):^8}  "
                  f"{(row['name'] or '?'):<14} "
                  f"{score_str:>8}   "
                  f"{issued}")

    print(c(b("└" + "─" * 71 + "┘")))


# ── Сводная статистика ────────────────────────────────────────────────────────

async def show_stats(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row

    async with db.execute("SELECT COUNT(*) as cnt FROM users") as cur:
        total_users = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE current_day >= 7") as cur:
        finished = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE current_day BETWEEN 1 AND 6") as cur:
        in_progress = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE current_day = 0") as cur:
        not_started = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE certificate_number IS NOT NULL") as cur:
        certs = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT AVG(quiz_score) as avg, MAX(quiz_score) as mx, MIN(quiz_score) as mn FROM users WHERE current_day >= 7") as cur:
        score_row = dict(await cur.fetchone())

    async with db.execute("SELECT AVG(time_seconds) as avg FROM rating") as cur:
        time_row = dict(await cur.fetchone())

    async with db.execute(
        "SELECT name, quiz_score FROM users WHERE current_day >= 7 ORDER BY quiz_score DESC LIMIT 1"
    ) as cur:
        top = await cur.fetchone()

    conv_rate = round(finished / total_users * 100) if total_users else 0
    bar_fin  = progress_bar(finished, total_users, 20)
    bar_prog = progress_bar(in_progress, total_users, 20)

    print(c(b("\n┌─ 📊 СТАТИСТИКА " + "─" * 55 + "┐")))
    print()
    print(f"  {b('Пользователи')}")
    print(f"  Всего зарегистрировано:    {b(str(total_users))}")
    print(f"  Завершили стажировку:      {g(str(finished))}  [{g(bar_fin)}] {g(str(conv_rate) + '%')}")
    print(f"  В процессе обучения:       {y(str(in_progress))}  [{y(bar_prog)}]")
    print(f"  Не начали:                 {d(str(not_started))}")
    print(f"  Сертификатов выдано:       {c(b(str(certs)))}")
    print()
    print(f"  {b('Финальный тест')}")
    if score_row["avg"] is not None:
        avg_score = round(score_row["avg"])
        max_score = score_row["mx"]
        min_score = score_row["mn"]
        avg_bar   = progress_bar(avg_score, 100, 20)
        print(f"  Средний балл:              {b(str(avg_score))}/100  [{y(avg_bar)}]")
        print(f"  Максимальный балл:         {g(str(max_score) + '/100')}")
        print(f"  Минимальный балл:          {r(str(min_score) + '/100')}")
    else:
        print(f"  {d('Данных ещё нет')}")
    if time_row["avg"]:
        print(f"  Среднее время прохождения: {b(fmt_time(time_row['avg']))}")
    if top:
        top = dict(top)
        print(f"  Лидер:                     {g(b(top['name']))} — {g(str(top['quiz_score']) + '/100')}")
    print()
    print(c(b("└" + "─" * 71 + "┘")))


# ── Точка входа ───────────────────────────────────────────────────────────────

async def main(show_only_users: bool, show_only_rating: bool,
               show_only_certs: bool, show_only_stats: bool):

    print(c(b("\n╔══════════════════════════════════════════════════════════════╗")))
    print(c(b("║              ESG Bot — Database Viewer                      ║")))
    print(c(b("╚══════════════════════════════════════════════════════════════╝")))

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            show_all = not any([show_only_users, show_only_rating,
                                show_only_certs, show_only_stats])

            if show_all or show_only_stats:
                await show_stats(db)
            if show_all or show_only_users:
                await show_users(db)
            if show_all or show_only_rating:
                await show_rating(db)
            if show_all or show_only_certs:
                await show_certificates(db)

    except aiosqlite.OperationalError:
        print(r("\n  ✗  Файл esg_bot.db не найден или БД ещё не инициализирована."))
        print(d("     Запусти бота хотя бы один раз: python3 bot.py\n"))
        return

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="viewdb.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="ESG Bot — просмотр текущего состояния базы данных.",
        epilog="""
Примеры:
  python3 viewdb.py            — все таблицы + статистика
  python3 viewdb.py --stats    — только сводная статистика
  python3 viewdb.py --users    — только пользователи
  python3 viewdb.py --rating   — только рейтинг
  python3 viewdb.py --certs    — только сертификаты
"""
    )
    parser.add_argument("--users",  action="store_true", help="Только таблица пользователей")
    parser.add_argument("--rating", action="store_true", help="Только рейтинг")
    parser.add_argument("--certs",  action="store_true", help="Только сертификаты")
    parser.add_argument("--stats",  action="store_true", help="Только сводная статистика")
    args = parser.parse_args()

    asyncio.run(main(args.users, args.rating, args.certs, args.stats))
