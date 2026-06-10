# utils/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def next_button(day: int, step: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Далее ➡️", callback_data=f"day_{day}_{step}_next")]
    ])


def answer_buttons(options: list[str], day: int, step: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"day_{day}_{step}_ans_{i}")]
        for i, opt in enumerate(options)
    ])


def multi_buttons(options: list[str], selected: set, day: int, step: int) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(options):
        label = ("✅ " if i in selected else "☑️ ") + opt
        rows.append([InlineKeyboardButton(text=label, callback_data=f"day_{day}_{step}_toggle_{i}")])
    rows.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"day_{day}_{step}_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_button(day: int, step: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"day_{day}_{step}_confirm")]
    ])


def start_day_button(day_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Начать день {day_num} ➡️", callback_data=f"start_day_{day_num}")]
    ])


def start_quiz_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Пройти финальный тест", callback_data="start_quiz")]
    ])


# ── Обратная совместимость (используется в handlers/quiz.py и старых местах) ──

def make_choice_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=opt["text"], callback_data=opt["callback_data"])]
        for opt in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def make_continue_keyboard(label: str = "Продолжить ➡️") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="continue")]
    ])


def make_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подать заявку 📋", callback_data="apply")]
    ])


def make_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender_M"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender_F"),
        ]
    ])


def make_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Готов", callback_data="ready_yes"),
            InlineKeyboardButton(text="Не готов", callback_data="ready_no"),
        ]
    ])


def make_rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Посмотреть рейтинг", callback_data="show_rating")]
    ])
