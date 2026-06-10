#!/usr/bin/env python3
"""
recleaner.py — утилита сброса состояния ESG-бота для разработки.

Использование:
  python recleaner.py              # интерактивный режим
  python recleaner.py -y           # без подтверждений
  python recleaner.py --list       # dry run (только показать, не удалять)
  python recleaner.py --restore    # восстановить последний бэкап БД
  python recleaner.py -y --no-db   # только кэш и логи, БД не трогать

Флаги:
  -y / --yes       не спрашивать подтверждение
  --no-backup      не делать бэкап перед удалением БД
  --no-db          не удалять БД
  --no-cache       не чистить __pycache__ / .pyc
  --no-logs        не чистить .log файлы
  --list           dry run — только показать что будет сделано
  --restore        восстановить последнюю резервную копию БД
"""

import argparse
import os
import shutil
import sys
import glob
import subprocess
from datetime import datetime
from pathlib import Path


# ── Конфигурация ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
DB_FILE = ROOT / "esg_bot.db"
BACKUP_DIR = ROOT / "backups"
LOGS_DIRS = [ROOT / "logs"]
LOG_PATTERNS = ["*.log", "*.log.*"]
BOT_ENTRY = "bot.py"   # имя файла точки входа бота


# ── ANSI-цвета (работают в большинстве терминалов, отключаются на Windows) ───

RESET  = "\033[0m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def _no_color() -> bool:
    return sys.platform == "win32" or not sys.stdout.isatty()

def c(text: str, color: str) -> str:
    if _no_color():
        return text
    return f"{color}{text}{RESET}"


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _fmt_size(path: Path) -> str:
    """Возвращает человекочитаемый размер файла."""
    try:
        size = path.stat().st_size
        for unit in ("Б", "КБ", "МБ", "ГБ"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ГБ"
    except OSError:
        return "?"


def _collect_pycache(root: Path) -> list[Path]:
    """Рекурсивно собирает все __pycache__ папки."""
    return sorted(root.rglob("__pycache__"))


def _collect_pyc(root: Path) -> list[Path]:
    """Собирает .pyc/.pyo файлы вне __pycache__."""
    result = []
    for pattern in ("**/*.pyc", "**/*.pyo"):
        for p in root.glob(pattern):
            if "__pycache__" not in str(p):
                result.append(p)
    return sorted(result)


def _collect_logs(root: Path) -> list[Path]:
    """Собирает лог-файлы."""
    result = []
    for pattern in LOG_PATTERNS:
        result.extend(root.glob(pattern))
    for log_dir in LOGS_DIRS:
        if log_dir.exists():
            for pattern in LOG_PATTERNS:
                result.extend(log_dir.glob(pattern))
    return sorted(set(result))


def _collect_backups() -> list[Path]:
    """Возвращает список бэкапов, отсортированных по дате (новые первые)."""
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("esg_bot_backup_*.db"), reverse=True)


def _is_bot_running() -> bool:
    """Проверяет, запущен ли бот прямо сейчас."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", BOT_ENTRY],
            capture_output=True, text=True
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        # Исключаем текущий процесс
        current_pid = str(os.getpid())
        pids = [p for p in pids if p != current_pid]
        return len(pids) > 0
    except FileNotFoundError:
        # pgrep недоступен (Windows) — пробуем tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq python.exe"],
                capture_output=True, text=True
            )
            return BOT_ENTRY in result.stdout
        except Exception:
            return False


def _print_header():
    print()
    print(c("╔══════════════════════════════════════════╗", CYAN))
    print(c("║     ESG Bot — Dev Cleaner v1.0           ║", CYAN))
    print(c("╚══════════════════════════════════════════╝", CYAN))
    print()


def _print_plan(
    clean_db: bool,
    clean_cache: bool,
    clean_logs: bool,
    do_backup: bool,
    dry_run: bool,
):
    """Выводит план действий с деталями."""
    pycache_dirs = _collect_pycache(ROOT)
    pyc_files = _collect_pyc(ROOT)
    log_files = _collect_logs(ROOT)

    tag_dry = c(" [dry run]", YELLOW) if dry_run else ""

    print(c("📋 ПЛАН ОЧИСТКИ" + ("  (dry run — ничего не будет удалено)" if dry_run else ""), BOLD))
    print()

    # БД
    if clean_db:
        if DB_FILE.exists():
            size = _fmt_size(DB_FILE)
            backup_note = c("  → сначала будет сделан бэкап", DIM) if do_backup else c("  → БЕЗ БЭКАПА!", RED)
            print(f"  🗄️  {c('БД', BOLD)} {DB_FILE.name}  ({size}){backup_note}{tag_dry}")
        else:
            print(f"  🗄️  {c('БД', BOLD)} {DB_FILE.name}  {c('— файл не найден, пропускаем', DIM)}")
    else:
        print(f"  🗄️  {c('БД', DIM)}  пропускаем (--no-db)")

    # Кэш
    if clean_cache:
        total_cache = len(pycache_dirs)
        total_pyc = len(pyc_files)
        print(f"  🗑️  {c('Кэш', BOLD)}  {total_cache} папок __pycache__,  {total_pyc} отдельных .pyc файлов{tag_dry}")
        for d in pycache_dirs[:5]:
            print(f"        {c(str(d.relative_to(ROOT)), DIM)}")
        if len(pycache_dirs) > 5:
            print(f"        {c(f'... и ещё {len(pycache_dirs) - 5}', DIM)}")
    else:
        print(f"  🗑️  {c('Кэш', DIM)}  пропускаем (--no-cache)")

    # Логи
    if clean_logs:
        if log_files:
            print(f"  📝  {c('Логи', BOLD)}  {len(log_files)} файлов{tag_dry}")
            for f in log_files:
                print(f"        {c(str(f.relative_to(ROOT)), DIM)}")
        else:
            print(f"  📝  {c('Логи', DIM)}  файлов не найдено")
    else:
        print(f"  📝  {c('Логи', DIM)}  пропускаем (--no-logs)")

    print()


# ── Операции очистки ──────────────────────────────────────────────────────────

def do_backup_db() -> Path | None:
    """Создаёт бэкап БД с timestamp. Возвращает путь к бэкапу."""
    if not DB_FILE.exists():
        return None
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"esg_bot_backup_{ts}.db"
    shutil.copy2(DB_FILE, backup_path)
    return backup_path


def do_delete_db(dry_run: bool) -> bool:
    if not DB_FILE.exists():
        print(f"  {c('⚠', YELLOW)}  БД не найдена, пропускаем")
        return False
    if not dry_run:
        DB_FILE.unlink()
    print(f"  {c('✓', GREEN)}  БД удалена: {DB_FILE.name}{c(' [dry]', YELLOW) if dry_run else ''}")
    return True


def do_clean_cache(dry_run: bool) -> int:
    """Удаляет все __pycache__ и .pyc файлы. Возвращает кол-во удалённых элементов."""
    count = 0
    for d in _collect_pycache(ROOT):
        if not dry_run:
            shutil.rmtree(d, ignore_errors=True)
        count += 1
    for f in _collect_pyc(ROOT):
        if not dry_run:
            f.unlink(missing_ok=True)
        count += 1
    tag = c(" [dry]", YELLOW) if dry_run else ""
    print(f"  {c('✓', GREEN)}  Кэш очищен: удалено {count} элементов{tag}")
    return count


def do_clean_logs(dry_run: bool) -> int:
    """Удаляет лог-файлы. Возвращает кол-во удалённых."""
    files = _collect_logs(ROOT)
    for f in files:
        if not dry_run:
            f.unlink(missing_ok=True)
    tag = c(" [dry]", YELLOW) if dry_run else ""
    print(f"  {c('✓', GREEN)}  Логи: удалено {len(files)} файлов{tag}")
    return len(files)


# ── Команда --restore ─────────────────────────────────────────────────────────

def cmd_restore():
    backups = _collect_backups()
    if not backups:
        print(c("  ✗  Бэкапов не найдено в папке backups/", RED))
        sys.exit(1)

    print(c("\n📦 ДОСТУПНЫЕ БЭКАПЫ:\n", BOLD))
    for i, b in enumerate(backups[:10]):
        size = _fmt_size(b)
        marker = c(" ← последний", GREEN) if i == 0 else ""
        print(f"  [{i}]  {b.name}  ({size}){marker}")

    print()
    choice = input("Введите номер для восстановления [0 = последний]: ").strip()
    idx = int(choice) if choice.isdigit() else 0
    if idx >= len(backups):
        print(c("  ✗  Неверный номер", RED))
        sys.exit(1)

    chosen = backups[idx]

    if DB_FILE.exists():
        confirm = input(
            c(f"\n⚠️  БД {DB_FILE.name} уже существует! Перезаписать? [y/N]: ", YELLOW)
        ).strip().lower()
        if confirm != "y":
            print("Отмена.")
            sys.exit(0)

    shutil.copy2(chosen, DB_FILE)
    print(c(f"\n  ✓  Восстановлено из: {chosen.name}", GREEN))
    print(c(f"  ✓  Записано в:       {DB_FILE.name}\n", GREEN))


# ── Основная логика ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ESG Bot Dev Cleaner — сброс состояния для разработки",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("-y", "--yes",       action="store_true", help="Не спрашивать подтверждение")
    parser.add_argument("--no-backup",       action="store_true", help="Не делать бэкап БД")
    parser.add_argument("--no-db",           action="store_true", help="Не удалять БД")
    parser.add_argument("--no-cache",        action="store_true", help="Не чистить __pycache__")
    parser.add_argument("--no-logs",         action="store_true", help="Не удалять .log файлы")
    parser.add_argument("--list",            action="store_true", help="Dry run — только показать план")
    parser.add_argument("--restore",         action="store_true", help="Восстановить последний бэкап БД")

    args = parser.parse_args()

    _print_header()

    # ── Режим восстановления ──────────────────────────────────────────────────
    if args.restore:
        cmd_restore()
        return

    dry_run = args.list
    clean_db    = not args.no_db
    clean_cache = not args.no_cache
    clean_logs  = not args.no_logs
    do_backup   = not args.no_backup and clean_db

    # ── Проверка что бот не запущен ───────────────────────────────────────────
    if _is_bot_running():
        print(c(f"⚠️  ВНИМАНИЕ: похоже, бот ({BOT_ENTRY}) сейчас запущен!", RED))
        print(c("   Остановите бот перед очисткой, иначе БД может повредиться.", RED))
        print()
        if not args.yes and not dry_run:
            confirm = input("Продолжить всё равно? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Отмена.")
                sys.exit(0)

    # ── Показываем план ───────────────────────────────────────────────────────
    _print_plan(clean_db, clean_cache, clean_logs, do_backup, dry_run)

    # ── Запрашиваем подтверждение ─────────────────────────────────────────────
    if not dry_run and not args.yes:
        print(c("Продолжить? [y/N]: ", YELLOW), end="")
        confirm = input().strip().lower()
        if confirm != "y":
            print("Отмена.")
            sys.exit(0)
        print()

    if dry_run:
        print(c("ℹ️  Dry run — ни один файл не был удалён.\n", CYAN))
        return

    # ── Выполнение ────────────────────────────────────────────────────────────
    print(c("🚀 Начинаем очистку...\n", BOLD))

    backup_path = None

    if clean_db and do_backup:
        backup_path = do_backup_db()
        if backup_path:
            size = _fmt_size(backup_path)
            print(f"  {c('✓', GREEN)}  Бэкап создан: {backup_path.relative_to(ROOT)}  ({size})")

    if clean_db:
        do_delete_db(dry_run=False)

    if clean_cache:
        do_clean_cache(dry_run=False)

    if clean_logs:
        do_clean_logs(dry_run=False)

    # ── Итог ─────────────────────────────────────────────────────────────────
    print()
    print(c("═" * 44, CYAN))
    print(c("✅ Очистка завершена!", GREEN + BOLD))
    if backup_path:
        print(c(f"   Бэкап сохранён: {backup_path.name}", DIM))
    print(c(f"   Запусти бота: python bot.py", DIM))
    print(c("═" * 44, CYAN))
    print()


if __name__ == "__main__":
    main()
    