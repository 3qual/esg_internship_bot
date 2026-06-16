# handlers/start.py
"""
Обработчик онбординга: /start → анкета (Пол → Возраст → Имя) → день 1
"""
import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import create_user, get_user, update_user, set_day
from utils.keyboards import make_start_keyboard, make_gender_keyboard

router = Router()


class OnboardingStates(StatesGroup):
    waiting_gender = State()
    waiting_age    = State()
    waiting_name   = State()


# ── /start ────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await create_user(message.from_user.id)
    user = await get_user(message.from_user.id)

    # Если уже зарегистрирован — продолжаем с места остановки
    if user and user["name"]:
        from handlers.days import send_current_step
        await send_current_step(message.from_user.id, message.bot, message.chat.id)
        return

    await message.answer(
        "Авторы: Арсений Лапшин, Ирина Бережная, Ника Бошина, Анна Лобанова\n\n\n",
        "👔 <b>Анатолий (HR):</b>\n\n"
        "Здравствуйте, меня зовут Анатолий! "
        "Я HR-менеджер компании <b>ESG Group</b>. "
        "Нам откликнулось ваше резюме!\n"
        "Предлагаем подать заявку на прохождение стажировки!",
        parse_mode="HTML",
        reply_markup=make_start_keyboard()
    )


# ── Кнопка «Подать заявку» ────────────────────────────────────────────────────
@router.callback_query(F.data == "apply")
async def on_apply(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "Отлично! Для начала укажите ваш пол:",
        reply_markup=make_gender_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_gender)
    await callback.answer()


# ── Шаг 1: Пол ───────────────────────────────────────────────────────────────
@router.callback_query(OnboardingStates.waiting_gender, F.data.in_({"gender_M", "gender_F"}))
async def on_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split("_")[1]
    await state.update_data(gender=gender)
    await callback.message.edit_reply_markup()
    await callback.message.answer("Сколько вам лет? (введите число)")
    await state.set_state(OnboardingStates.waiting_age)
    await callback.answer()


# ── Шаг 2: Возраст ───────────────────────────────────────────────────────────
@router.message(OnboardingStates.waiting_age)
async def on_age(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Введите возраст цифрами, например: 21")
        return
    age = int(message.text.strip())
    if not (10 <= age <= 99):
        await message.answer("Введите реальный возраст от 10 до 99.")
        return
    await state.update_data(age=age)
    await message.answer("И последнее — как вас зовут?")
    await state.set_state(OnboardingStates.waiting_name)


# ── Шаг 3: Имя ───────────────────────────────────────────────────────────────
@router.message(OnboardingStates.waiting_name)
async def on_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 30:
        await message.answer("Пожалуйста, введите корректное имя (2–30 символов).")
        return

    data = await state.get_data()
    gender = data["gender"]
    age = data["age"]

    await update_user(
        message.from_user.id,
        name=name, gender=gender, age=age,
        current_day=1, current_step=0
    )
    await state.clear()

    await message.answer("✅ <b>Заявка отправлена</b> 😊", parse_mode="HTML")
    await asyncio.sleep(3)
    await message.answer(
        "🎉 <b>Вы одобрены на должность стажёра в ESG Group!</b>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1)

    from handlers.days import send_current_step
    await send_current_step(message.from_user.id, message.bot, message.chat.id)
    