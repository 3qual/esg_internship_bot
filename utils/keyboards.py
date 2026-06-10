# utils/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def make_choice_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    """
    options: [{"text": "Вариант 1", "callback_data": "ans_0"}, ...]
    """
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
            InlineKeyboardButton(text="Мужской 👨", callback_data="gender_M"),
            InlineKeyboardButton(text="Женский 👩", callback_data="gender_F"),
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
