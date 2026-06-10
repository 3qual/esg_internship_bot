# handlers/days.py
"""
Универсальный обработчик всех 5 дней стажировки.
Читает контент из content/dayN.py и ведёт пользователя по шагам.
Поддерживаемые типы шагов:
  message, message_pause, question_single, question_multi,
  question_single_forced, system_message, day_end
"""
import asyncio
import importlib
from typing import Any

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message

from database import get_user, update_user, advance_step, set_day
from utils.keyboards import (
    next_button, answer_buttons, multi_buttons, start_day_button,
    start_quiz_button,
    # обратная совместимость
    make_choice_keyboard, make_continue_keyboard, make_ready_keyboard,
)

router = Router()

# ── Хранилище состояний question_multi (user_id → set of selected indices) ────
_multi_state: dict[int, set] = {}


# ── Загрузка контента дня ─────────────────────────────────────────────────────

def load_day(day_number: int) -> list[dict]:
    module = importlib.import_module(f"content.day{day_number}")
    return module.STEPS


# ── Форматирование текста с гендером и именем ─────────────────────────────────

def apply_gender(text: str, name: str, gender: str) -> str:
    import re
    result = text.replace("{name}", name)
    result = re.sub(
        r"\{г:([^|]*)\|([^}]*)\}",
        lambda m: m.group(1) if gender == "M" else m.group(2),
        result
    )
    return result


# ── Префикс отправителя ───────────────────────────────────────────────────────

def _prefix(sender: str) -> str:
    prefixes = {
        "hr":          "👔 <b>Анатолий (HR):</b>\n\n",
        "boss":        "👔 <b>Владимир Алексеевич:</b>\n\n",
        "liza":        "💬 <b>Лиза:</b>\n\n",
        "liza_hidden": "🔒 <i>Скрыто от Владимира:</i>\n💬 <b>Лиза:</b>\n\n",
        "system":      "",
    }
    return prefixes.get(sender, "")


def _format(step: dict, name: str, gender: str) -> str:
    sender = step.get("sender", "system")
    raw = step.get("text", "")
    text = apply_gender(raw, name, gender)
    if sender == "system":
        return f"<i>{text}</i>"
    return _prefix(sender) + text


# ── Отправка шага ─────────────────────────────────────────────────────────────

async def send_current_step(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    if not user:
        return

    day = user["current_day"]
    step = user["current_step"]

    if day > 5:
        from handlers.quiz import start_quiz
        await start_quiz(user_id, bot, chat_id)
        return

    if day == 0:
        await set_day(user_id, 1)
        user = await get_user(user_id)
        day, step = 1, 0

    try:
        steps = load_day(day)
    except ModuleNotFoundError:
        await bot.send_message(
            chat_id,
            f"📅 <b>День {day}</b> — контент в разработке. Следи за обновлениями!",
            parse_mode="HTML"
        )
        return

    if step >= len(steps):
        await set_day(user_id, day + 1)
        await send_current_step(user_id, bot, chat_id)
        return

    current = steps[step]
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"
    stype = current["type"]

    # ── message ───────────────────────────────────────────────────────────────
    if stype == "message":
        text = _format(current, name, gender)
        await _send_with_media(bot, chat_id, text, current)
        await advance_step(user_id)
        await asyncio.sleep(1)
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(0.5)
        await send_current_step(user_id, bot, chat_id)

    # ── message_pause ─────────────────────────────────────────────────────────
    elif stype == "message_pause":
        text = _format(current, name, gender)
        await _send_with_media(bot, chat_id, text, current,
                               reply_markup=next_button(day, step))
        # Ждём callback next

    # ── system_message ────────────────────────────────────────────────────────
    elif stype == "system_message":
        text = _format(current, name, gender)
        await bot.send_message(chat_id, text, parse_mode="HTML")
        await advance_step(user_id)
        await asyncio.sleep(0.5)
        await send_current_step(user_id, bot, chat_id)

    # ── question_single / question_single_forced ──────────────────────────────
    elif stype in ("question_single", "question_single_forced"):
        text = _format(current, name, gender)
        buttons = current.get("buttons", [])
        if text:
            await _send_with_media(bot, chat_id, text, current)
        await bot.send_message(
            chat_id,
            "Выберите ответ:",
            reply_markup=answer_buttons(buttons, day, step)
        )
        # Ждём callback ans

    # ── question_multi ────────────────────────────────────────────────────────
    elif stype == "question_multi":
        _multi_state[user_id] = set()
        text = _format(current, name, gender)
        buttons = current.get("buttons", [])
        if text:
            await _send_with_media(bot, chat_id, text, current)
        await bot.send_message(
            chat_id,
            "Выберите все подходящие варианты:",
            reply_markup=multi_buttons(buttons, set(), day, step)
        )
        # Ждём toggle + confirm

    # ── day_end ───────────────────────────────────────────────────────────────
    elif stype == "day_end":
        text = _format(current, name, gender)
        await bot.send_message(chat_id, text, parse_mode="HTML")
        await asyncio.sleep(1)
        next_day = current.get("next_day", day + 1)
        special = current.get("special")
        if special == "final_quiz":
            await bot.send_message(
                chat_id,
                "🏆 <b>Стажировка завершена! Все 5 дней пройдены.</b>\n"
                "Ты изучил 25 ESG-терминов. Пора проверить всё сразу — тебя ждёт финальный тест!",
                parse_mode="HTML",
                reply_markup=start_quiz_button()
            )
        else:
            await bot.send_message(
                chat_id,
                f"✅ <b>День {day} завершён!</b>\nДень {next_day} разблокирован.",
                parse_mode="HTML",
                reply_markup=start_day_button(next_day)
            )
        await advance_step(user_id)

    # ── Устаревшие типы (обратная совместимость) ──────────────────────────────
    elif stype == "ready_choice":
        await bot.send_message(
            chat_id,
            "👔 <b>Владимир Алексеевич:</b>\n\nНадеюсь, вы готов{г:|а}?".replace(
                "{г:|а}", "" if gender == "M" else "а"
            ),
            parse_mode="HTML",
            reply_markup=make_ready_keyboard()
        )

    elif stype == "question":
        text = apply_gender(current.get("text", ""), name, gender)
        options = [
            {"text": opt["text"], "callback_data": f"ans_{step}_{i}"}
            for i, opt in enumerate(current["options"])
        ]
        await bot.send_message(chat_id, text, parse_mode="HTML",
                               reply_markup=make_choice_keyboard(options))

    elif stype == "day_end_legacy":
        text = apply_gender(current["text"], name, gender)
        await bot.send_message(chat_id, text, parse_mode="HTML")
        await asyncio.sleep(1)
        next_day = current.get("next_day", day + 1)
        await bot.send_message(
            chat_id,
            f"✅ <b>День {day} завершён!</b>",
            parse_mode="HTML",
            reply_markup=make_continue_keyboard(f"Начать день {next_day} ▶️")
        )
        await advance_step(user_id)


async def _send_with_media(bot: Bot, chat_id: int, text: str, step: dict,
                           reply_markup=None):
    media = step.get("media")
    media_file = step.get("media_file")
    kwargs = dict(parse_mode="HTML", reply_markup=reply_markup)
    if media == "voice":
        await bot.send_message(
            chat_id,
            f"🎙️ <i>[Голосовое — {media_file or 'файл добавится позже'}]</i>\n\n{text}",
            **kwargs
        )
    elif media == "video":
        await bot.send_message(
            chat_id,
            f"🎥 <i>[Видео — {media_file or 'файл добавится позже'}]</i>\n\n{text}",
            **kwargs
        )
    else:
        await bot.send_message(chat_id, text, **kwargs)


# ── Реакции ───────────────────────────────────────────────────────────────────

async def _send_reactions(reactions: list[dict], bot: Bot, chat_id: int,
                           name: str, gender: str):
    for r in reactions:
        sender = r.get("sender", "system")
        raw = r.get("text", "")
        text = apply_gender(raw, name, gender)
        if sender == "system":
            formatted = f"<i>{text}</i>"
        else:
            formatted = _prefix(sender) + text
        await bot.send_message(chat_id, formatted, parse_mode="HTML")
        await asyncio.sleep(0.8)


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

# ── Кнопка «Далее» (message_pause) ───────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^day_\d+_\d+_next$"))
async def on_next(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    parts = callback.data.split("_")
    # day_{day}_{step}_next
    user_id = callback.from_user.id
    await advance_step(user_id)
    await send_current_step(user_id, callback.bot, callback.message.chat.id)
    await callback.answer()


# ── Кнопка «Начать день N» ────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^start_day_\d+$"))
async def on_start_day(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    day_num = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    await set_day(user_id, day_num)
    await send_current_step(user_id, callback.bot, callback.message.chat.id)
    await callback.answer()


# ── Ответ на question_single / question_single_forced ─────────────────────────
@router.callback_query(F.data.regexp(r"^day_\d+_\d+_ans_\d+$"))
async def on_answer_single(callback: CallbackQuery):
    parts = callback.data.split("_")
    # day_{day}_{step}_ans_{idx}
    day_val = int(parts[1])
    step_val = int(parts[2])
    ans_idx = int(parts[4])

    user_id = callback.from_user.id
    user = await get_user(user_id)
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"

    # Проверяем что это текущий шаг (защита от старых кнопок)
    if user["current_step"] != step_val or user["current_day"] != day_val:
        await callback.answer("Этот вопрос уже неактуален.", show_alert=False)
        return

    steps = load_day(day_val)
    current = steps[step_val]
    stype = current["type"]

    correct_list = current.get("correct", [0])
    is_correct = ans_idx in correct_list
    retry = current.get("retry", False) or stype == "question_single_forced"

    reactions_map = current.get("reactions", {})
    reactions = reactions_map.get(ans_idx, [])
    if isinstance(reactions, dict):
        reactions = [reactions]

    await callback.message.edit_reply_markup(reply_markup=None)

    if reactions:
        await _send_reactions(reactions, callback.bot, callback.message.chat.id, name, gender)

    if not is_correct and retry:
        # Показываем кнопки снова
        await asyncio.sleep(0.5)
        buttons = current.get("buttons", [])
        await callback.bot.send_message(
            callback.message.chat.id,
            "Попробуй ещё раз:",
            reply_markup=answer_buttons(buttons, day_val, step_val)
        )
    else:
        await asyncio.sleep(0.8)
        await advance_step(user_id)
        await send_current_step(user_id, callback.bot, callback.message.chat.id)

    await callback.answer()


# ── Toggle чекбокса question_multi ───────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^day_\d+_\d+_toggle_\d+$"))
async def on_toggle(callback: CallbackQuery):
    parts = callback.data.split("_")
    day_val = int(parts[1])
    step_val = int(parts[2])
    toggle_idx = int(parts[4])

    user_id = callback.from_user.id
    user = await get_user(user_id)
    if user["current_step"] != step_val or user["current_day"] != day_val:
        await callback.answer()
        return

    selected = _multi_state.get(user_id, set())
    if toggle_idx in selected:
        selected.discard(toggle_idx)
    else:
        selected.add(toggle_idx)
    _multi_state[user_id] = selected

    steps = load_day(day_val)
    current = steps[step_val]
    buttons = current.get("buttons", [])

    await callback.message.edit_reply_markup(
        reply_markup=multi_buttons(buttons, selected, day_val, step_val)
    )
    await callback.answer()


# ── Подтверждение question_multi ──────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^day_\d+_\d+_confirm$"))
async def on_confirm_multi(callback: CallbackQuery):
    parts = callback.data.split("_")
    day_val = int(parts[1])
    step_val = int(parts[2])

    user_id = callback.from_user.id
    user = await get_user(user_id)
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"

    if user["current_step"] != step_val or user["current_day"] != day_val:
        await callback.answer()
        return

    steps = load_day(day_val)
    current = steps[step_val]
    correct_set = set(current.get("correct", []))
    selected = _multi_state.get(user_id, set())
    is_correct = selected == correct_set

    reactions_map = current.get("reactions", {})
    key = "correct" if is_correct else "wrong"
    reactions = reactions_map.get(key, [])
    if isinstance(reactions, dict):
        reactions = [reactions]

    retry = current.get("retry", False)

    await callback.message.edit_reply_markup(reply_markup=None)

    if reactions:
        await _send_reactions(reactions, callback.bot, callback.message.chat.id, name, gender)

    if not is_correct and retry:
        _multi_state[user_id] = set()
        await asyncio.sleep(0.5)
        buttons = current.get("buttons", [])
        await callback.bot.send_message(
            callback.message.chat.id,
            "Попробуй ещё раз:",
            reply_markup=multi_buttons(buttons, set(), day_val, step_val)
        )
    else:
        _multi_state.pop(user_id, None)
        await asyncio.sleep(0.8)
        await advance_step(user_id)
        await send_current_step(user_id, callback.bot, callback.message.chat.id)

    await callback.answer()


# ── Обратная совместимость: старые callbacks ──────────────────────────────────

@router.callback_query(F.data == "ready_yes")
async def on_ready_yes(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
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
async def on_answer_legacy(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
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

    import json
    day_scores = json.loads(user.get("day_scores") or "{}")
    if option["is_correct"]:
        score_key = f"d{day}_correct"
        day_scores[score_key] = day_scores.get(score_key, 0) + 1
    else:
        score_key = f"d{day}_wrong"
        day_scores[score_key] = day_scores.get(score_key, 0) + 1

    await update_user(callback.from_user.id,
                      day_scores=json.dumps(day_scores, ensure_ascii=False))

    response_text = apply_gender(option["response"], name, gender)
    await callback.message.answer(response_text, parse_mode="HTML")
    await asyncio.sleep(1)
    await advance_step(callback.from_user.id)
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()
    