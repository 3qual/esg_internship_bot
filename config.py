# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "token.txt"


def load_token() -> str:
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            "Файл token.txt не найден в корне проекта. "
            "Создай token.txt и помести туда Telegram Bot Token."
        )

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()

    if not token:
        raise ValueError("Файл token.txt пустой. Укажи в нём Telegram Bot Token.")

    return token


BOT_TOKEN = load_token()

RATING_SESSION_DAYS = 30
