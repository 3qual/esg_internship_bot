# content/day4.py
"""
День 4 — контент в разработке.
Заполнить по той же структуре, что и day1.py
"""

DAY_NUMBER = 4
DAY_TITLE = "День 4"
DAY_TERMS = []  # TODO: вписать термины дня

STEPS = [
    {
        "type": "message",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nДень 4 — контент скоро появится.",
        "media": None,
    },
    {
        "type": "day_end",
        "sender": "boss",
        "text": "👔 <b>Владимир Алексеевич:</b>\n\nКоллеги, завтра продолжим.",
        "next_day": 5,
    },
]
