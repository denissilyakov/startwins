#!/usr/bin/env python
# coding: utf-8

# In[ ]:

from astrology_module import get_astrology_text_for_date
import asyncio
import json
import locale
import logging
import random
import re
import sqlite3
import time
from datetime import datetime, timedelta
import threading
import requests
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)
from telegram import ReplyKeyboardRemove
from astrology_module import generate_chart_image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import BotCommand, MenuButtonCommands
import psycopg2
from telegram.ext import CallbackQueryHandler
from telegram.ext import Application
from simple_calendar import SimpleCalendar, calendar_handler
import os
from dotenv import load_dotenv


load_dotenv()

# Отключаем использование системных прокси
proxies = {
    "http": None,
    "https": None,
}
logging.basicConfig(level=logging.INFO)

ASK_NAME, ASK_BIRTHDATE, ASK_BIRTHPLACE, ASK_BIRTHTIME, ASK_VIP_DATE, WAIT_ANSWER, CONFIRM_RESET = range(7)

# Клавиатуры
cancel_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("Отменить")]], resize_keyboard=True
)
back_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("Назад")], [KeyboardButton("Отменить")]], resize_keyboard=True
)
menu_keyboard = ReplyKeyboardMarkup(
    [
        [   KeyboardButton("🔮Получить прогноз на завтра"),
            KeyboardButton("❤️Узнать о совместимости")
        ],
        [KeyboardButton("📅✨Детальный прогноз по событию")],  # Новая кнопка
        [KeyboardButton("🧠🌌Звездно-психологический портерт")],
        [KeyboardButton("👤⭐Изменить личные данные")],
    ],
    resize_keyboard=True,
)

def load_static_data():
    global ZODIAC_SIGNS, CHINESE_SIGNS, emoji_dict, zodiac_emojis, chinese_emojis

    conn = get_pg_connection()
    cursor = conn.cursor()

    # Загрузка ZODIAC_SIGNS
    cursor.execute("SELECT cutoff_date, name FROM zodiac_signs ORDER BY cutoff_date")
    ZODIAC_SIGNS = cursor.fetchall()  # [(120, "Козерог"), (218, "Водолей"), ...]

    # Загрузка CHINESE_SIGNS
    cursor.execute("SELECT name FROM chinese_signs ORDER BY id")
    CHINESE_SIGNS = [row[0] for row in cursor.fetchall()]

    # Загрузка emoji_dict
    cursor.execute("SELECT keyword, emoji FROM emoji_mapping")
    rows = cursor.fetchall()
    emoji_dict = {}
    for keyword, emoji in rows:
        emoji_dict.setdefault(keyword, []).append(emoji)

    # Загрузка zodiac_emojis
    cursor.execute("SELECT form, emoji FROM zodiac_emojis")
    zodiac_emojis = dict(cursor.fetchall())

    # Загрузка chinese_emojis
    cursor.execute("SELECT form, emoji FROM chinese_emojis")
    chinese_emojis = dict(cursor.fetchall())

    conn.close()
    print("✅ Статические данные успешно загружены из базы данных.")


def get_pg_connection():
    db_url = os.getenv("ASTROLOG_DB")
    if db_url is None:
        raise ValueError("Переменная окружения ASTROLOG_DB не установлена")
    return psycopg2.connect(db_url)

# Настройка логирования
logging.basicConfig(
    filename="/Users/denissilyakov/Astrolog/bot/astro_bot.log",  # Путь и имя файла для логов
    level=logging.INFO,  # Уровень логирования (можно использовать DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Формат логов
    encoding="utf-8",  # Кодировка
)

def save_conversation_context(user_id, context):
    conn = get_pg_connection()
    cursor = conn.cursor()

    # Проверяем, что context — это список
    if isinstance(context, str):
        # Если передали строку — конвертируем в список
        context = [int(x.strip()) for x in context.strip('[]').split(',') if x.strip().isdigit()]

    # Ограничение на 1000 токенов
    if len(context) > 1000:
        context = context[-1000:]  # Оставляем последние 1000 токенов

    cursor.execute("""
        INSERT INTO user_conversations (user_id, context, timestamp)
        VALUES (%s, %s, %s)
    """, (user_id, json.dumps(context, ensure_ascii=False), datetime.now()))
    
    conn.commit()
    conn.close()


def get_conversation_context(user_id):
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT context FROM user_conversations WHERE user_id = %s
    ORDER BY timestamp DESC LIMIT 1
    """, (user_id,))

    context_data = cursor.fetchall()
    conn.close()

    # Если контексты есть, объединяем их в одну строку
    if context_data:
        # Преобразуем каждую запись в список чисел и объединяем их в один список
        context = []
        for row in context_data:
            # Извлекаем строку контекста и преобразуем в список целых чисел
            context_values = row[0].strip('[]').split(',')  # удаляем скобки и разбиваем по запятой
            # Добавляем элементы в список, преобразовав их в целые числа
            context.extend([int(value.strip()) for value in context_values if value.strip().isdigit()])
        return context  # Возвращаем список целых чисел
    else:
        return []  # если нет контекстов, возвращаем пустой список


# Функция для получения вопросов из базы данных
def get_questions(chain_id):
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT question, options, options_position, chain_order FROM question_chains
        WHERE chain_id = %s
        ORDER BY chain_order
        """,
        (chain_id,),
    )

    questions = cursor.fetchall()
    conn.close()
    return questions



# Функция для получения кнопок из базы данных, сортированных по позиции
def get_dynamic_menu_buttons(menu_chain_id):
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT button_name, button_action, position FROM dynamic_menu WHERE menu_chain_id = %s
    ORDER BY position
    """, (menu_chain_id,)
    )
    buttons = cursor.fetchall()

    conn.close()
    return buttons

async def user_wait_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_answer = update.message.text.strip()
    question_step = context.user_data["question_step"]
    chain_id = context.user_data.get("chain_id")
    
    if update.message.text.strip() == "📋 Главное меню":
        await show_menu(update, context)
        return ConversationHandler.END


    # Инициализация event_answers, если её нет
    if "event_answers" not in context.user_data:
        context.user_data["event_answers"] = {}

    # Получаем вопросы для текущей цепочки
    questions = get_questions(chain_id)
    current_question = questions[question_step]

    
    options_str = current_question[1]
    
        # Сохраняем options для календаря
    context.user_data["current_options_str"] = options_str

    # ➡️ Календарь вместо текстового ввода
    if options_str:
        if "DATE" in options_str:
            calendar = SimpleCalendar(
                min_date=datetime.now() + timedelta(days=1),
                max_date=None
            )
            await update.message.reply_text("📅 Выберите дату:", reply_markup=calendar.build_calendar())
            return WAIT_ANSWER

        if "PASTDT" in options_str:
            calendar = SimpleCalendar(
                min_date=None,
                max_date=datetime.now() - timedelta(days=1)
            )
            await update.message.reply_text("📅 Выберите дату в прошлом:", reply_markup=calendar.build_calendar())
            return WAIT_ANSWER

        if "BIRTHDT" in options_str:
            calendar = SimpleCalendar(
                min_date=datetime(1925, 1, 1),
                max_date=datetime(2015, 12, 31)
            )
            await update.message.reply_text("📅 Укажите дату рождения:", reply_markup=calendar.build_calendar())
            return WAIT_ANSWER
    
    # Проверяем, если пользователь нажал на кнопку "📋 Главное меню"
    if user_answer == "📋 Главное меню":
        context.user_data["question_step"] = 0
        context.user_data["event_answers"]= {}
        question_step = 0
        await show_menu(update, context)  # Показать основное меню
        return ConversationHandler.END  # Завершаем текущий разговор
    
    
    # Проверяем наличие DATE в options
    if options_str and "DATE" in options_str:
        if not is_valid_date(user_answer):
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод

        # Проверка, чтобы дата была позже сегодняшнего дня
        try:
            entered_date = datetime.strptime(user_answer, "%d.%m.%Y")
            if entered_date <= datetime.now():
                await update.message.reply_text(
                    "Дата должна быть позже сегодняшнего дня. Пожалуйста, введите корректную дату."
                )
                return WAIT_ANSWER  # Ожидаем новый ввод
        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод
    
        # Проверяем наличие PASTDT в options
    if options_str and "PASTDT" in options_str:
        if not is_valid_date(user_answer):
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод

        # Проверка, чтобы дата была позже сегодняшнего дня
        try:
            entered_date = datetime.strptime(user_answer, "%d.%m.%Y")
            if entered_date > datetime.now():
                await update.message.reply_text(
                    "Дата должна быть раньше сегодняшнего дня. Пожалуйста, введите корректную дату."
                )
                return WAIT_ANSWER  # Ожидаем новый ввод
        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод
        
        
            # Проверяем наличие BIRHDATE в options
    if options_str and "BIRTHDT" in options_str:
        if not is_valid_date(user_answer):
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод

        # Проверка, чтобы дата была позже сегодняшнего дня
        try:
            entered_date = datetime.strptime(user_answer, "%d.%m.%Y")
            if entered_date > datetime.now():
                await update.message.reply_text(
                    "Дата должна быть раньше сегодняшнего дня. Пожалуйста, введите корректную дату."
                )
                return WAIT_ANSWER  # Ожидаем новый ввод
        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.2025."
            )
            return WAIT_ANSWER  # Ожидаем новый ввод
        zodiac, chinese = get_zodiac_and_chinese_sign(user_answer)
        
        
        context.user_data["bdate_zodiac"] = zodiac
        context.user_data["bdate_chinese"] = chinese

    # Сохраняем ответ в user_data
    context.user_data["event_answers"][question_step] = user_answer
    
    # Дополнительная обработка для DATE/PASTDT/BIRTHDT
    if options_str and any(opt in options_str for opt in ["DATE", "PASTDT", "BIRTHDT"]):
        if "planets_info_counter" not in context.user_data:
            context.user_data["planets_info_counter"] = 0
        else:
            context.user_data["planets_info_counter"] += 1

        planets_key = f"planets_info_{context.user_data['planets_info_counter']}"

        planets_info = get_astrology_text_for_date(
            user_answer,
            time_str="12:00",
            mode="model",
            tz_offset=context.user_data.get("tz_offset", 0)
        )
        context.user_data[planets_key] = planets_info


    # Сохраняем ответ в БД
    save_answer_to_db(
        update.effective_user.id,
        context.user_data["chain_id"],
        question_step,
        user_answer,
    )
    # Переход к следующему шагу
    context.user_data["question_step"] += 1

    # Если все вопросы заданы, генерируем прогнозы
    if context.user_data["question_step"] >= len(questions):
        await generate_forecasts_from_chain(update, context)
        return ConversationHandler.END

    # Если есть вопросы, переходим к следующему вопросу
    return await ask_question(update, context)


def save_user_data(user_id, data):
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (
            user_id, name, birthdate, gender, zodiac,
            chinese_year, birthplace, tz_offset, birthtime, chat_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            name = EXCLUDED.name,
            birthdate = EXCLUDED.birthdate,
            gender = EXCLUDED.gender,
            zodiac = EXCLUDED.zodiac,
            chinese_year = EXCLUDED.chinese_year,
            birthplace = EXCLUDED.birthplace,
            tz_offset = EXCLUDED.tz_offset,
            birthtime = EXCLUDED.birthtime,
            chat_id = EXCLUDED.chat_id
        """,
        (
            user_id,
            data.get("name"),
            data.get("birthdate"),
            data.get("gender"),
            data.get("zodiac"),
            data.get("chinese_year"),
            data.get("birthplace"),
            data.get("tz_offset"),
            data.get("birthtime"),
            data.get("chat_id"),  # <--- новое поле
        ),
    )

    conn.commit()
    conn.close()



def load_user_data(user_id):
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name, birthdate, gender, zodiac,
               chinese_year, birthplace, tz_offset, birthtime, chat_id
        FROM users WHERE user_id = %s
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "name": row[0],
            "birthdate": row[1],
            "gender": row[2],
            "zodiac": row[3],
            "chinese_year": row[4],
            "birthplace": row[5],
            "tz_offset": row[6],
            "birthtime": row[7],
            "chat_id": row[8],   # <--- читаем chat_id
        }
    return {}


def decorate_with_emojis(text: str) -> str:
    words = re.findall(r"\w+", text.lower())
    matched_emojis = []
    used_emojis = set()

    for word in words:
        for key in emoji_dict:
            if key in word:
                emojis = [e for e in emoji_dict[key] if e not in used_emojis]
                if emojis:
                    emoji = random.choice(emojis)
                    matched_emojis.append((word, emoji))
                    used_emojis.add(emoji)
                    break

    all_zodiacs = "|".join(re.escape(k) for k in zodiac_emojis)
    all_chinese = "|".join(re.escape(k) for k in chinese_emojis)
    zodiac_pattern = re.compile(r"\b(" + all_zodiacs + r")\b")
    chinese_pattern = re.compile(r"\b(" + all_chinese + r")\b")

    def insert_zodiac_emoji(match):
        return f"{match.group(0)} {zodiac_emojis[match.group(0)]}"

    def insert_chinese_emoji(match):
        return f"{match.group(0)} {chinese_emojis[match.group(0)]}"

    text = zodiac_pattern.sub(insert_zodiac_emoji, text)
    text = chinese_pattern.sub(insert_chinese_emoji, text)

    if not matched_emojis:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text)
    for i, sentence in enumerate(sentences):
        inserted = 0
        for word, emoji in matched_emojis:
            if inserted >= 3:
                break
            if word in sentence.lower() and emoji not in sentence:
                pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
                sentence = pattern.sub(
                    lambda m: m.group(0) + f" {emoji}", sentence, count=1
                )
                inserted += 1
        sentences[i] = sentence

    return " ".join(sentences)


def get_zodiac_and_chinese_sign(birthdate: str):
    # Преобразуем дату в формат год-месяц-день
    day, month, year = map(int, birthdate.split("."))
    mmdd = int(f"{month:02}{day:02}")  # Формируем дату в формате ммдд
    zodiac = next(sign for cutoff, sign in ZODIAC_SIGNS if mmdd <= cutoff)
    chinese = CHINESE_SIGNS[(year - 1900) % 12]
    return zodiac, chinese


async def detect_gender(name: str) -> str:

    payload = {
        "model": "gemma3:latest",
        "prompt": f"Определи пол человека по имени: {name}. Ответь только одним словом: мужской или женский.",
        "stream": False,
        "temperature": 0.5,
        "system": "Ты лингвист. Отвечай строго: мужской или женский.",
    }
    try:
        res = requests.post("http://localhost:11434/api/generate", json=payload, proxies=proxies)
        answer = res.json().get("response", "").strip().lower()
        return "женский" if "жен" in answer else "мужской"
    except:
        return "мужской"

# Вставляем разогрев модели
async def warm_up_model():
    try:
        # Пример запроса к модели (замените на ваш реальный запрос)
        payload = {
            "model": "gemma3:latest",
            "prompt": "Разогрев модели",
            "stream": False,
            "temperature": 0.7,
            "system": "Система разогрева"
        }
        # Отправляем запрос к модели
        response = requests.post("http://localhost:11434/api/generate", json=payload, proxies=proxies)
        
        # Проверка успешности запроса
        if response.status_code == 200:
            logging.info("Модель разогрета успешно")
        else:
            logging.error(f"Ошибка при разогреве модели: {response.status_code}")
    except Exception as e:
        logging.error(f"Ошибка при разогреве модели: {e}")



# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Определяем объект для ответа
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        logging.error("❗ Не удалось найти message для отправки старта.")
        return

    # Корректный chat_id
    chat_id = message.chat_id
    context.user_data["chat_id"] = chat_id

    # Загрузка данных пользователя
    user_data = load_user_data(user_id)
    if user_data:
        context.user_data.update(user_data)

    # Устанавливаем дефолтные значения, если их нет
    context.user_data.setdefault("question_step", 0)
    context.user_data.setdefault("event_answers", {})
    context.user_data.setdefault("chain_id", 1)
    context.user_data.setdefault("question_chain_id", 1)

    # Вычисляем планеты, если есть дата рождения и нет расчётов
    if "birthdate" in context.user_data and "user_planets_info" not in context.user_data:
        context.user_data["user_planets_info"] = get_astrology_text_for_date(
            context.user_data["birthdate"],
            time_str=context.user_data.get("birthtime", "12:00"),
            mode="model",
            tz_offset=context.user_data.get("tz_offset", 0)
        )

    # Если пользователь зарегистрирован — показываем меню
    if "name" in context.user_data and "birthdate" in context.user_data:
        await message.reply_text(
            "👋 Твои данные загружены успешно. Выбери действие из меню:",
            reply_markup=menu_keyboard,
        )
        return ConversationHandler.END

    # Иначе — это новый пользователь, просим ввести имя
    await message.reply_text(
        "🌟 Добро пожаловать в АстроТвинз!\n\nДавай познакомимся, напиши как тебя зовут.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_NAME




# Очистка данных
async def reset_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ Ты уверен, что хочешь изменить личные данные?\nВся история общения будет удалена.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Уверен")], [KeyboardButton("Отменить")]],
            resize_keyboard=True,
        ),
    )
    return CONFIRM_RESET

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    user_id = update.effective_user.id

    if "уверен" in text:
        # Удаление из БД
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_conversations WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM forecasts WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
        conn.close()

        context.user_data.clear()
        
        context.user_data["chat_id"] = update.effective_chat.id
        await update.message.reply_text(
            "🗑️ Данные удалены. Введи своё имя:", reply_markup=ReplyKeyboardRemove()
        )
        return ASK_NAME

    elif "отмен" in text:
        await update.message.reply_text("❌ Отмена. Возвращаюсь в меню.", reply_markup=menu_keyboard)
        return ConversationHandler.END

    else:
        await update.message.reply_text("Пожалуйста, нажмите «Уверен» или «Отменить».")
        return CONFIRM_RESET


# Имя
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["name"] = name
    gender = await detect_gender(name)
    context.user_data["gender"] = gender
    await update.message.reply_text(
        f"Спасибо, {name}. Твой пол определён как {gender}.\nТеперь введи дату рождения в формате день.месяц.год (например, 14.02.1978):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_BIRTHDATE


# Дата рождения
async def get_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Применяем нормализацию и проверку даты
    normalized_date = normalize_and_validate_date(text)

    if normalized_date:
        context.user_data["birthdate"] = normalized_date
        zodiac, chinese = get_zodiac_and_chinese_sign(normalized_date)
        context.user_data["zodiac"] = zodiac
        context.user_data["chinese_year"] = chinese
        save_user_data(user_id, context.user_data)
        
        context.user_data["user_planets_info"] = get_astrology_text_for_date(
        normalized_date,
        time_str=context.user_data.get("birthtime", "12:00"),
        mode="model",
        tz_offset=context.user_data.get("tz_offset", 0)
        )

        await update.message.reply_text(
            f"Принято! Знак зодиака: {zodiac}, Восточный знак: {chinese}.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "📍 Укажите место рождения (пример: деревня Лазурная, Конаковский район, Тверская область):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ASK_BIRTHPLACE
    else:
        await update.message.reply_text(
            "Неверный формат даты. Пожалуйста, введите дату в формате день.месяц.год, например 01.01.1990."
        )
        return ASK_BIRTHDATE



async def detect_timezone_offset(location: str) -> int:
    payload = {
        "model": "gemma3:latest",
        "prompt": f"Определи часовой сдвиг (в формате +3 или -5) по месту рождения: {location}. Ответь числом — целым с плюсом или минусом, без пояснений.",
        "stream": False,
        "temperature": 0.3,
        "system": "Ты географ. Отвечай строго целым числом: например, +3 или -5.",
    }
    try:
        res = requests.post("http://localhost:11434/api/generate", json=payload, proxies=proxies)
        answer = res.json().get("response", "").strip()
        match = re.match(r"[+-]?\d+", answer)
        return int(match.group(0)) if match else 0
    except:
        return 0

async def get_birthplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    place = update.message.text.strip()
    context.user_data["birthplace"] = place

    # Определяем часовой сдвиг через модель
    tz_offset = await detect_timezone_offset(place)
    context.user_data["tz_offset"] = tz_offset

    await update.message.reply_text(
        f"Спасибо! Место рождения сохранено. Часовой сдвиг в месте рождения: UTC{'+' if tz_offset >= 0 else ''}{tz_offset}",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Переход к следующему шагу — запрос времени рождения
    await update.message.reply_text(
        "🕰️ Укажите время рождения (в формате ЧЧ:ММ), например 14:30.\nЕсли не знаете точное время — нажмите «Не знаю».",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Не знаю")]], resize_keyboard=True
        ),
    )
    return ASK_BIRTHTIME



# Прогноз на завтра
async def forecast_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tomorrow = datetime.now() + timedelta(days=1)
    context.user_data["forecast_date"] = tomorrow.strftime("%d.%m.%Y")
    context.user_data["chain_id"] = 10

    # Начинаем задавать вопросы, начиная с первого
    context.user_data["question_step"] = 0  # Сохраняем шаг для начала с первого вопроса
    return await ask_question(update, context)  # Запускаем цепочку вопросов


# VIP-дата
async def ask_vip_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем кнопки из базы данных
    buttons = get_dynamic_menu_buttons(2)

    if not buttons:
        await update.message.reply_text("Ошибка! Нет доступных кнопок.")
        return ConversationHandler.END

    # Создаем клавиатуру с кнопками
    keyboard = create_dynamic_keyboard(buttons)

    # Отправляем клавиатуру с кнопками
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

    return ConversationHandler.END



# История и навигация
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем кнопки из базы данных
    buttons = get_dynamic_menu_buttons(4)

    if not buttons:
        await update.message.reply_text("Ошибка! Нет доступных кнопок.")
        return ConversationHandler.END

    # Создаем клавиатуру с кнопками
    keyboard = create_dynamic_keyboard(buttons)

    # Отправляем клавиатуру с кнопками
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

    return ConversationHandler.END


async def history_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    page = context.user_data.get("history_page", 0)
    if "вперёд" in text:
        context.user_data["history_page"] = page + 1
    elif "назад" in text:
        context.user_data["history_page"] = max(0, page - 1)
    return await show_history(update, context)


# Меню и отмена
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌌 До встречи под звёздами!", reply_markup=menu_keyboard
    )
    return ConversationHandler.END


# Показ сохраненного в БД прогноза
async def show_saved_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    forecast_date = context.user_data.get("forecast_date")
    aspect = context.user_data.get("aspect")

    if not forecast_date or not aspect:
        await update.message.reply_text(
            "Нет запрошенного прогноза. Попробуйте снова через меню."
        )
        return ConversationHandler.END

    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT text FROM forecasts 
        WHERE user_id = %s AND forecast_date = %s AND aspect = %s
    """,
        (user_id, forecast_date, aspect),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        decorated = decorate_with_emojis(row[0])
        await update.message.reply_text(
            f"📆 Прогноз на {forecast_date} ({aspect}):\n\n{decorated}"
        )
    else:
        await update.message.reply_text("⚠️ Прогноз не найден в архиве.")

    # Возврат в главное меню
    await update.message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)
    return ConversationHandler.END



# Функция для создания клавиатуры с кнопками динамического меню
def create_dynamic_keyboard(buttons):
    keyboard = []
    current_row = []  # Для хранения кнопок в текущем ряду
    last_position = None  # Для отслеживания предыдущей позиции

    for button_name, button_action, position in buttons:
        # Если позиция изменилась и current_row не пуст, то нужно добавить текущий ряд в keyboard
        if position != last_position and current_row:
            keyboard.append(current_row)  # Добавляем предыдущий ряд
            current_row = []  # Новый ряд для кнопок с новой позицией

        # Добавляем кнопку в текущий ряд
        current_row.append(KeyboardButton(button_name))

        # Обновляем последнюю позицию
        last_position = position

    # Добавляем последний ряд, если он не пуст
    if current_row:
        keyboard.append(current_row)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функция для получения chain_id кнопки из базы данных
def get_chain_id_for_button(button_action):
    print("Button Action")
    print((button_action))
    
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT chain_id FROM dynamic_menu
    WHERE button_action = %s
    """,
        (button_action,),
    )

    result = cursor.fetchone()
    conn.close()
    print("get_chain_id_for_button, chain_id")
    print(result)
    if result:
        return result[0]  # Возвращаем найденный chain_id
    return None  # Если chain_id не найден, возвращаем None


# Обработчик для нажатия кнопки динамического меню
async def handle_dynamic_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    #Обработчик для нажатия кнопки динамического меню. Получает chain_id кнопки, обновляет его в user_data,
    #если chain_id не найден, то выводит ошибку, иначе - запускает цепочку вопросов.
    
    button_action = update.message.text.strip()  # Получаем действие кнопки
    print(f"Пользователь выбрал кнопку с действием: {button_action}")  # Логирование

    # Получаем chain_id для этой кнопки
    
    
    
    chain_id = get_chain_id_for_button(button_action)
    print("handle_dynamic_button, chain_id, button_action")
    print(chain_id)
    print(button_action)

    if chain_id is None:
        await update.message.reply_text(
            "Ошибка! Для этой кнопки не настроена цепочка вопросов."
        )
        return ConversationHandler.END

    # Обновляем chain_id в user_data
    context.user_data["chain_id"] = chain_id

    # Начинаем задавать вопросы, начиная с первого
    context.user_data["question_step"] = 0  # Сохраняем шаг для начала с первого вопроса
    return await ask_question(update, context)  # Запускаем цепочку вопросов


# Измененная функция generate_detailed_forecast
async def generate_detailed_forecast(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt, tone, temperature
):
    user_id = update.effective_user.id
    # Применяем замену переменных в промпте
    prompt = replace_variables_in_prompt(prompt, context)
    
        # Убираем меню перед началом генерации прогноза
    await update.message.reply_text(
        "Запрашиваю прогноз. Пожалуйста, немножко подождите...",
        reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
    )
    
    
    # Получаем последние 5 записей контекста
    conversation_context = get_conversation_context(user_id)

    payload = {
        "model": "gemma3:latest",
        "prompt": prompt,
        "stream": True,
        "temperature": temperature,
        "system": tone
    }
    
        # Добавляем контекст только если он не пустой
    if conversation_context != '[]':
        payload["context"] = conversation_context

    print(payload) #ОТЛАДКА
    typing_msg = await update.message.reply_text("…")
    try:
        response = requests.post(
            "http://localhost:11434/api/generate", json=payload, stream=True, proxies=proxies
        )
        astro_text = ""
        buffer = ""
        first = True

        for line in response.iter_lines(decode_unicode=True):
            if line.strip():
                part = json.loads(line)
                chunk = part.get("response", "")
                if chunk:
                    astro_text += chunk
                    buffer += chunk

                    if "\n" in buffer:
                        parts = buffer.split("\n")
                        for para in parts[:-1]:
                            clean_para = para.strip()
                            if clean_para:
                                decorated = decorate_with_emojis(clean_para)
                                if first:
                                    await typing_msg.edit_text(decorated)
                                    first = False
                                else:
                                    msg = await context.bot.send_message(
                                        chat_id=update.effective_chat.id, text="…"
                                    )
                                    delay = len(clean_para.split()) * 0.2
                                    await asyncio.sleep(delay)
                                    await msg.edit_text(decorated)
                        buffer = parts[-1]

        last_para = buffer.strip()
        if last_para:
            decorated = decorate_with_emojis(last_para)
            msg = await context.bot.send_message(
                chat_id=update.effective_chat.id, text="…"
            )
            delay = len(last_para.split()) * 0.2
            await asyncio.sleep(delay)
            await msg.edit_text(decorated)

        # Сохраняем прогноз в базу данных
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO forecasts (user_id, forecast_date, aspect, forecast_text)
            VALUES (%s, %s, %s, %s)
        """,
            (
                user_id,
                datetime.now().strftime("%d %B %Y года"),
                "Детальный прогноз по событию",
                astro_text,
            ),
        )
        cursor.connection.commit()
        

        # После получения нового ответа
        new_context = part["context"]
        # Сохраняем обновленный контекст в базе данных
        save_conversation_context(user_id,  new_context)

        # await update.message.reply_text(f"Прогноз на {datetime.now().strftime('%d %B %Y года')}:\n\n{astro_text}")

    except Exception as e:
        logging.error(f"Ошибка при генерации прогноза: {e}")
        await update.message.reply_text("Ошибка при генерации прогноза.")


# Обработчик кнопки "Детальный прогноз по событию"
async def detailed_vip_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем кнопки из базы данных
    buttons = get_dynamic_menu_buttons(3)

    if not buttons:
        await update.message.reply_text("Ошибка! Нет доступных кнопок.")
        return ConversationHandler.END

    # Создаем клавиатуру с кнопками
    keyboard = create_dynamic_keyboard(buttons)

    # Отправляем клавиатуру с кнопками
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

    return ConversationHandler.END


# Функция для обработки цепочки вопросов
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        print("❗ Не удалось найти message для отправки вопроса.")
        return

    chain_id = context.user_data.get("chain_id")

    if not chain_id:
        await message.reply_text("Ошибка! Не указана цепочка вопросов.")
        return ConversationHandler.END

    questions = get_questions(chain_id)
    if not questions:
        await message.reply_text("Ошибка! Вопросы для выбранной цепочки не найдены.")
        return ConversationHandler.END

    question_step = context.user_data.get("question_step", 0)
    current_question = questions[question_step]
    question_text = current_question[0]
    options_str = current_question[1]
    options_position_str = current_question[2]

    # Преобразуем опции
    try:
        options = json.loads(options_str) if options_str else []
    except json.JSONDecodeError:
        options = []

    # Преобразуем позиции
    try:
        options_positions = json.loads(options_position_str) if options_position_str else []
    except json.JSONDecodeError:
        options_positions = []

    logging.info(f"Текущий вопрос: {question_text}")
    logging.info(f"Опции: {options}")
    logging.info(f"Позиции: {options_positions}")


    # Ключевые слова — запуск календаря
    special_inputs = {"DATE", "PASTDT", "BIRTHDT"}
    if any(opt in special_inputs for opt in options):
        context.user_data["current_options_str"] = options_str

        calendar = None
        if "DATE" in options_str:
            calendar = SimpleCalendar(min_date=datetime.now() + timedelta(days=1))
        elif "PASTDT" in options_str:
            calendar = SimpleCalendar(max_date=datetime.now() - timedelta(days=1))
        elif "BIRTHDT" in options_str:
            calendar = SimpleCalendar(
                min_date=datetime(1925, 1, 1),
                max_date=datetime(2015, 12, 31),
                center_year=2000
            )


        if calendar:
            await message.reply_text(
                "⌨️ Выберите дату из календаря ниже:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("📋 Главное меню")]],
                    resize_keyboard=True
                )
            )
            await message.reply_text(
                question_text,
                reply_markup=calendar.build_year_selection()
            )
            return WAIT_ANSWER


    # Если опций нет — обычный текстовый ввод
    if not options:
        await message.reply_text(
            f"{question_text}\nПожалуйста, введите свой ответ:"
        )
        return WAIT_ANSWER

    # Строим клавиатуру
    if options_positions and len(options) == len(options_positions):
        grouped = {}
        for opt, pos in zip(options, options_positions):
            grouped.setdefault(pos, []).append(KeyboardButton(opt))
        keyboard = [grouped[k] for k in sorted(grouped)]
    else:
        # fallback — все кнопки в одну строку
        keyboard = [[KeyboardButton(opt) for opt in options]]

    keyboard.append([KeyboardButton("📋 Главное меню")])
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await message.reply_text(question_text, reply_markup=markup)
    return WAIT_ANSWER



    # Если опции отсутствуют — текстовый ввод
    if not options:
        await update.message.reply_text(
            f"{question_text}\nПожалуйста, введите свой ответ:"
        )
        return WAIT_ANSWER

    # Строим клавиатуру
    if options_positions and len(options) == len(options_positions):
        grouped = {}
        for opt, pos in zip(options, options_positions):
            grouped.setdefault(pos, []).append(KeyboardButton(opt))
        keyboard = [grouped[k] for k in sorted(grouped)]
    else:
        # fallback — все кнопки в одну строку
        keyboard = [[KeyboardButton(opt) for opt in options]]

    keyboard.append([KeyboardButton("📋 Главное меню")])
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(question_text, reply_markup=markup)
    return WAIT_ANSWER




# Функция для получения цепочки параметров из таблицы question_chain_prompts
def get_question_chain_prompts(chain_id):
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT prompt, tone, temperature, chain_order FROM question_chain_prompts
    WHERE chain_id = %s
    ORDER BY chain_order
    """,
        (chain_id,),
    )

    prompts = cursor.fetchall()

    conn.close()
    return prompts


# Функция для генерации всех прогнозов на основе цепочки
async def generate_forecasts_from_chain(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    # Получаем chain_id из данных пользователя
    chain_id = context.user_data.get("chain_id")

    if not chain_id:
        await update.message.reply_text("Ошибка! Не указан chain_id.")
        return ConversationHandler.END

    # Получаем цепочку значений prompt, tone, temperature из базы данных
    prompts = get_question_chain_prompts(chain_id)

    # Для каждого prompt, вызываем функцию generate_detailed_forecast
    for prompt, tone, temperature, _ in prompts:
        await generate_detailed_forecast(update, context, prompt, tone, temperature)
        
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="show_reply_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # После завершения всех вызовов показываем главное меню
    await update.message.reply_text(
        "🔔 Прогноз завершён! 🔔 — а хочешь узнать о себе ещё больше? ✨ Погрузись глубже в тайны своей судьбы с приложением ✨\"Звёздный двойник\" 🪞 — там тебя ждут новые возможности, редкие знания и расширенная астрологическая картина!"
    , reply_markup=menu_keyboard
    )

    return ConversationHandler.END

def replace_variables_in_prompt(prompt, context):
    chain_id = context.user_data.get("chain_id")
    if chain_id:
        collect_questions_for_chain(context, chain_id)

    logging.info(f"Event Questions: {context.user_data.get('event_questions')}")

    # Стандартные переменные
    variables = {
        "{name}": context.user_data.get("name", ""),
        "{birthdate}": context.user_data.get("birthdate", ""),
        "{zodiac}": context.user_data.get("zodiac", ""),
        "{chinese_year}": context.user_data.get("chinese_year", ""),
        "{gender}": context.user_data.get("gender", ""),
        "{forecast_date}": context.user_data.get("forecast_date", ""),
        "{bdate_zodiac}": context.user_data.get("bdate_zodiac", ""),
        "{bdate_chinese}": context.user_data.get("bdate_chinese", ""),
        "{user_planets_info}": context.user_data.get("user_planets_info", ""),
    }

    # --- Теперь корректно обрабатываем forecast_date для планет ---
    forecast_date_str = context.user_data.get("forecast_date")
    if forecast_date_str:
        forecast_date_for_planets = context.user_data.get("forecast_date")
        if forecast_date_for_planets:
            if "planets_info_fd" not in context.user_data:
                planets_info_fd = get_astrology_text_for_date(
                    forecast_date_for_planets,
                    time_str="12:00",
                    mode="model",
                    tz_offset=context.user_data.get("tz_offset", 0)
                )
                context.user_data["planets_info_fd"] = planets_info_fd

            variables["{planets_info_fd}"] = context.user_data.get("planets_info_fd", "")

    # --- Замена стандартных переменных ---
    for key, value in variables.items():
        prompt = prompt.replace(key, value)

    # --- Замена вопросов ---
    for step in range(len(context.user_data.get("event_questions", []))):
        question = context.user_data["event_questions"][step]
        prompt = prompt.replace(f"{question_key(step)}", question)

    # --- Замена ответов ---
    for step, answer in context.user_data.get("event_answers", {}).items():
        prompt = prompt.replace(f"{answer_key(step)}", answer)

    # --- Подставляем planets_info_N ---
    for step in range(0, context.user_data.get("planets_info_counter", -1) + 1):
        planets_key = f"planets_info_{step}"
        planets_info = context.user_data.get(planets_key, "")
        prompt = prompt.replace(f"{{{planets_key}}}", planets_info)

    prompt = prompt.replace("{", "").replace("}", "")
    return prompt



    # Проверим, не используются ли фигурные скобки как часть текста. Заменим их на безопасные символы.
    #prompt = prompt.replace("{", "").replace("}", "")



def collect_questions_for_chain(context, chain_id):
    """
    Собирает вопросы для заданной цепочки по chain_id и сохраняет их
    в context.user_data['event_questions']. Вопросы индексируются с 0.

    Ожидается, что get_questions(chain_id) возвращает:
    (question_text, options, options_position, chain_order)
    """
    questions = get_questions(chain_id)

    if not questions:
        logging.error(f"Вопросы для цепочки с chain_id {chain_id} не найдены.")
        return

    # Сортируем по chain_order (4-й элемент — x[3])
    try:
        sorted_questions = sorted(questions, key=lambda x: int(x[3]))
    except Exception as e:
        logging.error(f"Ошибка при сортировке вопросов: {e}")
        sorted_questions = questions  # fallback — без сортировки

    # Индексируем вопросы
    event_questions = {
        index: q[0] for index, q in enumerate(sorted_questions)
    }

    context.user_data["event_questions"] = event_questions
    logging.info(
        f"Собрано {len(event_questions)} вопросов для цепочки с chain_id {chain_id}."
    )



def answer_key(step):
    # Это будет {answer_1}, {answer_2} и так далее
    return f"answer_{step}"


def question_key(step):
    # Это будет {questions_1}, {questions_2} и так далее
    return f"question_{step}"


# Сохранение ответа на вопрос
def save_answer_to_db(user_id, chain_id, question_step, answer):
    retries = 5
    for attempt in range(retries):
        try:
            conn = get_pg_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO question_chain_answers (user_id, chain_id, question_step, answer)
                VALUES (%s, %s, %s, %s)
            """,
                (user_id, chain_id, question_step, answer),
            )
            conn.commit()
            conn.close()
            break
        except sqlite3.OperationalError as e:
            if attempt < retries - 1:
                time.sleep(1)  # Ожидаем 1 секунду перед повтором
            else:
                logging.error(f"Ошибка при сохранении данных в БД: {e}")
                raise


# Функция для проверки формата даты
def is_valid_date(date_str: str) -> bool:
    try:
        # Пробуем парсить дату в формате день.месяц.год
        datetime.strptime(date_str, "%d.%m.%Y")
        return True
    except ValueError:
        return False

# Функция для нормализации и проверки даты
def normalize_and_validate_date(date_str: str) -> str:
    # Пытаемся обработать несколько форматов
    for fmt in (
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ):  # Добавляем несколько возможных форматов
        try:
            date_object = datetime.strptime(date_str, fmt)
            # Преобразуем в формат день.месяц.год
            return date_object.strftime("%d.%m.%Y")
        except ValueError:
            pass  # Если не совпал формат, пробуем следующий

    # Если не удалось распознать дату в известных форматах, возвращаем None
    return None

# Обработчик для кнопки "📋 Главное меню"
async def handle_main_menu(update, context):
    # Показать главное меню, если была нажата кнопка "📋 Главное меню"
    if update.message.text == "📋 Главное меню":
        await show_menu(update, context)

def run_model_warmup_in_thread():
    asyncio.run(warm_up_model())

async def get_birthtime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text.lower() == "не знаю":
        birthtime = "12:00"
    else:
        # Проверка формата времени
        try:
            datetime.strptime(text, "%H:%M")
            birthtime = text
        except ValueError:
            await update.message.reply_text(
                "Неверный формат времени. Введите в формате ЧЧ:ММ, например 14:30, или нажмите «Не знаю»"
            )
            return ASK_BIRTHTIME

    context.user_data["birthtime"] = birthtime

    await update.message.reply_text(
        f"Принято. Время рождения: {birthtime}",
        reply_markup=menu_keyboard
    )

    # Демонстрация карты планет (с учётом времени, если будет использоваться в будущем)
    planet_text = get_astrology_text_for_date(
        context.user_data["birthdate"],
        time_str=context.user_data.get("birthtime", "12:00"),
        mode="pretty",
        tz_offset=context.user_data.get("tz_offset", 0)
    )
    await update.message.reply_text(f"Карта планет: {planet_text}")
    
    await update.message.reply_text(f"Идет подготовка натальной карты, подождите пожалуйста несколько секунд...")
    buf = generate_chart_image(context.user_data["birthdate"], birthtime, context.user_data.get("tz_offset", 0), context.user_data["name"])
    await update.message.reply_photo(photo=buf, caption="🌌 Твоя натальная карта")

    save_user_data(user_id, context.user_data)
    return ConversationHandler.END

async def set_menu(application):
    # Устанавливаем свои команды
    await application.bot.set_my_commands([
        BotCommand("start", "Начать 🚀"),
        BotCommand("menu", "Главное меню 📋"),
        BotCommand("profile", "Профиль 👤"),
        BotCommand("help", "Помощь ❓")
    ])

    # Устанавливаем кнопку меню
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()
    )

async def setup(application):
    await set_menu(application)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 Ты можешь задать любой вопрос или сообщить о проблеме в телеграмм чате «Звездный двойник».\n"
        "Наша команда незамедлительно поможет тебе."
    )

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)

    if not user_data:
        await update.message.reply_text("⚠️ Информация о пользователе не найдена. Пожалуйста, начните с команды /start.")
        return

    name = user_data.get("name", "❌ Не указано")
    birthdate = user_data.get("birthdate", "❌ Не указано")
    birthplace = user_data.get("birthplace", "❌ Не указано")
    tz_offset = user_data.get("tz_offset", "❌ Не указано")
    tz_offset_formatted = f"UTC{tz_offset:+}" if tz_offset is not None else "❌ Не указано"

    profile_text = (
        "👤 Информация о пользователе:\n\n"
        f"• Имя: {name}\n"
        f"• Дата рождения: {birthdate}\n"
        f"• Место рождения: {birthplace}\n"
        f"• Часовой сдвиг в месте рождения: {tz_offset_formatted}"
    )

    await update.message.reply_text(profile_text)

def get_all_chat_ids():
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM users WHERE chat_id IS NOT NULL")
    chat_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return chat_ids

async def send_update_notification_to_all_chats(application):
    chat_ids = get_all_chat_ids()
    notification_text = (
        "📢 Дорогой друг!\n\n"
        "Бот обновлён и теперь стал ещё лучше 🌟\n"
        "Добавлены новые функции и улучшено качество прогнозов!\n"
        "Нажмите кнопку ниже, чтобы обновить сервис."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить сервис", callback_data="/start")]
    ])
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=notification_text,
                reply_markup=keyboard
            )
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Ошибка отправки в чат {chat_id}: {e}")


async def handle_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await start(update, context)

async def send_start_on_launch(app: Application):
    await send_update_notification_to_all_chats(app)

async def full_post_init(application):
    # Сначала ставим кнопки меню
    await setup(application)
    # Потом отправляем всем обновлённое сообщение
    await send_start_on_launch(application)


# Запуск
def main():
    
    
    load_static_data()  # <--- Загружаем все константы из БД
    
    # --- перед запуском polling --- запускаем задачу рассылки
    async def startup_tasks():
        await send_update_notification_to_all_chats(app)
    
    app = (
        ApplicationBuilder()
        .token(os.getenv("ASTROLOG_BOT"))
        .post_init(full_post_init)  # <<< ВОТ ТУТ ДОБАВЛЯЕМ
        .build()
    )
    
    # Сохраняем функции в bot_data для календаря
    app.bot_data["save_answer_to_db"] = save_answer_to_db
    app.bot_data["ask_question"] = ask_question

    # Запуск разогрева модели при старте бота
    threading.Thread(target=run_model_warmup_in_thread).start()
    
    

    # Обновляем ConversationHandler
    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Получить прогноз на завтра$"), forecast_tomorrow
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Узнать о совместимости$"), ask_vip_date
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Изменить личные данные$"), reset_user_data
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Детальный прогноз по событию$"),
                detailed_vip_forecast,
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Звездно-психологический портерт$"), show_history
            ),            
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, handle_dynamic_button
            ),  # Добавить обработчик для кнопок
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthdate)],
            ASK_BIRTHPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthplace)],
            ASK_BIRTHTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthtime)],
            WAIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_wait_answer)],
            CONFIRM_RESET: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_reset)],
        },
        fallbacks=[MessageHandler(filters.Regex("(?i)^отменить$"), cancel)],
    )

    app.add_handler(conv_handler)

    app.add_handler(MessageHandler(filters.Regex("(?i)^◀ назад$"), history_navigation))
    app.add_handler(MessageHandler(filters.Regex("(?i)^вперёд ▶$"), history_navigation))
    app.add_handler(MessageHandler(filters.Regex("(?i)^меню$"), show_menu))
    app.add_handler(MessageHandler(filters.Regex("📋 Главное меню"), handle_main_menu))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))  # У тебя уже есть функция show_menu
    app.add_handler(CommandHandler("help", show_help))  # Нужно будет сделать функцию show_help
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CallbackQueryHandler(handle_start_callback, pattern="^/start$"))
    app.add_handler(CallbackQueryHandler(calendar_handler, pattern="^calendar_"))


    
    app.run_polling()

if __name__ == "__main__":
    main()


# %%
