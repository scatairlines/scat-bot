import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
from datetime import datetime
from aiohttp import web
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ СЕКРЕТОВ ===
API_TOKEN = os.getenv("API_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "google-credentials.json")

# === GOOGLE SHEETS НАСТРОЙКА ===
creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
sheet_service = build('sheets', 'v4', credentials=creds).spreadsheets().values()

# === СОСТОЯНИЯ ОПРОСА ===
class Survey(StatesGroup):
    name = State()
    employee_id = State()
    base = State()
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

bot = Bot(API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def has_filled(employee_id):
    result = sheet_service.get(spreadsheetId=SPREADSHEET_ID, range='A2:Z').execute()
    values = result.get('values', [])
    for row in values:
        if len(row) > 2 and row[2] == employee_id:
            return True
    return False

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await message.answer("Введите ваше ФИО:")
    await state.set_state(Survey.name)

@dp.message(Survey.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите ваш ID сотрудника:")
    await state.set_state(Survey.employee_id)

@dp.message(Survey.employee_id)
async def process_id(message: Message, state: FSMContext):
    employee_id = message.text.strip()
    if has_filled(employee_id):
        await message.answer("❗️Вы уже проходили опрос.")
        await state.clear()
        return
    await state.update_data(employee_id=employee_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Астана", callback_data="base_astana")],
        [InlineKeyboardButton(text="Алматы", callback_data="base_almaty")],
        [InlineKeyboardButton(text="Шымкент", callback_data="base_shymkent")],
        [InlineKeyboardButton(text="Актау", callback_data="base_aktau")],
    ])
    await message.answer("Выберите вашу базировку:", reply_markup=keyboard)
    await state.set_state(Survey.base)

@dp.callback_query(Survey.base)
async def process_base(call: CallbackQuery, state: FSMContext):
    base_map = {
        "base_astana": "Астана",
        "base_almaty": "Алматы",
        "base_shymkent": "Шымкент",
        "base_aktau": "Актау"
    }
    await state.update_data(base=base_map[call.data])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Полностью удовлетворен(а)", callback_data="q1_1")],
        [InlineKeyboardButton(text="Скорее удовлетворен(а), чем нет", callback_data="q1_2")],
        [InlineKeyboardButton(text="Скорее не удовлетворен(а), чем удовлетворен(а)", callback_data="q1_3")],
        [InlineKeyboardButton(text="Полностью не удовлетворен(а)", callback_data="q1_4")],
    ])
    await call.message.edit_text("1. Насколько вы удовлетворены текущими стандартами сервиса?", reply_markup=keyboard)
    await state.set_state(Survey.q1)
    await call.answer()

@dp.callback_query(Survey.q1)
async def process_q1(call: CallbackQuery, state: FSMContext):
    answers = {
        "q1_1": "Полностью удовлетворен(а)",
        "q1_2": "Скорее удовлетворен(а), чем нет",
        "q1_3": "Скорее не удовлетворен(а), чем удовлетворен(а)",
        "q1_4": "Полностью не удовлетворен(а)",
    }
    await state.update_data(q1=answers[call.data], q2=[])
    await send_q2(call.message, state)
    await state.set_state(Survey.q2)
    await call.answer()

async def send_q2(message, state: FSMContext):
    data = await state.get_data()
    selected = data.get("q2", [])
    options = [
        ("Вежливость и клиентоориентированность экипажа", "politeness"),
        ("Качество питания и напитков", "food"),
        ("Обратная связь от пассажиров", "feedback"),
        ("Комфорт салона и чистота", "comfort"),
        ("Процессы обслуживания", "process"),
        ("Командная работа и взаимодействие", "teamwork")
    ]
    builder = InlineKeyboardBuilder()
    for text, value in options:
        prefix = "✅ " if value in selected else "☐ "
        builder.button(text=prefix + text, callback_data="q2_" + value)
    builder.button(text="➡ Далее", callback_data="q2_done")
    builder.adjust(1)
    await message.edit_text("2. Какие аспекты нуждаются в улучшении? (до 2)", reply_markup=builder.as_markup())

@dp.callback_query(Survey.q2)
async def process_q2(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("q2", [])
    if call.data == "q2_done":
        await state.set_state(Survey.q3)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="q3_1")],
            [InlineKeyboardButton(text="Есть пробелы", callback_data="q3_2")],
            [InlineKeyboardButton(text="Недостаточно", callback_data="q3_3")],
            [InlineKeyboardButton(text="Устарело", callback_data="q3_4")],
        ])
        await call.message.edit_text("3. Достаточно ли вы обучены?", reply_markup=keyboard)
        await call.answer()
        return
    option = call.data[3:]
    if option in selected:
        selected.remove(option)
    elif len(selected) < 2:
        selected.append(option)
    await state.update_data(q2=selected)
    await send_q2(call.message, state)
    await call.answer()

@dp.callback_query(Survey.q3)
async def process_q3(call: CallbackQuery, state: FSMContext):
    answers = {
        "q3_1": "Да",
        "q3_2": "Есть пробелы",
        "q3_3": "Недостаточно",
        "q3_4": "Устарело",
    }
    await state.update_data(q3=answers[call.data])
    await call.message.edit_text("4. Ваши предложения по улучшению сервиса:")
    await state.set_state(Survey.q4)
    await call.answer()

@dp.message(Survey.q4)
async def process_q4(message: Message, state: FSMContext):
    await state.update_data(q4=message.text, q5=[])
    await send_q5(message, state)
    await state.set_state(Survey.q5)

async def send_q5(message_or_call, state: FSMContext, edit=False):
    data = await state.get_data()
    selected = data.get("q5", [])
    options = [
        ("Недостаток времени на каждого пассажира", "time"),
        ("Ограниченность ресурсов (еда, вода, расходники)", "resources"),
        ("Неудобный порядок обслуживания / процедуры", "order"),
        ("Языковой барьер", "lang"),
        ("Агрессивное поведение пассажиров", "aggression"),
        ("Технические неисправности оборудования", "tech")
    ]
    builder = InlineKeyboardBuilder()
    for text, value in options:
        prefix = "✅ " if value in selected else "☐ "
        builder.button(text=prefix + text, callback_data="q5_" + value)
    builder.button(text="✅ Завершить", callback_data="q5_done")
    builder.adjust(1)
    text = "5. Какие трудности вы чаще всего испытываете при обслуживании пассажиров? (до 2)"
    if edit:
        await message_or_call.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message_or_call.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(Survey.q5)
async def process_q5(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("q5", [])
    if call.data == "q5_done":
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        q2_labels = {
            "politeness": "Вежливость и клиентоориентированность экипажа",
            "food": "Качество питания и напитков",
            "feedback": "Обратная связь от пассажиров",
            "comfort": "Комфорт салона и чистота",
            "process": "Процессы обслуживания",
            "teamwork": "Командная работа и взаимодействие"
        }
        q5_labels = {
            "time": "Недостаток времени на каждого пассажира",
            "resources": "Ограниченность ресурсов (еда, вода, расходники)",
            "order": "Неудобный порядок обслуживания / процедуры",
            "lang": "Языковой барьер",
            "aggression": "Агрессивное поведение пассажиров",
            "tech": "Технические неисправности оборудования"
        }
        q2_text = ", ".join([q2_labels.get(item, item) for item in data.get("q2", [])])
        q5_text = ", ".join([q5_labels.get(item, item) for item in data.get("q5", [])])
        row = [
            data["timestamp"],
            data.get("full_name", ""),
            data.get("employee_id", ""),
            str(call.from_user.id),
            data.get("base", ""),
            data.get("q1", ""),
            q2_text,
            data.get("q3", ""),
            data.get("q4", ""),
            q5_text,
        ]
        sheet_service.append(
            spreadsheetId=SPREADSHEET_ID,
            range="A2",
            valueInputOption="USER_ENTERED",
            body={"values": [row]}
        ).execute()
        await call.message.edit_text("✅ Спасибо! Ваши ответы записаны.")
        await state.clear()
        await call.answer()
        return
    option = call.data[3:]
    if option in selected:
        selected.remove(option)
    elif len(selected) < 2:
        selected.append(option)
    await state.update_data(q5=selected)
    await send_q5(call.message, state, edit=True)
    await call.answer()

# === ВЕБ-СЕРВЕР ДЛЯ UPTIME ROBOT ===
async def handle(request):
    return web.Response(text="✅ Bot is running")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# === ЗАПУСК ===
if __name__ == "__main__":
    async def main():
        await start_webserver()
        await dp.start_polling(bot)

    asyncio.run(main())
