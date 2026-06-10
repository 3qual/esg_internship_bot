# handlers/days.py
"""
Универсальный движок шагов для всех 5 дней стажировки.
Поддерживаемые типы: message, message_pause, question_single,
question_multi, question_single_forced, system_message, day_end
"""
import asyncio
import importlib
import random
import re
from typing import Any

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery

from database import get_user, update_user, advance_step, set_day
from utils.keyboards import (
    next_button, answer_buttons, multi_buttons,
    start_day_button, start_quiz_button,
    make_choice_keyboard, make_continue_keyboard, make_ready_keyboard,
)

router = Router()

# ── Состояние question_multi (user_id → set of selected indices) ──────────────
_multi_state: dict[int, set] = {}


# ── Загрузка контента дня ─────────────────────────────────────────────────────

def load_day(day_number: int) -> list[dict]:
    module = importlib.import_module(f"content.day{day_number}")
    return module.STEPS


# ── Форматирование текста с гендером и именем ─────────────────────────────────

def apply_gender(text: str, name: str, gender: str) -> str:
    result = text.replace("{name}", name)
    result = re.sub(
        r"\{г:([^|]*)\|([^}]*)\}",
        lambda m: m.group(1) if gender == "M" else m.group(2),
        result
    )
    return result


# ── Префикс отправителя ───────────────────────────────────────────────────────

def _prefix(sender: str) -> str:
    return {
        "hr":          "👔 <b>Анатолий (HR):</b>\n\n",
        "boss":        "👔 <b>Владимир Алексеевич:</b>\n\n",
        "liza":        "💬 <b>Лиза:</b>\n\n",
        "liza_hidden": "🔒 <i>Скрыто от Владимира:</i>\n💬 <b>Лиза:</b>\n\n",
        "system":      "",
    }.get(sender, "")


def _format(step: dict, name: str, gender: str) -> str:
    sender = step.get("sender", "system")
    raw = step.get("text", "")
    text = apply_gender(raw, name, gender)
    if sender == "system":
        return f"<i>{text}</i>"
    return _prefix(sender) + text


# ── Отправка с медиа-заглушкой ────────────────────────────────────────────────

async def _send_with_media(bot: Bot, chat_id: int, text: str, step: dict,
                           reply_markup=None):
    media = step.get("media")
    media_file = step.get("media_file", "")
    kwargs = dict(parse_mode="HTML", reply_markup=reply_markup)

    if media == "voice":
        # Заглушка голосового сообщения
        description = media_file if media_file else "голосовое сообщение"
        placeholder = f"🎙️ <i>[Голосовое — {description}]</i>"
        full_text = f"{placeholder}\n\n{text}" if text else placeholder
        await bot.send_message(chat_id, full_text, **kwargs)

    elif media == "video":
        # Заглушка видео
        description = media_file if media_file else "видео"
        placeholder = f"🎥 <i>[Видео — {description}]</i>"
        full_text = f"{placeholder}\n\n{text}" if text else placeholder
        await bot.send_message(chat_id, full_text, **kwargs)

    else:
        if text:
            await bot.send_message(chat_id, text, **kwargs)


# ── Перемешивание кнопок (сохраняем маппинг новый_idx → старый_idx) ──────────

def _shuffle_buttons(step: dict) -> tuple[list[str], dict[int, int]]:
    """
    Возвращает (перемешанные_кнопки, маппинг {новый_idx: старый_idx}).
    Используется чтобы после перемешивания правильно определять correct/reactions.
    """
    buttons = step.get("buttons", [])
    indexed = list(enumerate(buttons))           # [(0, "текст0"), (1, "текст1"), ...]
    random.shuffle(indexed)
    new_buttons = [text for _, text in indexed]
    mapping = {new_i: old_i for new_i, (old_i, _) in enumerate(indexed)}
    return new_buttons, mapping


def _remap_correct(correct: list[int], mapping: dict[int, int]) -> list[int]:
    """Пересчитывает индексы правильных ответов под новый порядок кнопок."""
    reverse = {old: new for new, old in mapping.items()}
    return [reverse[c] for c in correct if c in reverse]


def _remap_reactions(reactions: dict, mapping: dict[int, int]) -> dict:
    """Пересчитывает ключи reactions (числовые) под новый порядок кнопок."""
    reverse = {old: new for new, old in mapping.items()}
    new_reactions = {}
    for key, val in reactions.items():
        if isinstance(key, int) and key in reverse:
            new_reactions[reverse[key]] = val
        else:
            new_reactions[key] = val   # "correct"/"wrong" — не трогаем
    return new_reactions


# ── Хранилище маппингов перемешанных кнопок (user_id → mapping) ──────────────
_shuffle_map: dict[int, dict[int, int]] = {}


# ── Основная функция отправки текущего шага ───────────────────────────────────

async def send_current_step(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    if not user:
        return

    day = user["current_day"]
    step_idx = user["current_step"]

    # day=6/7 → финальный тест (обрабатывается quiz.py)
    if day >= 6:
        return

    if day == 0:
        await set_day(user_id, 1)
        user = await get_user(user_id)
        day, step_idx = 1, 0

    try:
        steps = load_day(day)
    except ModuleNotFoundError:
        await bot.send_message(
            chat_id,
            f"📅 <b>День {day}</b> — контент в разработке. Следи за обновлениями!",
            parse_mode="HTML"
        )
        return

    if step_idx >= len(steps):
        await set_day(user_id, day + 1)
        await send_current_step(user_id, bot, chat_id)
        return

    current = steps[step_idx]
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
                               reply_markup=next_button(day, step_idx))

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
        if text:
            await _send_with_media(bot, chat_id, text, current)

        # Перемешиваем кнопки
        shuffled_buttons, mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = mapping

        await bot.send_message(
            chat_id,
            "Выберите ответ:",
            reply_markup=answer_buttons(shuffled_buttons, day, step_idx)
        )

    # ── question_multi ────────────────────────────────────────────────────────
    elif stype == "question_multi":
        _multi_state[user_id] = set()
        text = _format(current, name, gender)
        if text:
            await _send_with_media(bot, chat_id, text, current)

        # Перемешиваем кнопки
        shuffled_buttons, mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = mapping

        await bot.send_message(
            chat_id,
            "Выберите все подходящие варианты:",
            reply_markup=multi_buttons(shuffled_buttons, set(), day, step_idx)
        )

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
                "🏆 Нажми кнопку ниже, чтобы начать финальный тест!",
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
            "👔 <b>Владимир Алексеевич:</b>\n\nНадеюсь, вы готов{}?".format(
                "" if gender == "M" else "а"
            ),
            parse_mode="HTML",
            reply_markup=make_ready_keyboard()
        )

    elif stype == "question":
        text = apply_gender(current.get("text", ""), name, gender)
        options = [
            {"text": opt["text"], "callback_data": f"ans_{step_idx}_{i}"}
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


# ── Отправка реакций ──────────────────────────────────────────────────────────

async def _send_reactions(reactions: list[dict], bot: Bot, chat_id: int,
                          name: str, gender: str):
    for r in reactions:
        sender = r.get("sender", "system")
        raw = r.get("text", "")
        text = apply_gender(raw, name, gender)
        if not text:
            continue
        if sender == "system":
            formatted = f"<i>{text}</i>"
        else:
            formatted = _prefix(sender) + text
        await bot.send_message(chat_id, formatted, parse_mode="HTML")
        await asyncio.sleep(0.8)


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

# ── Кнопка «Далее» ────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^day_\d+_\d+_next$"))
async def on_next(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
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
    day_val = int(parts[1])
    step_val = int(parts[2])
    new_idx = int(parts[4])   # индекс в ПЕРЕМЕШАННОМ порядке

    user_id = callback.from_user.id
    user = await get_user(user_id)
    name = user["name"] or "стажёр"
    gender = user["gender"] or "M"

    if user["current_step"] != step_val or user["current_day"] != day_val:
        await callback.answer("Этот вопрос уже неактуален.", show_alert=False)
        return

    steps = load_day(day_val)
    current = steps[step_val]
    stype = current["type"]

    # Восстанавливаем оригинальный индекс через маппинг
    mapping = _shuffle_map.get(user_id, {})
    orig_idx = mapping.get(new_idx, new_idx)

    correct_list = current.get("correct", [0])
    is_correct = orig_idx in correct_list
    retry = current.get("retry", False) or stype == "question_single_forced"

    reactions_map = current.get("reactions", {})
    reactions = reactions_map.get(orig_idx, [])
    if isinstance(reactions, dict):
        reactions = [reactions]

    await callback.message.edit_reply_markup(reply_markup=None)

    if reactions:
        await _send_reactions(reactions, callback.bot, callback.message.chat.id, name, gender)

    if not is_correct and retry:
        await asyncio.sleep(0.5)
        # Новое перемешивание для повтора
        shuffled_buttons, new_mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = new_mapping
        await callback.bot.send_message(
            callback.message.chat.id,
            "Попробуй ещё раз:",
            reply_markup=answer_buttons(shuffled_buttons, day_val, step_val)
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
    toggle_new_idx = int(parts[4])   # индекс в перемешанном порядке

    user_id = callback.from_user.id
    user = await get_user(user_id)

    if user["current_step"] != step_val or user["current_day"] != day_val:
        await callback.answer()
        return

    selected = _multi_state.get(user_id, set())
    if toggle_new_idx in selected:
        selected.discard(toggle_new_idx)
    else:
        selected.add(toggle_new_idx)
    _multi_state[user_id] = selected

    steps = load_day(day_val)
    current = steps[step_val]
    shuffled_buttons, _ = _get_shuffled(user_id, current)

    await callback.message.edit_reply_markup(
        reply_markup=multi_buttons(shuffled_buttons, selected, day_val, step_val)
    )
    await callback.answer()


def _get_shuffled(user_id: int, step: dict) -> tuple[list[str], dict]:
    """Возвращает текущий перемешанный порядок кнопок для пользователя."""
    mapping = _shuffle_map.get(user_id, {})
    if not mapping:
        return step.get("buttons", []), {}
    buttons = step.get("buttons", [])
    shuffled = [""] * len(buttons)
    for new_i, old_i in mapping.items():
        if new_i < len(shuffled) and old_i < len(buttons):
            shuffled[new_i] = buttons[old_i]
    return shuffled, mapping


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

    # Переводим выбранные новые индексы обратно в оригинальные
    mapping = _shuffle_map.get(user_id, {})
    selected_new = _multi_state.get(user_id, set())
    selected_orig = {mapping.get(i, i) for i in selected_new}

    correct_set = set(current.get("correct", []))
    is_correct = selected_orig == correct_set

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
        # Новое перемешивание для повтора
        shuffled_buttons, new_mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = new_mapping
        await callback.bot.send_message(
            callback.message.chat.id,
            "Попробуй ещё раз:",
            reply_markup=multi_buttons(shuffled_buttons, set(), day_val, step_val)
        )
    else:
        _multi_state.pop(user_id, None)
        _shuffle_map.pop(user_id, None)
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
    # Только если НЕ в состоянии теста (quiz.py перехватит раньше если роутеры подключены правильно)
    user = await get_user(callback.from_user.id)
    if user and user.get("current_day", 0) >= 6:
        # Отдаём quiz.py — но на случай если порядок роутеров неправильный, дублируем
        from handlers.quiz import send_quiz_question
        await callback.message.edit_reply_markup(reply_markup=None)
        await send_quiz_question(callback.from_user.id, callback.bot, callback.message.chat.id)
        await callback.answer()
        return
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
    score_key = f"d{day}_correct" if option["is_correct"] else f"d{day}_wrong"
    day_scores[score_key] = day_scores.get(score_key, 0) + 1
    await update_user(callback.from_user.id,
                      day_scores=json.dumps(day_scores, ensure_ascii=False))

    response_text = apply_gender(option["response"], name, gender)
    await callback.message.answer(response_text, parse_mode="HTML")
    await asyncio.sleep(1)
    await advance_step(callback.from_user.id)
    await send_current_step(callback.from_user.id, callback.bot, callback.message.chat.id)
    await callback.answer()
    