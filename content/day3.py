# content/day3.py
"""
День 3 — контент в разработке.
Заполнить по той же структуре, что и day1.py
"""

DAY_NUMBER = 3
DAY_TITLE = "День 3"
DAY_TERMS = []  # TODO: вписать термины дня

STEPS = [
    {
        "type": "message",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nДень 3 — контент скоро появится.",
        "media": None,
    },
    {
        "type": "day_end",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nКоллеги, завтра продолжим.",
        "next_day": 4,
    },
]
