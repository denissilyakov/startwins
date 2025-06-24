import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# === Настройки ===
API_TOKEN = '7578554558:AAGwtDOYQWbw7b1axbhSfXYs0ttgTnawkOM'
SUPPORT_CHAT_ID = -1002764789009  # ID оператора или группы

# === Логирование ===
logging.basicConfig(level=logging.INFO)

# === Инициализация бота и диспетчера ===
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

# === Команда /start ===
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✍️ Оставить обращение")]],
        resize_keyboard=True
    )
    await message.answer(
        "Здравствуйте! 👋\n\n"
        "Вы обратились в бота поддержки сервиса *Звёздный Двойник*.\n"
        "Пожалуйста, опишите свою проблему или вопрос — мы обязательно вам ответим.",
        reply_markup=kb
    )

# === Команда /ответ для операторов ===
@dp.message(Command("ответ"))
async def reply_to_user(message: types.Message):
    try:
        parts = message.text.strip().split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("⚠️ Использование: /ответ user_id текст")
            return

        user_id = int(parts[1])
        reply_text = parts[2]

        await bot.send_message(
            user_id,
            f"💬 *Ответ от поддержки:*\n{reply_text}"
        )
        await message.answer("✅ Ответ отправлен пользователю.")
    except Exception as e:
        logging.exception("Ошибка при отправке ответа пользователю:")
        await message.answer(f"❌ Ошибка при отправке ответа: {e}")

# === Кнопка "Оставить обращение" ===
@dp.message(F.text == "✍️ Оставить обращение")
async def leave_request(message: types.Message):
    await message.answer("Опишите, пожалуйста, вашу проблему. Мы передадим её специалисту.")
    await bot.send_message(
        SUPPORT_CHAT_ID,
        f"📬 Пользователь @{message.from_user.username or 'Без username'} (ID: {message.from_user.id}) начал новое обращение."
    )

# === Приём текста обращения ===
@dp.message()
async def handle_request(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or 'Без username'
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()

    await bot.send_message(
        SUPPORT_CHAT_ID,
        f"🆕 Новое обращение:\n"
        f"👤 Имя: {full_name or 'Не указано'}\n"
        f"🔗 Username: @{username}\n"
        f"🆔 Chat ID: {user_id}\n"
        f"💬 Текст: {message.text}"
    )

    await message.answer("Спасибо! Ваше обращение принято. Мы скоро с вами свяжемся.")

# === Запуск бота ===
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
