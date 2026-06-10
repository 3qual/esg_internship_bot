# handlers/quiz.py
"""
Финальный тест — 27 вопросов, таймер, рейтинг.
"""
import asyncio
import time
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram import Bot

from database import get_user, update_user, save_result
from utils.keyboards import make_choice_keyboard, make_continue_keyboard, make_rating_keyboard
from utils.rating_calc import format_time, place_emoji, place_label
from content.final_quiz import QUESTIONS

router = Router()

async def start_quiz(user_id: int, bot: Bot, chat_id: int):
    """Запускает финальный тест."""
    await update_user(
        user_id,
        current_day=6,      # 6 = тест начат
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
    """Отправляет текущий вопрос теста."""
    user = await get_user(user_id)
    step = user["current_step"]

    if step >= len(QUESTIONS):
        await finish_quiz(user_id, bot, chat_id)
        return

    q = QUESTIONS[step]
    num = step + 1
    total = len(QUESTIONS)

    options = [
        {"text": opt["text"], "callback_data": f"quiz_{step}_{i}"}
        for i, opt in enumerate(q["options"])
    ]

    await bot.send_message(
        chat_id,
        f"❓ <b>Вопрос {num}/{total}</b>\n\n{q['text']}",
        parse_mode="HTML",
        reply_markup=make_choice_keyboard(options)
    )

async def finish_quiz(user_id: int, bot: Bot, chat_id: int):
    """Завершает тест, считает результат, сохраняет в рейтинг."""
    user = await get_user(user_id)
    score = user["quiz_score"]
    end_ts = time.time()
    start_ts = user["quiz_start_ts"] or end_ts
    elapsed = end_ts - start_ts

    await update_user(user_id, quiz_end_ts=end_ts, current_day=7)  # 7 = всё пройдено

    # Максимум 100 баллов (27 вопросов × ~3.7 балла каждый)
    max_raw = len(QUESTIONS)
    score_100 = round((score / max_raw) * 100)

    # Сохраняем в рейтинг
    place = await save_result(user_id, user["name"], score_100, elapsed)

    # Финальное сообщение
    emoji = place_emoji(place)
    label = place_label(place)
    time_str = format_time(elapsed)

    msg = (
        f"🏁 <b>Стажировка завершена!</b>\n\n"
        f"📊 Результат: <b>{score_100}/100</b>\n"
        f"⏱ Время: <b>{time_str}</b>\n\n"
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
            "Знания об ESG у тебя есть — это главное.\n"
            "Можно попробовать улучшить результат в следующей сессии."
        )

    await bot.send_message(
        chat_id,
        msg,
        parse_mode="HTML",
        reply_markup=make_rating_keyboard()
    )

@router.callback_query(F.data.startswith("quiz_"))
async def on_quiz_answer(callback: CallbackQuery):
    await callback.message.edit_reply_markup()

    parts = callback.data.split("_")
    step_idx = int(parts[1])
    option_idx = int(parts[2])

    user = await get_user(callback.from_user.id)
    q = QUESTIONS[step_idx]
    option = q["options"][option_idx]

    # Начисляем балл
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

@router.callback_query(F.data == "show_rating")
async def on_show_rating(callback: CallbackQuery):
    from database import get_top_rating
    rows = await get_top_rating(10)
    if not rows:
        await callback.message.answer("Рейтинг пока пуст. Будь первым! 🚀")
        await callback.answer()
        return

    lines = ["🏆 <b>Топ стажёров</b>\n"]
    for i, r in enumerate(rows, 1):
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        else:
            medal = f"{i}."
        time_str = format_time(r["time_seconds"])
        lines.append(f"{medal} <b>{r['name']}</b> — {r['quiz_score']}/100 ({time_str})")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()
