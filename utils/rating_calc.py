# utils/rating_calc.py

def calc_place(score: int, time_seconds: float, existing_first: dict | None) -> int | None:
    """
    Рассчитывает место пользователя.
    existing_first: словарь {'time_seconds': float} для текущего 1-го места, или None.
    Возвращает 1, 2, или None (сертификат участника).
    """
    if score == 100:
        if existing_first is None:
            return 1
        if time_seconds < existing_first["time_seconds"]:
            return 1  # быстрее — забираем первое место
        else:
            return 2  # медленнее — второе
    elif 91 <= score <= 98:
        return 2
    return None

def format_time(seconds: float) -> str:
    """Форматирует секунды в '5 мин 12 сек'."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m} мин {s} сек"
    return f"{s} сек"

def place_emoji(place: int | None) -> str:
    if place == 1:
        return "🥇"
    if place == 2:
        return "🥈"
    return "📜"

def place_label(place: int | None) -> str:
    if place == 1:
        return "1 место"
    if place == 2:
        return "2 место"
    return "Сертификат стажёра"
