# handlers/days.py
"""
Универсальный обработчик всех 5 дней стажировки.
Читает контент из content/dayN.py и ведёт пользователя по шагам.
"""
import asyncio
import importlib
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message
from database import get_user, update_user, advance_step, set_day
from utils.keyboards import (
    make_choice_keyboard, make_continue_keyboard,
    make_ready_keyboard
)

router = Router()

# ── Загрузка контента дня ─────────────────────────────────────────────────────

def load_day(day_number: int):
    """Динамически загружает модуль content/dayN.py"""
    module = importlib.import_module(f"content.day{day_number}")
    return module.STEPS

# ── Форматирование текста с гендером и именем ─────────────────────────────────

def apply_gender(text: str, name: str, gender: str) -> str:
    import re
    result = text.replace("{name}", name)
    # {г:мужская форма|женская форма}
    result = re.sub(
        r"\{г:([^|]*)\|([^}]*)\}",
        lambda m: m.group(1) if gender == "M" else m.group(2),
        result
    )
    return result

# ── Главная функция: отправить текущий шаг пользователю ──────────────────────

async def send_current_step(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    if not user:
        return

    day = user["current_day"]
    step = user["current_step"]

    # Если все 5 дней пройдены — запускаем финальный тест
    if day > 5:
        from handlers.quiz import start_quiz
        await start_quiz(user_id, bot, chat_id)
        return

    # Если день ещё не начат (day=0 после регистрации — не должно быть, но на всякий)
    if day == 0:
        await set_day(user_id, 1)
        user = await get_user(user_id)
        day, step = 1, 0

    try:
        steps = load_day(day)
    except ModuleNotFoundError:
        # День ещё не написан — заглушка
        await bot.send_message(
            chat_id,
            f"📅 <b>День {day}</b> — контент в разработке. Следи за обновлениями!",
            parse_mode="HTML"
        )
        return

    if step >= len(steps):
        # Этот день полностью пройден — переходим к следующему
        await set_day(user_id, day + 1)
        await send_current_step(user_id, bot, chat_id)
        return

    current = steps[step]
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"

    stype = current["type"]

    # ── Тип: обычное сообщение ────────────────────────────────────────────────
    if stype == "message":
        text = apply_gender(current["text"], name, gender)
        await _send_message_step(bot, chat_id, text, current, step, len(steps))
        await advance_step(user_id)
        # Небольшая задержка для эффекта «живой переписки»
        await asyncio.sleep(0.8)
        await send_current_step(user_id, bot, chat_id)

    # ── Тип: выбор "Готов / Не готов" ────────────────────────────────────────
    elif stype == "ready_choice":
        await bot.send_message(
            chat_id,
            f"👔 <b>Владимир Алексеевич:</b>\n\nНадеюсь, вы {apply_gender('готов{г:|а}', name, gender)}?",
            parse_mode="HTML",
            reply_markup=make_ready_keyboard()
        )
        # Ждём callback — не advance_step

    # ── Тип: вопрос с вариантами ──────────────────────────────────────────────
    elif stype == "question":
        text = apply_gender(current.get("text", ""), name, gender)
        options = [
            {"text": opt["text"], "callback_data": f"ans_{step}_{i}"}
            for i, opt in enumerate(current["options"])
        ]
        msg = await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=make_choice_keyboard(options)
        )
        # Ждём callback

    # ── Тип: конец дня ────────────────────────────────────────────────────────
    elif stype == "day_end":
        text = apply_gender(current["text"], name, gender)
        await bot.send_message(chat_id, text, parse_mode="HTML")
        await asyncio.sleep(1)
        next_day = current.get("next_day", day + 1)
        await bot.send_message(
            chat_id,
            f"✅ <b>День {day} завершён!</b>\n\nДень {next_day} уже доступен. Продолжить когда будешь готов{apply_gender('{г:|а}', name, gender)}.",
            parse_mode="HTML",
            reply_markup=make_continue_keyboard(f"Начать день {next_day} ▶️")
        )
        await advance_step(user_id)

async def _send_message_step(bot: Bot, chat_id: int, text: str, step_data: dict, step_idx: int, total: int):
    """Отправляет сообщение. Если есть медиа — ставит заглушку."""
    media = step_data.get("media")
    media_file = step_data.get("media_file")

    if media == "voice":
        # TODO: когда файл будет готов, заменить на bot.send_voice(...)
        await bot.send_message(
            chat_id,
            f"🎙 <i>[Голосовое сообщение — {media_file or 'файл добавится позже'}]</i>\n\n{text}",
            parse_mode="HTML"
        )
    elif media == "video":
        # TODO: когда файл будет готов, заменить на bot.send_video(...)
        await bot.send_message(
            chat_id,
            f"🎥 <i>[Видео — {media_file or 'файл добавится позже'}]</i>\n\n{text}",
            parse_mode="HTML"
        )
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML")

# ── Callbacks ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ready_yes")
async def on_ready_yes(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
    user = await get_user(callback.from_user.id)
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"
    # Сразу показываем приветствие Лизы
    await advance_step(callback.from_user.id)
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()

@router.callback_query(F.data == "ready_no")
async def on_ready_no(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "👔 <b>Владимир Алексеевич:</b>\n\n"
        "Что ж, значит ваша адаптация в компании будет особенно интересной.",
        parse_mode="HTML"
    )
    await asyncio.sleep(1)
    await advance_step(callback.from_user.id)
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()

@router.callback_query(F.data == "continue")
async def on_continue(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()

@router.callback_query(F.data.startswith("ans_"))
async def on_answer(callback: CallbackQuery):
    """Обработка ответа на вопрос."""
    await callback.message.edit_reply_markup()  # убираем кнопки

    parts = callback.data.split("_")
    step_idx = int(parts[1])
    option_idx = int(parts[2])

    user = await get_user(callback.from_user.id)
    day = user["current_day"]
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"

    steps = load_day(day)
    step_data = steps[step_idx]
    option = step_data["options"][option_idx]

    # Начисляем балл за правильный ответ (опционально, пока не влияет на рейтинг)
    # В рейтинг идёт только финальный тест, но можно хранить для статистики
    import json
    day_scores = json.loads(user.get("day_scores") or "{}")
    if option["is_correct"]:
        score_key = f"d{day}_correct"
        day_scores[score_key] = day_scores.get(score_key, 0) + 1
    else:
        score_key = f"d{day}_wrong"
        day_scores[score_key] = day_scores.get(score_key, 0) + 1

    await update_user(callback.from_user.id, day_scores=json.dumps(day_scores, ensure_ascii=False))

    # Показываем реакцию
    response_text = apply_gender(option["response"], name, gender)
    await callback.message.answer(response_text, parse_mode="HTML")

    await asyncio.sleep(1)
    await advance_step(callback.from_user.id)
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()
