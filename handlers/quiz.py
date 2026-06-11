# handlers/quiz.py
"""
Финальный тест — 27 вопросов, таймер, рейтинг.
"""
import asyncio
import random
import time

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram import Bot

from database import (
    get_user, update_user, save_result,
    ensure_user_certificate, get_top_rating, get_full_rating, get_certificate_info
)
from utils.keyboards import make_choice_keyboard, make_continue_keyboard, make_rating_keyboard
from utils.rating_calc import format_time, place_emoji, place_label
from content.final_quiz import QUESTIONS

router = Router()


async def start_quiz(user_id: int, bot: Bot, chat_id: int):
    await update_user(
        user_id,
        current_day=6,
        current_step=0,
        quiz_score=0,
        quiz_start_ts=time.time(),
        quiz_end_ts=None
    )
    await bot.send_message(
        chat_id,
        "🎓 <b>Поздравляю! Ты прошёл все 5 дней стажировки!</b>\n\n"
        "Теперь — финальный тест из <b>27 вопросов</b>.\n"
        "Таймер уже идёт. Чем быстрее и точнее — тем выше в рейтинге.\n\n"
        "Удачи! 🚀",
        parse_mode="HTML",
        reply_markup=make_continue_keyboard("Начать тест ▶️")
    )


async def send_quiz_question(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    step = user["current_step"]

    if step >= len(QUESTIONS):
        await finish_quiz(user_id, bot, chat_id)
        return

    q = QUESTIONS[step]
    num = step + 1
    total = len(QUESTIONS)

    options_with_idx = list(enumerate(q["options"]))
    random.shuffle(options_with_idx)

    keyboard_options = [
        {
            "text": opt["text"],
            "callback_data": f"quiz_{step}_{orig_idx}"
        }
        for orig_idx, opt in options_with_idx
    ]

    await bot.send_message(
        chat_id,
        f"❓ <b>Вопрос {num}/{total}</b>\n\n{q['text']}",
        parse_mode="HTML",
        reply_markup=make_choice_keyboard(keyboard_options)
    )


async def finish_quiz(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    score = user["quiz_score"]
    end_ts = time.time()
    start_ts = user["quiz_start_ts"] or end_ts
    elapsed = end_ts - start_ts

    await update_user(user_id, quiz_end_ts=end_ts, current_day=7)

    max_raw = len(QUESTIONS)
    score_100 = round((score / max_raw) * 100)

    await update_user(user_id, quiz_score=score_100)

    place = await save_result(user_id, user["name"], score_100, elapsed)
    cert_number, cert_issued_at = await ensure_user_certificate(user_id)

    emoji = place_emoji(place)
    label = place_label(place)
    time_str = format_time(elapsed)

    msg = (
        f"🏁 <b>Стажировка завершена!</b>\n\n"
        f"📊 Результат: <b>{score_100}/100</b>\n"
        f"⏱ Время: <b>{time_str}</b>\n"
        f"🎓 Номер сертификата: <b>{cert_number}</b>\n"
        f"📅 Дата выдачи: <b>{cert_issued_at}</b>\n\n"
        f"{emoji} <b>{label}</b>\n\n"
    )

    if place == 1:
        msg += (
            "🥇 Поздравляю! Ты занял первое место в рейтинге стажёров!\n"
            "Владимир Алексеевич был бы доволен.\n"
            "Ну, насколько он вообще бывает доволен."
        )
    elif place == 2:
        msg += (
            "🥈 Отличный результат! Второе место — это уже далеко не все стажёры.\n"
            "ESG-повестку ты явно понял."
        )
    else:
        msg += (
            "📜 Ты прошёл стажировку и получаешь <b>сертификат участника</b>!\n"
            "Теперь его можно проверить командой:\n"
            "<code>/check-certificate "
            f"{cert_number}</code>"
        )

    await bot.send_message(
        chat_id,
        msg,
        parse_mode="HTML",
        reply_markup=make_rating_keyboard()
    )


@router.callback_query(F.data == "start_quiz")
async def on_start_quiz(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await start_quiz(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()


@router.callback_query(F.data == "continue")
async def on_quiz_continue(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if user and user.get("current_day") == 6:
        await callback.message.edit_reply_markup(reply_markup=None)
        await send_quiz_question(callback.from_user.id, callback.bot, callback.message.chat.id)
        await callback.answer()


@router.callback_query(F.data.startswith("quiz_"))
async def on_quiz_answer(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)

    parts = callback.data.split("_")
    step_idx = int(parts[1])
    option_idx = int(parts[2])

    user = await get_user(callback.from_user.id)
    q = QUESTIONS[step_idx]
    option = q["options"][option_idx]

    if option["is_correct"]:
        new_score = (user["quiz_score"] or 0) + 1
        await update_user(callback.from_user.id, quiz_score=new_score)
        await callback.message.answer("✅ Верно!")
    else:
        correct_text = next(o["text"] for o in q["options"] if o["is_correct"])
        await callback.message.answer(
            f"❌ Неверно.\n\n💡 Правильный ответ: <b>{correct_text}</b>",
            parse_mode="HTML"
        )

    await update_user(callback.from_user.id, current_step=step_idx + 1)
    await asyncio.sleep(0.5)
    await send_quiz_question(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()


def _build_rating_text(rows: list[dict], current_user_id: int | None = None) -> str:
    if not rows:
        return "Рейтинг пока пуст. Будь первым! 🚀"

    lines = ["🏆 <b>Рейтинг стажёров</b>\n"]

    for i, r in enumerate(rows, 1):
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."

        time_str = format_time(r["time_seconds"])
        line = f"{medal} <b>{r['name']}</b> — {r['quiz_score']}/100 ({time_str})"

        if current_user_id is not None and r["user_id"] == current_user_id:
            line = f"<b><u>{line}</u></b>"

        lines.append(line)

    return "\n".join(lines)


@router.callback_query(F.data == "show_rating")
async def on_show_rating(callback: CallbackQuery):
    rows = await get_full_rating()
    text = _build_rating_text(rows, callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "/rating")
async def cmd_rating(message: Message):
    rows = await get_full_rating()
    text = _build_rating_text(rows, message.from_user.id)
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.startswith("/check-certificate"))
async def cmd_check_certificate(message: Message):
    parts = (message.text or "").strip().split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Укажи номер сертификата так:\n<code>/check-certificate 12345</code>",
            parse_mode="HTML"
        )
        return

    raw_number = parts[1].strip()
    if not raw_number.isdigit() or len(raw_number) != 5:
        await message.answer(
            "Номер сертификата должен состоять из 5 цифр.\n"
            "Пример: <code>/check-certificate 12345</code>",
            parse_mode="HTML"
        )
        return

    cert_info = await get_certificate_info(int(raw_number))
    if not cert_info:
        await message.answer("Сертификат с таким номером не найден.")
        return

    await message.answer(
        "🎓 <b>Проверка сертификата</b>\n\n"
        f"Номер: <b>{cert_info['certificate_number']}</b>\n"
        f"Владелец: <b>{cert_info['name']}</b>\n"
        f"Баллы: <b>{cert_info['quiz_score']}/100</b>\n"
        f"Дата выдачи: <b>{cert_info['certificate_issued_at']}</b>",
        parse_mode="HTML"
    )