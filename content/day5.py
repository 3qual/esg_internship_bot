# content/day5.py
"""
День 5 — контент в разработке.
Заполнить по той же структуре, что и day1.py
"""

DAY_NUMBER = 5
DAY_TITLE = "День 5"
DAY_TERMS = []  # TODO: вписать термины дня

STEPS = [
    {
        "type": "message",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nДень 5 — контент скоро появится.",
        "media": None,
    },
    {
        "type": "day_end",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nКоллеги, завтра продолжим.",
        "next_day": 6,
    },
]
