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
from pathlib import Path
from typing import Any

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramAPIError

from database import get_user, update_user, advance_step, set_day
from utils.keyboards import (
    next_button, answer_buttons, multi_buttons,
    start_day_button, start_quiz_button,
    make_choice_keyboard, make_continue_keyboard, make_ready_keyboard,
)

router = Router()

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

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


# ── Отправка медиа-файла ──────────────────────────────────────────────────────

async def _send_media_file(bot: Bot, chat_id: int, media_type: str,
                            media_file: str, caption: str | None = None):
    """
    Отправляет реальный медиа-файл из папки media/.
    voice/*.ogg  → send_voice  (отображается как голосовое сообщение)
    image/*.jpg  → send_photo
    video/*.mp4  → send_video
    """
    if not media_file:
        return

    # Ищем файл: либо полный путь, либо по типу
    path = MEDIA_DIR / media_file
    if not path.exists():
        # Попробуем угадать подпапку по типу
        sub = {"voice": "audio", "photo": "image", "video": "video"}.get(media_type, "")
        path = MEDIA_DIR / sub / media_file
        if not path.exists():
            return  # файл не найден — молча пропускаем

    file = FSInputFile(str(path))
    kwargs = {"caption": caption, "parse_mode": "HTML"} if caption else {}

    try:
        if media_type == "voice":
            await bot.send_voice(chat_id, file, **kwargs)
        elif media_type == "photo":
            await bot.send_photo(chat_id, file, **kwargs)
        elif media_type == "video":
            await bot.send_video(chat_id, file, **kwargs)
    except TelegramAPIError:
        pass  # если файл сломан — не крашимся


# ── Отправка шага с возможным медиа ──────────────────────────────────────────

async def _send_with_media(bot: Bot, chat_id: int, text: str, step: dict,
                           reply_markup=None):
    media_type = step.get("media")        # "voice" / "photo" / "video" / None
    media_file = step.get("media_file", "")
    kwargs = dict(parse_mode="HTML", reply_markup=reply_markup)

    if media_type and media_file:
        # Сначала отправляем текст, потом медиа
        if text:
            await bot.send_message(chat_id, text, **kwargs)
        await _send_media_file(bot, chat_id, media_type, media_file)
    else:
        if text:
            await bot.send_message(chat_id, text, **kwargs)


# ── Перемешивание кнопок ──────────────────────────────────────────────────────

def _shuffle_buttons(step: dict) -> tuple[list[str], dict[int, int]]:
    buttons = step.get("buttons", [])
    indexed = list(enumerate(buttons))
    random.shuffle(indexed)
    new_buttons = [text for _, text in indexed]
    mapping = {new_i: old_i for new_i, (old_i, _) in enumerate(indexed)}
    return new_buttons, mapping


def _remap_correct(correct: list[int], mapping: dict[int, int]) -> list[int]:
    reverse = {old: new for new, old in mapping.items()}
    return [reverse[c] for c in correct if c in reverse]


def _remap_reactions(reactions: dict, mapping: dict[int, int]) -> dict:
    reverse = {old: new for new, old in mapping.items()}
    new_reactions = {}
    for key, val in reactions.items():
        if isinstance(key, int) and key in reverse:
            new_reactions[reverse[key]] = val
        else:
            new_reactions[key] = val
    return new_reactions


_shuffle_map: dict[int, dict[int, int]] = {}


# ── Отправка реакций ──────────────────────────────────────────────────────────

async def _send_reactions(reactions: list[dict], bot: Bot, chat_id: int,
                          name: str, gender: str):
    for r in reactions:
        # Если это медиа-элемент реакции (не сообщение)
        if r.get("media_type") and r.get("media_file"):
            await asyncio.sleep(0.5)
            await _send_media_file(
                bot, chat_id,
                r["media_type"], r["media_file"],
                caption=r.get("text") or None
            )
            continue

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


# ── Основная функция отправки текущего шага ───────────────────────────────────

async def send_current_step(user_id: int, bot: Bot, chat_id: int):
    user = await get_user(user_id)
    if not user:
        return

    day = user["current_day"]
    step_idx = user["current_step"]

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

    if stype == "message":
        text = _format(current, name, gender)
        await _send_with_media(bot, chat_id, text, current)
        await advance_step(user_id)
        await asyncio.sleep(1)
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(0.5)
        await send_current_step(user_id, bot, chat_id)

    elif stype == "message_pause":
        text = _format(current, name, gender)
        await _send_with_media(bot, chat_id, text, current,
                               reply_markup=next_button(day, step_idx))

    elif stype == "system_message":
        text = _format(current, name, gender)
        await bot.send_message(chat_id, text, parse_mode="HTML")
        await advance_step(user_id)
        await asyncio.sleep(0.5)
        await send_current_step(user_id, bot, chat_id)

    elif stype in ("question_single", "question_single_forced"):
        text = _format(current, name, gender)
        if text:
            await _send_with_media(bot, chat_id, text, current)
        shuffled_buttons, mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = mapping
        await bot.send_message(
            chat_id,
            "Выберите ответ:",
            reply_markup=answer_buttons(shuffled_buttons, day, step_idx)
        )

    elif stype == "question_multi":
        _multi_state[user_id] = set()
        text = _format(current, name, gender)
        if text:
            await _send_with_media(bot, chat_id, text, current)
        shuffled_buttons, mapping = _shuffle_buttons(current)
        _shuffle_map[user_id] = mapping
        await bot.send_message(
            chat_id,
            "Выберите все подходящие варианты:",
            reply_markup=multi_buttons(shuffled_buttons, set(), day, step_idx)
        )

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


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS — без изменений
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^day_\d+_\d+_next$"))
async def on_next(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    user_id = callback.from_user.id
    await advance_step(user_id)
    await send_current_step(user_id, callback.bot, callback.message.chat.id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^start_day_\d+$"))
async def on_start_day(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    day_num = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    await set_day(user_id, day_num)
    await send_current_step(user_id, callback.bot, callback.message.chat.id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^day_\d+_\d+_ans_\d+$"))
async def on_answer_single(callback: CallbackQuery):
    parts = callback.data.split("_")
    day_val = int(parts[1])
    step_val = int(parts[2])
    new_idx = int(parts[4])

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


@router.callback_query(F.data.regexp(r"^day_\d+_\d+_toggle_\d+$"))
async def on_toggle(callback: CallbackQuery):
    parts = callback.data.split("_")
    day_val = int(parts[1])
    step_val = int(parts[2])
    toggle_new_idx = int(parts[4])

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
    mapping = _shuffle_map.get(user_id, {})
    if not mapping:
        return step.get("buttons", []), {}
    buttons = step.get("buttons", [])
    shuffled = [""] * len(buttons)
    for new_i, old_i in mapping.items():
        if new_i < len(shuffled) and old_i < len(buttons):
            shuffled[new_i] = buttons[old_i]
    return shuffled, mapping


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
    user = await get_user(callback.from_user.id)
    if user and user.get("current_day", 0) >= 6:
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
    