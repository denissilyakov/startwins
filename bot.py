#!/usr/bin/env python
# coding: utf-8

# In[ ]:

from astrology_module import get_astrology_text_for_date, save_user_astrology
from invite_links import create_portrait_invite, build_share_button
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
from astrology_utils import (
    get_inline_questions,
    get_user_asked_inline_questions,
    log_user_inline_question,
    handle_pre_checkout,
    handle_successful_payment,
    handle_invoice_callback
)
from astrology_utils import get_user_inline_question_texts
from uuid import uuid4
import httpx
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
from astrology_utils import update_user_balance, get_user_balance, insert_coin_transaction, add_welcome_bonus_if_needed
from yookassa import Configuration, Payment
import uuid
from telegram.ext import PreCheckoutQueryHandler
from dateutil.relativedelta import relativedelta


# Настройка ключей ЮKassa
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")
load_dotenv()
BOT_USERNAME = os.getenv("BOT_USERNAME")
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
        [   KeyboardButton("🔮Прогноз на завтра"),
            KeyboardButton("❤️Узнать о совместимости")
        ],
        [KeyboardButton("📅Прогноз на событие"), KeyboardButton("🌠 Задай свой вопрос")],  # Новая кнопка
        [KeyboardButton("🌌Астро-Психология"), KeyboardButton("🪞Звёздный двойник")],
        [KeyboardButton("🪙 Подписка и баланс")],
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

def create_new_inline_id() -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nextval('inline_questions_inline_id_seq')")
            return cursor.fetchone()[0]
    finally:
        conn.close()
        



async def generate_inline_questions_for_user(user_id: int, context, chat_id: int, topic: int):
    name = context.user_data.get("name", "")
    gender = context.user_data.get("gender", "")
    birthdate = context.user_data.get("birthdate", "")
    zodiac = context.user_data.get("zodiac", "")
    chinese = context.user_data.get("chinese_year", "")

    # Получаем натальную карту, если ещё не рассчитана
    if "birthdate" in context.user_data and "user_planets_info" not in context.user_data:
        context.user_data["user_planets_info"] = get_astrology_text_for_date(
            context.user_data["birthdate"],
            time_str=context.user_data.get("birthtime", "12:00"),
            mode="model",
            tz_offset=context.user_data.get("tz_offset", 0)
        )

    planets = context.user_data.get("user_planets_info", "")
    
    topic = int(context.user_data.get("topic"))
    if topic ==1: 
        prompt_id = 96
        promt_question_theme = "направленные на изучение собственного я."
    if topic ==2: 
        prompt_id = 97
        promt_question_theme = "вопросы на самореализацию в сфере любви."
    if topic ==3: 
        prompt_id = 98
        promt_question_theme = "вопросы на самореализацию в сфере работы."
    if topic ==4: 
        prompt_id = 99
        promt_question_theme = "вопросы на самореализацию в сфере социума."
        
    previous = get_user_inline_question_texts(user_id, topic)
    previous_text = "\n".join(f"- {q}" for q in previous)

    prompt = (
        f"Сгенерируй 16 новых астрологических вопросов (без нумерации), которые могли бы заинтересовать пользователя, "+ promt_question_theme +
        f"основываясь на его личных и астрологических данных:\n\n"
        f"Имя: {name}\n"
        f"Пол: {gender}\n"
        f"Дата рождения: {birthdate}\n"
        f"Знак зодиака: {zodiac}\n"
        f"Восточный знак: {chinese}\n"
        f"Натальная карта:\n{planets}\n\n"
        f"Ранее заданные вопросы:\n{previous_text}\n\n"
        f"Сформулируй 16 уникальных вопросов. Пиши каждый вопрос с новой строки, без нумерации, без тире, без точек, без маркеров. Просто текст вопроса. В вопросах обращайся на 'ты', как к другу."
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text="🌌 Подожди немного… Формируются уникальные вопросы по твоей натальной карте…" ,
        reply_markup=ReplyKeyboardRemove()
    )

    payload = {
        "model": "gemma3:latest",
        "prompt": prompt,
        "stream": False,
        "temperature": 0.4,
        "system": "Ты профессиональный психолог. Твоя задача — написать 16 вопросов без нумерации, без точек, без тире. Просто текст вопроса. Не начинай ни один вопрос с числа или маркера. Обращайся на 'ты'."
    }

    try:
        async with httpx.AsyncClient(timeout=500.0, trust_env=False) as client:
            response = await client.post("http://localhost:11434/api/generate", json=payload)
            questions_text = response.json().get("response", "")

        questions = [q.strip("-• ").strip() for q in questions_text.strip().split("\n") if q.strip()]
        if not questions:
            return

        inline_id = create_new_inline_id()
        conn = get_pg_connection()
        with conn:
            cursor = conn.cursor()
            for index, q in enumerate(questions[:16]):
                cursor.execute("""
                    INSERT INTO inline_questions (inline_id, order_index, question, user_id, gender, prompt_id, topic)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (inline_id, index, q, user_id, gender, prompt_id, topic))

        context.user_data["current_inline_id"] = inline_id

    except Exception as e:
        logging.error(f"Ошибка генерации inline-вопросов: {e}")



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
    
    if update.message:
        user_answer = update.message.text.strip()
    elif update.callback_query and update.callback_query.data:
        user_answer = update.callback_query.data.strip()
    else:
        logging.warning("❗ Нет текста ответа для user_wait_answer.")
        return WAIT_ANSWER
    
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
                max_date=datetime.now() + relativedelta(years=1)
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
        
        if "LINK" in options_str:
            
            user_id = update.effective_user.id
            link = create_portrait_invite(user_id)
            markup = build_share_button(link)

            await update.message.reply_text(
                f"🔗 Готово! Вот твоя персональная ссылка, которую можно отправить другу:\n\n{link}",
                reply_markup=markup
            )

            # Пропускаем сохранение ответа и сразу переходим к следующему шагу
            context.user_data["question_step"] += 1

            # Проверка: если это был последний шаг
            if context.user_data["question_step"] >= len(get_questions(context.user_data["chain_id"])):
                await generate_forecasts_from_chain(update, context)
                return ConversationHandler.END

            return await ask_question(update, context)

    
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
        zodiac, chinese = get_zodiac_and_chinese_sign(user_answer)
        context.user_data["bdate_zodiac"] = zodiac
        context.user_data["bdate_chinese"] = chinese
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
    
    if options_str and any(opt in options_str for opt in ["BIRTHDT"]):
        zodiac, chinese = get_zodiac_and_chinese_sign(user_answer)
        context.user_data["bdate_zodiac"] = zodiac
        context.user_data["bdate_chinese"] = chinese


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
        
        # Специальная защита: если последний вопрос пришёл от callback_query (inline-кнопка), а не message
        if not update.message and update.callback_query:
            update.message = update.callback_query.message  # подменим, чтобы было откуда брать chat_id
        
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
        "prompt": f"Определи пол имени «{name}». Ответь только «мужской» или «женский».",
        "stream": False,
        "temperature": 0.4,
        "system": "Отвечай строго одним словом: мужской или женский."
    }

    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.post("http://localhost:11434/api/generate", json=payload)
        result = response.json().get("response", "").strip().lower()
        return "женский" if "жен" in result else "мужской"

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

async def process_portrait_invite(start_param, user_id, bot, update, context):
    #"""
    #Обрабатывает инвайт-ссылку с токеном формата 'portrait_xxx'.
    #Начисляет бонус 250 АстроКоинов пригласившему, если ссылка не была использована.
    #"""

    token = start_param.strip()
    print("Обработка начисления бонуса")
    
    user_id = update.effective_user.id
    user_data = load_user_data(user_id)




    conn = get_pg_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT creator_id, used FROM portrait_links WHERE token = %s",
                    (token,)
                )
                row = cursor.fetchone()

                if not row:
                    return

                creator_id, used = row

                if used or creator_id == user_id:
                    return

                # Обновляем статус ссылки
                cursor.execute(
                    "UPDATE portrait_links SET used = true, used_by_user_id = %s, used_at = NOW() WHERE token = %s",
                    (user_id, token)
                )

                if user_data and user_data.get("birthdate") and user_data.get("name") and user_data.get("birthtime"):
                # Пользователь уже зарегистрирован — не запускаем цепочку
                    # 📬 Уведомляем пригласившего
                    await bot.send_message(
                        chat_id=creator_id,
                        text=(
                            "🎉 Твоим приглашением воспользовался уже зарегистрированный пользователь StarTwins!\n"
                            f"К сожалению, в таком случае бонус не предоставляется.\n"
                            f"Но мы очень признательны тебе за пересылку приглашения. Может у тебя еще есть друзья, которые еще не с нами?"
                        )
                    )
                    await update.message.reply_text("Ты прошел по ссылке с приглашением, но ты уже и так с нами, чему мы безмерно рады!🌟", 
                                                    reply_markup=menu_keyboard)
                    return ConversationHandler.END
                
                # Начисляем 100 АстроКоинов
                bonus_amount = 100
                update_user_balance(creator_id, bonus_amount)

                # ⬇️ Записываем транзакцию
                cursor.execute("""
                    INSERT INTO coin_transactions (user_id, coin_amount, price_rub, package_id)
                    VALUES (%s, %s, %s, %s)
                """, (creator_id, bonus_amount, 0, 1))

                # Получаем новый баланс
                new_balance = get_user_balance(creator_id)

    finally:
        conn.close()

    # 📬 Уведомляем пригласившего
    await bot.send_message(
        chat_id=creator_id,
        text=(
            "🎉 По твоему приглашению зарегистрировался пользователь!\n"
            f"Начислен бонус +{bonus_amount} АстроКоинов. 💰\n"
            f"Твой текущий баланс: {new_balance} АстроКоинов 🪙."
        )
    )
    


    #if user_data and user_data.get("birthdate") and user_data.get("name") and user_data.get("birthtime"):
    #    # Пользователь уже зарегистрирован — сразу запускаем цепочку
    #    context.user_data.update(user_data)
    #    context.user_data["chain_id"] = 1
    #    context.user_data["question_step"] = 0
    #    context.user_data["event_answers"] = {}

        # Сохраняем текущий chat_id в БД
    #    user_data["chat_id"] = update.effective_chat.id
    #    save_user_data(user_id, user_data)

    #    return await ask_question(update, context)

    # Новый пользователь — начинаем с имени
    await update.message.reply_text("🌟 Давай познакомимся. Напиши своё имя:")
    context.user_data["from_compat"] = True
    return ASK_NAME

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    args = context.args
    if args and args[0].startswith("compat_"):
        token = args[0].split("compat_")[1]
        return await handle_compat_start(update, context, token)

    # ✨ Обработка инвайт-ссылки "Звёздного двойника"
    if args and args[0].startswith("portrait_"):
        token = args[0]  # не отрезаем префикс, он нужен
        #отладка
        print(token)
        return await process_portrait_invite(token, update.effective_user.id, context.bot, update, context)
    
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
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

    # Устанавливаем значения только если уже есть имя и дата рождения (то есть не регистрация)
    if "name" in context.user_data and "birthdate" and "birthplace" in context.user_data:
        context.user_data.setdefault("question_step", 0)
        context.user_data.setdefault("event_answers", {})
        #context.user_data.setdefault("chain_id", 1)
        #context.user_data.setdefault("question_chain_id", 1)


    # Вычисляем планеты, если есть дата рождения и нет расчётов
    if "birthdate" in context.user_data and "user_planets_info" not in context.user_data:
        context.user_data["user_planets_info"] = get_astrology_text_for_date(
            context.user_data["birthdate"],
            time_str=context.user_data.get("birthtime", "12:00"),
            mode="model",
            tz_offset=context.user_data.get("tz_offset", 0)
        )

    # Если пользователь зарегистрирован — показываем меню
    if "name" in context.user_data and "birthdate" and "birthplace" in context.user_data:
        await message.reply_text(
            "👋 Твои данные загружены успешно. Выбери действие из меню:",
            reply_markup=menu_keyboard,
        )
        return ConversationHandler.END

    # Иначе — это новый пользователь, просим ввести имя
    await message.reply_text(
        "🌟 Добро пожаловать в StarTwins!\n\nДавай познакомимся, напиши своё имя:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_NAME




# Очистка данных
async def reset_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем сообщение из message или callback_query
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        logging.error("❗ Не удалось найти message для reset_user_data.")
        return ConversationHandler.END

    # Ответ пользователю
    await message.reply_text(
        "⚠️ Ты уверен, что хочешь изменить личные данные?\nВся история общения будет удалена, баланс АстроКоинов будет обнулён.",
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
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Удаление всех данных пользователя
        cursor.execute("DELETE FROM user_conversations WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM forecasts WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

        # 💬 Удаление inline-вопросов и логов
        cursor.execute("DELETE FROM user_inline_logs WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM inline_questions WHERE user_id = %s", (user_id,))
        
        conn.commit()
        conn.close()

        context.user_data.clear()
        context.user_data["chat_id"] = update.effective_chat.id

        await update.message.reply_text(
            "🗑️ Все данные удалены. Введи своё имя:",
            reply_markup=ReplyKeyboardRemove()
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
        f"Спасибо, {name}. Твой пол определён как {gender}."
    )

    # Показываем календарь для даты рождения
    context.user_data["current_options_str"] = "BIRTHDT"
    context.user_data["calendar_center_year"] = 1990
    calendar = SimpleCalendar(
        min_date=datetime(1925, 1, 1),
        max_date=datetime(2015, 12, 31),
        center_year=1990
    )
    await update.message.reply_text(
        "📅 Укажи дату рождения, выбрав её из календаря:",
        reply_markup=calendar.build_year_selection()
    )
    return context.bot_data["ASK_BIRTHPLACE"]



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


async def detect_timezone_offset(place: str) -> int:
    payload = {
        "model": "gemma3:latest",
        "prompt": f"Какой часовой пояс (UTC+N) у города или населённого пункта «{place}»? Ответь числом от -12 до +14.",
        "stream": False,
        "temperature": 0.4,
        "system": "Ответь строго числом — смещением в часах от UTC, без текста."
    }

    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.post("http://localhost:11434/api/generate", json=payload)
        try:
            offset = int(response.json().get("response", "0").strip())
            return max(-12, min(14, offset))
        except ValueError:
            return 0

async def get_birthplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    place = update.message.text.strip()
    context.user_data["birthplace"] = place

    # Определяем часовой сдвиг через модель
    tz_offset = await detect_timezone_offset(place)
    context.user_data["tz_offset"] = tz_offset

    await update.message.reply_text(
        f"Спасибо! Место рождения сохранено. "
        f"Часовой сдвиг в месте рождения: UTC{'+' if tz_offset >= 0 else ''}{tz_offset}\n\n"
        f"🕰️ Укажите время рождения (в формате ЧЧ:ММ), например 14:30.\n"
        f"Если не знаете точное время — нажмите «Не знаю».",
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Не знаю", callback_data="birthtime_unknown")]
        ])
    )


    return ASK_BIRTHTIME



# Прогноз на завтра
async def forecast_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    tomorrow = datetime.now() + timedelta(days=1)
    context.user_data["forecast_date"] = tomorrow.strftime("%d.%m.%Y")
    context.user_data["chain_id"] = 10
    context.user_data["button_id"] = 100
    # Начинаем задавать вопросы, начиная с первого
    context.user_data["question_step"] = 0  # Сохраняем шаг для начала с первого вопроса
    return await ask_question(update, context)  # Запускаем цепочку вопросов


# VIP-дата
async def ask_vip_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем кнопки из базы данных
    buttons = get_dynamic_menu_buttons(2)
    context.user_data["forecast_date"] = ""

    if not buttons:
        await update.message.reply_text("Ошибка! Нет доступных кнопок.")
        return ConversationHandler.END

    # Создаем клавиатуру с кнопками
    keyboard = create_dynamic_keyboard(buttons)

    # Отправляем клавиатуру с кнопками
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

    return ConversationHandler.END



# История и навигация
async def astro_stages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем кнопки из базы данных
    #buttons = get_dynamic_menu_buttons(4)

    from astrology_utils import get_pg_connection

    user_id = update.effective_user.id
    context.user_data["forecast_date"] = ""
    # Получаем все этапы
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, button_id FROM astro_psychology_stages ORDER BY position")
    stages = cursor.fetchall()

    # Получаем текущий прогресс пользователя
    cursor.execute("SELECT current_stage_id FROM user_astro_progress WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    current_stage_id = row[0] if row else None

    conn.close()

    context.user_data["current_stage_id"] =  current_stage_id
    # Формируем отображение прогресса
    lines = [
    "🌌 *Ты на пороге глубокого самоисследования.*",
    "Каждый этап Астро-Психологии раскрывает важные грани твоей личности.",
    "Пройдя весь путь, ты получишь максимально точный и целостный астро-психологический портрет,",
    "основанный на твоих ответах, астрологических данных и скрытых закономерностях.",
    "",
    "*Твой путь в Астро-Психологии:*"
    ]

    buttons = []
    next_stage = None
    passed = True

    for sid, title, bid in stages:
        if current_stage_id is None or sid > current_stage_id:
            if next_stage is None:
                next_stage = sid
                lines.append(f"🟡 *{title}* — этап открыт для прохождения")
                buttons = get_dynamic_menu_buttons(bid)
            else:
                lines.append(f"🔒 {title}")
            passed = False
        else:
            lines.append(f"✅ {title}")

    if passed:
        lines.append("\n🎉 Ты прошёл все этапы! Поздравляем с достижением глубины самопонимания ✨")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown"
    )

    if not buttons:
        #await update.message.reply_text("Ошибка! Нет доступных кнопок.")
        return ConversationHandler.END

    # Создаем клавиатуру с кнопками
    keyboard = create_dynamic_keyboard(buttons)
    # Отправляем клавиатуру с кнопками
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

    return ConversationHandler.END



# Меню и отмена
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query and update.callback_query.message)
    if message:
        
        await message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)

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

    keyboard.append([KeyboardButton("📋 Главное меню")])
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

# Функция для получения chain_id кнопки из базы данных
def get_button_id_for_button(button_action):
    print("Button Action")
    print((button_action))
    
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT id FROM dynamic_menu
    WHERE button_action = %s
    """,
        (button_action,),
    )

    result = cursor.fetchone()
    conn.close()
    print("get_button_id_for_button, button_id")
    print(result)
    if result:
        return result[0]  # Возвращаем найденный chain_id
    return None  # Если id не найден, возвращаем None



# Обработчик для нажатия кнопки динамического меню
async def handle_dynamic_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    #Обработчик для нажатия кнопки динамического меню. Получает chain_id кнопки, обновляет его в user_data,
    #если chain_id не найден, то выводит ошибку, иначе - запускает цепочку вопросов.
    
    
    
    button_action = update.message.text.strip()  # Получаем действие кнопки
    print(f"Пользователь выбрал кнопку с действием: {button_action}")  # Логирование

    # Получаем chain_id для этой кнопки
    if button_action == "📋 Главное меню":
        return await show_menu(update, context)

    
    
    chain_id = get_chain_id_for_button(button_action)
    print("handle_dynamic_button, chain_id, button_action")
    print(chain_id)
    print(button_action)
    
    button_id = get_button_id_for_button(button_action)
    

    if chain_id is None:
        await update.message.reply_text(
            "Ошибка! Для этой кнопки не настроена цепочка вопросов."
        )
        return ConversationHandler.END

    # Обновляем chain_id в user_data
    context.user_data["chain_id"] = chain_id
    context.user_data["button_id"] = button_id
    
    # Начинаем задавать вопросы, начиная с первого
    context.user_data["question_step"] = 0  # Сохраняем шаг для начала с первого вопроса
    return await ask_question(update, context)  # Запускаем цепочку вопросов

async def generate_detailed_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt, tone, temperature):
    user_id = update.effective_user.id

    # Универсальный способ получить message для reply
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        logging.warning("Не удалось получить сообщение для ответа.")
        return

    # Подстановка переменных
    prompt = replace_variables_in_prompt(prompt, context)
    

    # Скрыть клавиатуру
    await message.reply_text(
        "Запрашиваю прогноз. Пожалуйста, немного подождите...",
        reply_markup=ReplyKeyboardRemove()
    )

    # Получаем последние 5 записей контекста (если есть) временно отключено
    #conversation_context = get_conversation_context(user_id)
    conversation_context = '[]'
    
    payload = {
        "model": "gemma3:latest",
        "prompt": prompt,
        "stream": True,
        "temperature": temperature,
        "system": tone
    }

    if conversation_context != '[]':
        payload["context"] = conversation_context

    logging.info(f"[payload] {payload}")

    typing_msg = await message.reply_text("…")

    astro_text = ""
    buffer = ""
    first = True
    timeout = httpx.Timeout(500.0) 
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream("POST", "http://localhost:11434/api/generate", json=payload) as response:
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    part = json.loads(line)
                    chunk = part.get("response", "")
                    if not chunk:
                        continue

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
                                    delay = len(clean_para.split()) * 0
                                    await asyncio.sleep(delay)
                                    await typing_msg.edit_text(decorated)
                                    
                                typing_msg = await context.bot.send_message(
                                    chat_id=update.effective_chat.id, text="…"
                                )
                                    
                        buffer = parts[-1]
            try:
                await typing_msg.delete()
            except Exception:
                pass
        last_para = buffer.strip()
        if last_para:
            decorated = decorate_with_emojis(last_para)
            delay = len(last_para.split()) * 0
            await asyncio.sleep(delay)

            try:
                await typing_msg.edit_text(decorated)
            except Exception:
                pass  # Игнорируем ошибку, если не удалось отредактировать сообщение

        # Сохраняем результат в БД
        conn = get_pg_connection()
        cursor = conn.cursor()

        aspect = context.user_data.get("aspect", "Аспект не определен")
        forecast_date_str = context.user_data.get("forecast_date", "")
        try:
            forecast_date = datetime.strptime(forecast_date_str, "%d.%m.%Y").date()
        except:
            forecast_date = datetime.today().date()

        generate_date = datetime.today().date()
        logging.info(f"💾 Сохраняю прогноз: user_id={user_id}, date={forecast_date}, aspect={aspect}")
        cursor.execute(
            """
            INSERT INTO forecasts (user_id, forecast_date, aspect, forecast_text, generate_date)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (
                user_id,
                forecast_date,
                aspect,
                astro_text,
                generate_date,
            ),
        )
        
        
        conn.commit()
        conn.close()

        # Обновляем контекст
        new_context = part.get("context")
        if new_context:
            save_conversation_context(user_id, new_context)

    except Exception as e:
        logging.error(f"❌ Ошибка при генерации прогноза: {e}")
        await message.reply_text("⚠️ Произошла ошибка при генерации прогноза.")




# Обработчик кнопки "Прогноз на событие"
async def detailed_vip_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    context.user_data["aspect"]="Прогноз на событие"
    
    
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

    # Преобразуем опции, исключая служебные типа LINK
    try:
        raw_options = json.loads(options_str) if options_str else []
        options = [opt for opt in raw_options if opt not in {"LINK", "CONTACT"}]
    except json.JSONDecodeError:
        raw_options = []
        options = []

    # Преобразуем позиции
    try:
        options_positions = json.loads(options_position_str) if options_position_str else []
    except json.JSONDecodeError:
        options_positions = []

    logging.info(f"Текущий вопрос: {question_text}")
    logging.info(f"Опции: {options}")
    logging.info(f"Позиции: {options_positions}")

    # LINK — показать вопрос и сразу отправить ссылку, затем перейти к следующему шагу
    if "LINK" in raw_options:
        from invite_links import create_portrait_invite, build_share_button

        user_id = update.effective_user.id
        link = create_portrait_invite(user_id)
        markup = build_share_button(link)

        await message.reply_text(
            question_text,
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📋 Главное меню")]], resize_keyboard=True)
        )

        await message.reply_text(
            f"🔗 Ваша персональная ссылка:\n{link}",
            reply_markup=markup
        )

        context.user_data["question_step"] += 1
        questions = get_questions(context.user_data["chain_id"])
        if context.user_data["question_step"] >= len(questions):
            await generate_forecasts_from_chain(update, context)
            return ConversationHandler.END

        return await ask_question(update, context)

    if "CONTACT" in raw_options:
        
        await message.reply_text(
            question_text,
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📋 Главное меню")]], resize_keyboard=True)
        )

        token = str(uuid4())
        initiator_id = update.effective_user.id
        name = context.user_data.get("name", "Пользователь")
        
        if "user_planets_info" not in context.user_data:
            context.user_data["user_planets_info"] = get_astrology_text_for_date(
                context.user_data.get("birthdate"),
                time_str=context.user_data.get("birthtime", "12:00"),
                mode="model",
                tz_offset=context.user_data.get("tz_offset", 0)
            )
        
        # 🔧 Сохраняем полные данные инициатора, а не только ответы
        initiator_data = {
            "name": context.user_data.get("name"),
            "birthdate": context.user_data.get("birthdate"),
            "gender": context.user_data.get("gender"),
            "zodiac": context.user_data.get("zodiac"),
            "chinese_year": context.user_data.get("chinese_year"),
            "user_planets_info": context.user_data.get("user_planets_info"),
            "event_answers": context.user_data.get("event_answers", {}),
            "chain_id": context.user_data.get("chain_id", 100)
        }
        answers_json = json.dumps(initiator_data, ensure_ascii=False)

        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO compatibility_requests (token, initiator_id, initiator_name, initiator_data, compat_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (token, initiator_id, name, answers_json,'romantic'))
        conn.commit()
        conn.close()

        bot_username = context.bot.username
        compat_link = f"https://t.me/{bot_username}?start=compat_{token}"

        text = (
            f"💞 Пользователь StarTwins *{name}* хочет узнать, насколько вы совместимы астрологически!\n\n"
            f"📌 Пройди короткий опрос, астрологический прогноз увидит только отправитель.\n\n"
            f"Нажми на кнопку ниже, чтобы начать анализ:"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔮 Пройти совместимость", url=compat_link)]
        ])

        await message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
        await show_menu(update, context)
        return ConversationHandler.END

    if "FRIENDCON" in raw_options:
        
        await message.reply_text(
            question_text,
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📋 Главное меню")]], resize_keyboard=True)
        )

        token = str(uuid4())
        initiator_id = update.effective_user.id
        name = context.user_data.get("name", "Пользователь")
        
        if "user_planets_info" not in context.user_data:
            context.user_data["user_planets_info"] = get_astrology_text_for_date(
                context.user_data.get("birthdate"),
                time_str=context.user_data.get("birthtime", "12:00"),
                mode="model",
                tz_offset=context.user_data.get("tz_offset", 0)
            )
        
        # 🔧 Сохраняем полные данные инициатора, а не только ответы
        initiator_data = {
            "name": context.user_data.get("name"),
            "birthdate": context.user_data.get("birthdate"),
            "gender": context.user_data.get("gender"),
            "zodiac": context.user_data.get("zodiac"),
            "chinese_year": context.user_data.get("chinese_year"),
            "user_planets_info": context.user_data.get("user_planets_info"),
            "event_answers": context.user_data.get("event_answers", {}),
            "chain_id": context.user_data.get("chain_id", 102)
        }
        answers_json = json.dumps(initiator_data, ensure_ascii=False)

        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO compatibility_requests (token, initiator_id, initiator_name, initiator_data, compat_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (token, initiator_id, name, answers_json,'friendship'))
        conn.commit()
        conn.close()

        bot_username = context.bot.username
        compat_link = f"https://t.me/{bot_username}?start=compat_{token}"

        text = (
            f"💞 Пользователь StarTwins *{name}* хочет узнать, насколько вы совместимы астрологически!\n\n"
            f"📌 Пройди короткий опрос, астрологический прогноз увидит только отправитель.\n\n"
            f"Нажми на кнопку ниже, чтобы начать анализ:"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔮 Пройти совместимость", url=compat_link)]
        ])

        await message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
        await show_menu(update, context)
        return ConversationHandler.END

    
    if "INLINEQ" in raw_options:
        try:
            inline_id = int(options[1])  # формат: ["INLINEQ", "101"]
        except:
            await message.reply_text("⚠️ Неверный формат INLINEQ.")
            return ConversationHandler.END

        topic = int(context.user_data.get("topic"))
        all_questions = get_inline_questions(inline_id,topic)
        asked = get_user_asked_inline_questions(update.effective_user.id, inline_id, topic)
        new_questions = [q for q in all_questions if q not in asked]

        if not new_questions:
            await message.reply_text("⭐ Все вопросы уже были заданы.")
            return ConversationHandler.END

        for index, q in enumerate(new_questions):
            await message.reply_text(
                q,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Задать вопрос", callback_data=f"inline_ask::{inline_id}::{index}")]
                ])
            )


        return ConversationHandler.END


    # Ключевые слова — запуск календаря
    special_inputs = {"DATE", "PASTDT", "BIRTHDT"}
    if any(opt in special_inputs for opt in raw_options):
        context.user_data["current_options_str"] = options_str

        calendar = None
        if "DATE" in options_str:
            calendar = SimpleCalendar(min_date=datetime.now() + timedelta(days=1), max_date=datetime.now() + relativedelta(years=1))
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
    context.user_data["__tariff_confirmed"] = False
    
    if not chain_id:
        await update.message.reply_text("Ошибка! Не указан chain_id.")
        return ConversationHandler.END
    
    # Проверка, если это прогноз на завтра
    if int(chain_id) == 10:
        # Сформировать аспект
        answers = context.user_data.get("event_answers", {})
        logging.info(f"[🔍 event_answers] {answers}")
        answer_0 = answers.get("0") or answers.get(0, "")

        context.user_data["aspect"] = f"завтра, {answer_0}"

        
        forecast_date_str = context.user_data.get("forecast_date", "")
        try:
            forecast_date = datetime.strptime(forecast_date_str, "%d.%m.%Y").date()
        except:
            forecast_date = datetime.today().date()

        # Проверка в базе, есть ли прогноз
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT forecast_text FROM forecasts
            WHERE user_id = %s AND forecast_date = %s AND aspect = %s
        """, (update.effective_user.id, forecast_date, context.user_data["aspect"]))
        row = cursor.fetchone()
        conn.close()

        if row:
            decorated = decorate_with_emojis(row[0])
            await update.message.reply_text(f"📆 Прогноз на завтра:\n\n{decorated}")
            await update.message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)
            return ConversationHandler.END

    
# При анализе совместимости с контактом
    if int(chain_id) == 101:
        prompts = get_question_chain_prompts(100)
        result_text = ""

        for prompt, tone, temperature, _ in prompts:
            prompt = replace_variables_in_prompt(prompt, context)
            result_text += prompt + "\n"  # или сгенерированный ответ

        await process_compatibility_result(update, context, result_text)
        
        # Благодарность и завершение
        message = update.message or (update.callback_query and update.callback_query.message)        
        if message:
                await message.reply_text(
                "🙏 Спасибо за участие!\n\n"
                "🔮 Твой анализ совместимости завершён, и он уже отправлен пользователю, от которого тебе пришла ссылка.\n\n"
                "✨ Добро пожаловать в сервис *АстроТвинз* — здесь ты можешь получить персональные прогнозы, пройти тесты и узнать больше о себе.",
                parse_mode='Markdown',
                reply_markup=menu_keyboard
            )       
        user_id = update.effective_user.id
        if add_welcome_bonus_if_needed(user_id):
            update_user_balance(user_id,100)
            await message.reply_text("Спасибо за регистрацию! Тебе начислен привественный бонус 100 АстроКоинов 🪙")
        
        return ConversationHandler.END  # ❗ важный return, чтобы не шли дальше
    
# При анализе совместимости с контактом
    if int(chain_id) == 103:
        prompts = get_question_chain_prompts(102)
        result_text = ""

        for prompt, tone, temperature, _ in prompts:
            prompt = replace_variables_in_prompt(prompt, context)
            result_text += prompt + "\n"  # или сгенерированный ответ

        await process_compatibility_result(update, context, result_text)
        
        # Благодарность и завершение
        message = update.message or (update.callback_query and update.callback_query.message)        
        if message:
                await message.reply_text(
                "🙏 Спасибо за участие!\n\n"
                "🔮 Твой анализ совместимости завершён, и он уже отправлен пользователю, от которого тебе пришла ссылка.\n\n"
                "✨ Добро пожаловать в сервис *АстроТвинз* — здесь ты можешь получить персональные прогнозы, пройти тесты и узнать больше о себе.",
                parse_mode='Markdown',
                reply_markup=menu_keyboard
            )       
        user_id = update.effective_user.id
        
        if add_welcome_bonus_if_needed(user_id):
            update_user_balance(user_id,100)
            await message.reply_text("Спасибо за регистрацию! Тебе начислен привественный бонус 100 АстроКоинов 🪙")
        
        return ConversationHandler.END  # ❗ важный return, чтобы не шли дальше

    # 📊 Ищем дату из вопроса с опцией [DATE]
    forecast_date_str = context.user_data.get("forecast_date")

    if not forecast_date_str:
        questions = get_questions(chain_id)
        for idx, (_text, options, *_rest) in enumerate(questions):
            if options and "DATE" in options:
                answer = context.user_data.get("event_answers", {}).get(str(idx)) or context.user_data.get("event_answers", {}).get(idx)
                if answer:
                    forecast_date_str = answer
                    context.user_data["forecast_date"]=forecast_date_str
                    break

    if forecast_date_str:
        try:
            buf = generate_chart_image(
                birthdate=forecast_date_str,
                birthtime="12:00",
                tz_offset=context.user_data.get("tz_offset", 0),
                user_name=f"Положение планет на {forecast_date_str}"
            )
            message = update.message or (update.callback_query and update.callback_query.message)
            if message:
                await message.reply_photo(photo=buf, caption=f"🌌 Положение планет на {forecast_date_str}")
        except Exception as e:
            logging.warning(f"⚠️ Ошибка при генерации изображения положения планет: {e}")




    # Получаем цепочку значений prompt, tone, temperature из базы данных
    context.user_data["__prompts_to_generate"] = get_question_chain_prompts(chain_id)
    return await run_prompt_step(update, context)

def is_astro_psychology_chain(chain_id):
    conn = get_pg_connection()
    cursor = conn.cursor()
    
    # Получаем id кнопки из dynamic_menu по chain_id
    cursor.execute("SELECT menu_chain_id FROM dynamic_menu WHERE chain_id = %s", (chain_id,))
    button = cursor.fetchone()
    
    if not button:
        conn.close()
        return False
    
    button_id = button[0]

    # Проверяем, есть ли эта кнопка в astro_psychology_stages
    cursor.execute("SELECT 1 FROM astro_psychology_stages WHERE button_id = %s", (button_id,))
    result = cursor.fetchone() is not None
    
    conn.close()
    return result


async def run_prompt_step(update, context):
    prompts = context.user_data.get("__prompts_to_generate", [])
    
    if not prompts:
        chain_id = context.user_data.get("chain_id")
        # после генерации прогноза
        if is_astro_psychology_chain(chain_id):
            user_id = update.effective_user.id
            current_stage_id = context.user_data.get("current_stage_id")
            
            #Проверяем если это первый этап или прибавляем еденицу к текущему этапу для апдейта
            if current_stage_id is None:
                current_stage_id = 1
            else:
                current_stage_id = current_stage_id+1
                
            
            print(current_stage_id)
            
            conn = get_pg_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_astro_progress (user_id, current_stage_id, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET current_stage_id = EXCLUDED.current_stage_id,
                    updated_at = NOW()
            """, (user_id, current_stage_id))
            conn.commit()
            conn.close()
        
        user_id = update.effective_user.id
        token = create_portrait_invite(user_id)       
        markup = build_share_button(token)
        await update.effective_message.reply_text(
            "🔔 Прогноз завершён! 🔔 — а хочешь узнать о себе ещё больше? ✨ "
            "Пригласи своего друга зарегистрироваться в сервисе ✨\"Звёздный двойник\" 🪞 и получи 100 АстроКоинов 🪙 "
            "Используй их, например, в фунции \"📅Прогноз на событие\" чтобы узнать, какой образ подойдёт для важного дня.",
            reply_markup=markup
        )
        
        await update.effective_message.reply_text(
            "Ты готов продолжить погружение во Вселенную? Выбери пункт меню:",
            reply_markup=menu_keyboard,
        )
        
        return ConversationHandler.END

    prompt, tone, temperature, _ = prompts.pop(0)
    
    #отладка
    print("run_prompts "+str(prompt))
    
    async def do_forecast():
        await generate_detailed_forecast(update, context, prompt, tone, temperature)
        await run_prompt_step(update, context)  # запускаем следующий
    
    # 👉 Проверка: тариф уже подтверждён?
    if context.user_data.get("__tariff_confirmed", False):
        return await do_forecast()
    
    # 👉 Иначе — подтверждаем и помечаем как подтверждённый
    async def wrapped_forecast():
        context.user_data["__tariff_confirmed"] = True
        return await do_forecast()

    return await confirm_tariff_and_generate(update, context, wrapped_forecast)

#Функция пригласи друга
async def inlinequery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[inlinequery] получен запрос: {update.inline_query.query}")
    query = update.inline_query.query
    if query.startswith("portrait_"):
        invite_link = f"https://t.me/{BOT_USERNAME}?start={query}"
        results = [
            InlineQueryResultArticle(
                id=query,
                title="Пригласи друга в Звёздного двойника 🌟",
                input_message_content=InputTextMessageContent(
                f"🌠 Исследуй себя и найди своего звёздного двойника в истории\nЖми 👉 {invite_link}"
                ),
                description="Нажми, чтобы отправить другу приглашение"
            )
        ]
        await update.inline_query.answer(results, cache_time=1)



def replace_variables_in_prompt(prompt, context):
    

    user_id = context.user_data.get("user_id")
    print(context.user_data.get("user_id")) #отладка

    # Загрузка данных пользователя
    user_data = load_user_data(user_id)
    if user_data:
        user_data.update(user_data)
        
    print(context.user_data.get("name", "")) #отладка
    
    if (
        "user_planets_info" not in context.user_data
        and context.user_data.get("birthdate")
    ):
        context.user_data["user_planets_info"] = get_astrology_text_for_date(
            context.user_data["birthdate"],
            time_str=context.user_data.get("birthtime", "12:00"),
            mode="model",
            tz_offset=context.user_data.get("tz_offset", 0) or 0
        )
    
    chain_id = context.user_data.get("chain_id")
    
    if (
        "compat_token" in context.user_data and
        any(s in prompt for s in ["{initiator_", "{responder_}"])
    ):
        load_compat_variables(context, context.user_data["compat_token"])

    # Всегда собираем event_questions, если есть chain_id
    if chain_id:
        collect_questions_for_chain(context, chain_id)

    logging.info(f"Event Questions: {context.user_data.get('event_questions')}")
    



    # --- Стандартные переменные ---
    variables = {
        "{name}": context.user_data.get("name", ""),
        "{gender}": context.user_data.get("gender", ""),
        "{forecast_date}": context.user_data.get("forecast_date", ""),
        "{bdate_zodiac}": context.user_data.get("bdate_zodiac", ""),
        "{bdate_chinese}": context.user_data.get("bdate_chinese", ""),
        "{user_planets_info}": context.user_data.get("user_planets_info", ""),
        "{INLINEQ}": str(context.user_data.get("INLINEQ") or ""),
        "{currentdt}": datetime.now().strftime("%d.%m.%Y")
    }

    # --- Подставляем ТОЛЬКО если явно задано как регистрация ---
    if context.user_data.get("birthdate"):
        variables["{birthdate}"] = context.user_data.get("birthdate", "")
        variables["{zodiac}"] = context.user_data.get("zodiac", "")
        variables["{chinese_year}"] = context.user_data.get("chinese_year", "")
    else:
        variables["{birthdate}"] = ""
        variables["{zodiac}"] = ""
        variables["{chinese_year}"] = ""

    # --- Планеты на forecast_date ---
    forecast_date_str = context.user_data.get("forecast_date")
    if forecast_date_str:
        if "planets_info_fd" not in context.user_data:
            planets_info_fd = get_astrology_text_for_date(
                forecast_date_str,
                time_str="12:00",
                mode="model",
                tz_offset=context.user_data.get("tz_offset", 0)
            )
            context.user_data["planets_info_fd"] = planets_info_fd

        variables["{planets_info_fd}"] = context.user_data.get("planets_info_fd", "")

        # --- Переменные инициатора ---
    variables.update({
        "{initiator_name}": context.user_data.get("initiator_name", ""),
        "{initiator_zodiac}": context.user_data.get("initiator_zodiac", ""),
        "{initiator_chinese}": context.user_data.get("initiator_chinese", ""),
        "{initiator_planets}": context.user_data.get("initiator_planets", "")
    })

    # --- Переменные респондента ---
    variables.update({
        "{responder_name}": context.user_data.get("responder_name", ""),
        "{responder_zodiac}": context.user_data.get("responder_zodiac", ""),
        "{responder_chinese}": context.user_data.get("responder_chinese", ""),
        "{responder_planets}": context.user_data.get("responder_planets", "")
    })

    # --- Вопросы и ответы респондента ---
    responder_q_keys = [k for k in context.user_data if k.startswith("responder_q_")]
    for k in responder_q_keys:
        i = k.split("_")[-1]
        q_key = f"{{responder_q_{i}}}"
        a_key = f"{{responder_a_{i}}}"
        variables[q_key] = str(context.user_data.get(k, ""))
        variables[a_key] = str(context.user_data.get(f"responder_a_{i}", ""))

    # --- Вопросы и ответы инициатора ---
    initiator_q_keys = [k for k in context.user_data if k.startswith("initiator_q_")]
    for k in initiator_q_keys:
        i = k.split("_")[-1]
        q_key = f"{{initiator_q_{i}}}"
        a_key = f"{{initiator_a_{i}}}"
        variables[q_key] = str(context.user_data.get(k, ""))
        variables[a_key] = str(context.user_data.get(f"initiator_a_{i}", ""))

        
    # --- Замена вопросов ---
    if context.user_data.get("INLINEQ") is None:
        for step in range(len(context.user_data.get("event_questions", []))):
            question = context.user_data["event_questions"][step]
            prompt = prompt.replace(f"{question_key(step)}", str(question))

    # --- Замена ответов ---
    for step, answer in context.user_data.get("event_answers", {}).items():
        prompt = prompt.replace(f"{answer_key(step)}", str(answer))

    # --- Планеты N ---
    for step in range(0, context.user_data.get("planets_info_counter", -1) + 1):
        planets_key = f"planets_info_{step}"
        planets_info = context.user_data.get(planets_key, "")
        prompt = prompt.replace(f"{{{planets_key}}}", planets_info)
    
        
    # --- Замена стандартных переменных ---
    for key, value in variables.items():
        #print отладка
        print("key="+str(key)+"  value="+str(value))
        prompt = prompt.replace(key, value)

    # ❗ Удаляем нераспознанные фигурные скобки
    prompt = prompt.replace("{", "").replace("}", "")
    return prompt


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

    # 🔁 Обработка inline-кнопки "Не знаю"
    if update.callback_query and update.callback_query.data == "birthtime_unknown":
        await update.callback_query.answer()
        birthtime = "12:00"
        message = update.callback_query.message
    elif update.message and update.message.text:
        text = update.message.text.strip()
        if text.lower() == "не знаю":
            birthtime = "12:00"
            message = update.message
        else:
            try:
                datetime.strptime(text, "%H:%M")
                birthtime = text
                message = update.message
            except ValueError:
                await update.message.reply_text(
                    "Неверный формат времени. Введите в формате ЧЧ:ММ, например 14:30, или нажмите «Не знаю»",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("Не знаю")]], resize_keyboard=True
                    )
                )
                return ASK_BIRTHTIME
    else:
        return ConversationHandler.END

    context.user_data["birthtime"] = birthtime

    await message.reply_text(
        f"Принято. Время рождения: {birthtime}",
        reply_markup=ReplyKeyboardRemove()
    )

    context.user_data["user_planets_info"] = get_astrology_text_for_date(
        context.user_data["birthdate"],
        time_str=context.user_data["birthtime"],
        mode="pretty",
        tz_offset=context.user_data.get("tz_offset", 0)
    )

    buf = generate_chart_image(
        context.user_data["birthdate"],
        birthtime,
        context.user_data.get("tz_offset", 0),
        context.user_data.get("name", "") + ", это твоя натальная карта."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Расшифровка натальной карты", callback_data="show_planet_info")]
    ])

    await message.reply_photo(photo=buf, caption="🌌 Твоя натальная карта",
        reply_markup=keyboard)

    context.user_data["chat_id"] = update.effective_chat.id
    save_user_data(user_id, context.user_data)
    save_user_astrology(user_id, context.user_data["birthdate"], birthtime, context.user_data.get("tz_offset", 0))

    if context.user_data.get("compat_chain_id"):
        context.user_data["chain_id"] = context.user_data.pop("compat_chain_id")
        context.user_data["question_step"] = 0
        context.user_data["event_answers"] = {}
        return await ask_question(update, context)

    if add_welcome_bonus_if_needed(user_id):
        update_user_balance(user_id,100)
        await message.reply_text("Спасибо за регистрацию! Тебе начислен привественный бонус 100 АстроКоинов 🪙", reply_markup=menu_keyboard)
    else:
        await message.reply_text("Рады нашей встрече! ✨💫🤗 Выбери пункт в меню:", reply_markup=menu_keyboard)

    return ConversationHandler.END



async def set_menu(application):
    # Устанавливаем свои команды
    await application.bot.set_my_commands([
        BotCommand("start", "Начать 🚀"),
        BotCommand("menu", "Главное меню 📋"),
        BotCommand("profile", "Профиль 👤"),
        #BotCommand("resetdata", "Изменить личные данные 👤⭐"),
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
        "Жми здесь: https://t.me/StarTwins_techsupport_bot . Наша команда незамедлительно поможет тебе."
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
        f"• Часовой сдвиг: {tz_offset_formatted}\n\n"
        "🔧 Хотите изменить личные данные?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да", callback_data="confirm_resetdata"),
            InlineKeyboardButton("Нет", callback_data="cancel_resetdata")
        ]
    ])

    await update.message.reply_text(profile_text, reply_markup=keyboard)

async def handle_confirm_resetdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    # Получаем сообщение из callback и вручную вызываем reset_user_data
    fake_update = Update(
        update.update_id,
        message=update.callback_query.message  # Создаём новый update с нужным message
    )

    return await reset_user_data(fake_update, context)


async def handle_cancel_resetdata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)


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
        "Сервис обновлён и теперь стал ещё лучше 🌟\n"
        "Добавлены новые функции и улучшено качество прогнозов!\n"
        "Нажмите кнопку ниже, чтобы обновиться и избежать некорректной работы сервиса."
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

async def ask_star_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["forecast_date"] = ""
    keyboard = [
        [InlineKeyboardButton("🧘 О себе", callback_data="theme::1")],
        [InlineKeyboardButton("💖 Любовь", callback_data="theme::2")],
        [InlineKeyboardButton("💼 Работа", callback_data="theme::3")],
        [InlineKeyboardButton("🌐 Социум", callback_data="theme::4")],
    ]
    await update.message.reply_text(
        "🧭 Выбери тематику вопроса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )  
    
async def handle_question_theme_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    topic = int(query.data.split("::")[1])
    context.user_data["topic"] = topic   
    user_id = update.effective_user.id
    gender = context.user_data.get("gender", "")
    context.user_data["button_id"] = 99


    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT inline_id FROM inline_questions
        WHERE user_id = %s AND topic = %s
        ORDER BY inline_id DESC LIMIT 1
    """, (user_id, topic))
    row = cursor.fetchone()
    conn.close()


    inline_id = row[0] if row else None

    if inline_id:
        all_questions = get_inline_questions(inline_id,topic)
        asked = get_user_asked_inline_questions(user_id, inline_id, topic)
        new_questions = [q for q in all_questions if q not in asked]
    else:
        new_questions = []

    if len(new_questions) <= 8:
        chat_id=update.effective_chat.id
        await generate_inline_questions_for_user(user_id, context, chat_id, topic)
        inline_id = context.user_data.get("current_inline_id")
        topic = int(query.data.split("::")[1])
        all_questions = get_inline_questions(inline_id,topic)
        asked = get_user_asked_inline_questions(user_id, inline_id, topic)
        new_questions = [q for q in all_questions if q not in asked]

    context.user_data["inline_question_page"] = 0
    context.user_data["inline_questions_available"] = new_questions
    context.user_data["current_inline_id"] = inline_id
    topic = int(context.user_data.get("topic"))
    
    return await show_next_inline_questions(update, context)

async def show_next_inline_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message

    inline_id = context.user_data['current_inline_id']
    topic = int(context.user_data.get("topic"))
    
    #отладка
    print("show_next_inline_questions, inline_id:" + str(inline_id), " topic:" + str(topic))
    
    all_questions = get_inline_questions(inline_id,topic)
    asked = get_user_asked_inline_questions(update.effective_user.id, inline_id, topic)
    new_questions = [q for q in all_questions if q not in asked]

    # получаем реальные order_index
    available_questions = [
        (i, q) for i, q in enumerate(all_questions)
        if q in new_questions
    ]

    page = context.user_data.get("inline_question_page", 0)
    start = page * 3
    end = start + 3

    if start >= len(available_questions):
        # сбрасываем на начало
        page = 0
        start = 0
        end = 3

    current_batch = available_questions[start:end]
    context.user_data["inline_question_page"] = page + 1

    for real_index, q in current_batch:
        await message.reply_text(
            q,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Задать вопрос", callback_data=f"inline_ask::{inline_id}::{real_index}")]
            ])
        )

    await message.reply_text(
        "🔁 Выбери вопрос или нажми кнопку внизу для показа других вариантов",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("Показать больше вопросов")],
                [KeyboardButton("📋 Главное меню")]
            ],
            resize_keyboard=True
        )
    )

    print("✅ Завершаю show_next_inline_questions")
    return ConversationHandler.END



async def handle_inline_button_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    print("✅ [DEBUG] handle_inline_button_forecast triggered")
    logging.info("✅ [DEBUG] handle_inline_button_forecast triggered")

    _, inline_id_str, index_str = query.data.split("::")
    inline_id = int(inline_id_str)
    question_index = int(index_str)
    topic = int(context.user_data.get("topic"))
    all_questions = get_inline_questions(inline_id,topic)
    if question_index >= len(all_questions):
        await query.message.reply_text("⚠️ Ошибка: вопрос не найден.")
        return

    question_text = all_questions[question_index]
    log_user_inline_question(update.effective_user.id, inline_id, question_text, topic)
    context.user_data["INLINEQ"] = question_text
    
    

    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prompt_id FROM inline_questions
        WHERE inline_id = %s AND order_index = %s
        LIMIT 1
    """, (inline_id, question_index))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await query.message.reply_text("⚠️ prompt_id не найден.")
        return

    prompt_id = row[0]
    context.user_data["chain_id"] = prompt_id
    
    logging.info("🔁 Начинаем generate_forecasts_from_chain")
    print(str(context.user_data["chain_id"]))
    await generate_forecasts_from_chain(update, context)
    logging.info("✅ Завершена generate_forecasts_from_chain")
    # Загружаем цепочку prompt-ов
    #prompts = get_question_chain_prompts(prompt_id)

    #print(f"👉 prompt_id: {prompt_id}")
    #print(f"👉 question_text: {question_text}")
    #print(f"👉 prompts: {prompts}")

    
    #for prompt, tone, temperature, _ in prompts:
        #updated_prompt = replace_variables_in_prompt(prompt, context)
        #print(f"🧪 Генерация прогноза по prompt: {prompt}")

        #async def do_inline_forecast():
        #    await generate_detailed_forecast(
        #        update, context,
        #        prompt=updated_prompt,
        #        tone=tone,
        #        temperature=temperature
        #   )
#            await query.message.reply_text(
#                "🔔 Прогноз завершён! Хочешь узнать о себе ещё больше? ✨ "
#                "Погрузись глубже в свою натальную карту через ✨ «Звёздный двойник» 🪞!",
#                reply_markup=menu_keyboard
#            )

    #user_id = update.effective_user.id
    #token = create_portrait_invite(user_id)       
    #markup = build_share_button(token)
    #await query.message.reply_text(
    #            "🔔 Прогноз завершён! 🔔 — а хочешь узнать о себе ещё больше? ✨ "
    #            "Пригласи своего друга зарегистрироваться в сервисе ✨\"Звёздный двойник\" 🪞 и получи 100 АстроКоинов 🪙 "
    #            "Используй их, например, в фунции \"🌠 Задай свой вопрос\" и найди новые области своего развития и самопознания.",
    #            reply_markup=markup
    #        )
            
    #await query.message.reply_text(
    #            "Ты готов продолжить погружение во Вселенную? Выбери пункт меню:",
    #            reply_markup=menu_keyboard,
    #        )


    #await confirm_tariff_and_generate(update, context, do_inline_forecast)

    return ConversationHandler.END

async def handle_compat_start(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT initiator_name, compat_type FROM compatibility_requests WHERE token = %s", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("⚠️ Ссылка недействительна.")
        return ConversationHandler.END

    initiator_name, compat_type = row
    initiator_name = initiator_name or "Пользователь"
    compat_type = compat_type or "romantic"

    # Определяем, какой chain_id запустить в зависимости от типа совместимости
    if compat_type == "friendship":
        compat_chain_id = 103
        invite_text = (
            f"{initiator_name} приглашает тебя пройти астрологический анализ совместимости!\n"
            f"📋 Ответь на вопросы, ответы не увидит инициатор, ему будут предоставлен только результатат анализа."
        )
    else:
        compat_chain_id = 101
        invite_text = (
            f"{initiator_name} приглашает тебя пройти астрологический анализ совместимости!\n"
            f"📋 Ответь на вопросы, ответы не увидит инициатор, ему будут предоставлен только результатат анализа."
        )

    await update.message.reply_text(invite_text, reply_markup=ReplyKeyboardRemove())

    context.user_data["compat_token"] = token
    context.user_data["compat_chain_id"] = compat_chain_id

    user_id = update.effective_user.id
    user_data = load_user_data(user_id)

    if user_data and user_data.get("birthdate") and user_data.get("name"):
        # Пользователь уже зарегистрирован — сразу запускаем цепочку
        context.user_data.update(user_data)
        context.user_data["chain_id"] = compat_chain_id
        context.user_data["question_step"] = 0
        context.user_data["event_answers"] = {}

        # Сохраняем текущий chat_id в БД
        user_data["chat_id"] = update.effective_chat.id
        save_user_data(user_id, user_data)

        return await ask_question(update, context)

    # Новый пользователь — начинаем с имени
    await update.message.reply_text("🌟 Давай познакомимся. Напиши своё имя:")
    context.user_data["from_compat"] = True
    return ASK_NAME


async def process_compatibility_result(update, context, result_text):
    token = context.user_data.get("compat_token")
    responder_id = update.effective_user.id

    # 🔧 Сохраняем все ключевые поля респондента, а не только ответы
    responder_data = json.dumps({
        "name": context.user_data.get("name"),
        "birthdate": context.user_data.get("birthdate"),
        "gender": context.user_data.get("gender"),
        "zodiac": context.user_data.get("zodiac"),
        "chinese_year": context.user_data.get("chinese_year"),
        "user_planets_info": context.user_data.get("user_planets_info"),
        "event_answers": context.user_data.get("event_answers", {}),
        "chain_id": context.user_data.get("chain_id", 101)
    }, ensure_ascii=False)

    if not token:
        logging.warning("⚠️ Нет токена совместимости.")
        return
    if not result_text.strip():
        logging.warning("⚠️ Пустой result_text.")
        return

    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE compatibility_requests
        SET responder_id = %s, responder_data = %s, result_text = %s, is_complete = TRUE
        WHERE token = %s
    """, (responder_id, responder_data, result_text, token))

    cursor.execute("SELECT initiator_id FROM compatibility_requests WHERE token = %s", (token,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()

    if row:
        initiator_id = row[0]
        await context.bot.send_message(
            chat_id=initiator_id,
            text="📩 По запрошенному анализу совместимости получен результат.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Посмотреть результат", callback_data=f"show_compat_result::{token}")]
            ])
        )



async def handle_show_compat_result(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    token = query.data.split("::")[1]
    
        # Получаем тип совместимости
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT compat_type, initiator_id FROM compatibility_requests WHERE token = %s", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await query.message.reply_text("⚠️ Данные по совместимости не найдены.")
        return ConversationHandler.END

    compat_type, initiator_id = row
    compat_type = compat_type or "romantic"

    await query.message.reply_text("🔮 Формирую сообщение, будет готово через несколько секунд...")

    # Очищаем контекст и указываем токен совместимости
    #context.user_data.clear() -- временно закоментированно 
    context.user_data["compat_token"] = token

    # Определяем prompt цепочку
    if compat_type == "friendship":
        prompt_chain_id = 102
    else:
        prompt_chain_id = 100

    # Генерация через встроенную функцию (внутри будет вызвана load_compat_variables)
    prompts = get_question_chain_prompts(prompt_chain_id)
    for prompt, tone, temperature, _ in prompts:
        await generate_detailed_forecast(update, context, prompt, tone, temperature)

    message = update.message or (update.callback_query and update.callback_query.message)
    if message:
        await message.reply_text("📋 Главное меню:", reply_markup=menu_keyboard)



def load_compat_variables(context, token):
    logging.info(f"🔄 Загружаем данные совместимости по токену: {token}")
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT initiator_data, responder_data FROM compatibility_requests WHERE token = %s", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        logging.warning("⚠️ Совместимость: данные по токену не найдены.")
        return

    try:
        initiator_data = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        responder_data = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    except Exception as e:
        logging.warning(f"⚠️ Ошибка при разборе JSON совместимости: {e}")
        return

    # инициатор
    context.user_data["initiator_name"] = initiator_data.get("name", "")
    context.user_data["initiator_zodiac"] = initiator_data.get("zodiac", "")
    context.user_data["initiator_chinese"] = initiator_data.get("chinese_year", "")
    context.user_data["initiator_planets"] = initiator_data.get("user_planets_info", "")

    initiator_chain_id = initiator_data.get("chain_id")
    initiator_answers = initiator_data.get("event_answers", {})
    if initiator_chain_id:
        initiator_questions = get_questions(initiator_chain_id)
        for i, (qtext, *_rest) in enumerate(initiator_questions):
            context.user_data[f"initiator_q_{i}"] = qtext
            context.user_data[f"initiator_a_{i}"] = initiator_answers.get(str(i)) or initiator_answers.get(i, "")

    # респондент
    context.user_data["responder_name"] = responder_data.get("name", "")
    context.user_data["responder_zodiac"] = responder_data.get("zodiac", "")
    context.user_data["responder_chinese"] = responder_data.get("chinese_year", "")
    context.user_data["responder_planets"] = responder_data.get("user_planets_info", "")

    responder_chain_id = responder_data.get("chain_id")
    responder_answers = responder_data.get("event_answers", {})
    if responder_chain_id:
        responder_questions = get_questions(responder_chain_id)
        for i, (qtext, *_rest) in enumerate(responder_questions):
            context.user_data[f"responder_q_{i}"] = qtext
            context.user_data[f"responder_a_{i}"] = responder_answers.get(str(i)) or responder_answers.get(i, "")

async def handle_star_twin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from astrology_module import calculate_twins_for_all_categories

    user_id = update.effective_user.id
    conn = get_pg_connection()
    cursor = conn.cursor()

    # Получаем пол пользователя
    user_gender = context.user_data.get("gender", "")
    user_gender_ru = "мужчина" if user_gender == "мужской" else "женщина"

    # Проверяем, есть ли уже двойники
    cursor.execute("SELECT COUNT(*) FROM astro_twins WHERE user_id = %s", (user_id,))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    if count == 0:
        await update.message.reply_text(
            "Подбираю звёздных двойников. Пожалуйста, немного подождите, это займёт несколько минут...",
            reply_markup=ReplyKeyboardRemove()
        )
        await calculate_twins_for_all_categories(user_id, user_gender_ru)

    # Список категорий для инлайн-кнопок
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT c.code, c.name
        FROM astro_twins at
        JOIN astro_twin_categories c ON at.twin_category_id = c.id
        WHERE at.user_id = %s
    """, (user_id,))

    categories = cursor.fetchall()
    cursor.close()
    conn.close()

    if not categories:
        await update.message.reply_text("Не удалось найти звёздных двойников.")
        return

    # Эмодзи по категориям
    emoji_map = {
        "inner_world": "🧘",
        "love": "💘",
        "work": "💼",
        "society": "🫂"
    }

    # Создание инлайн-клавиатуры с категориями и эмодзи
    keyboard = [
        [InlineKeyboardButton(f"{emoji_map.get(cat_code, '')} {cat_name}", callback_data=f"show_twins_{cat_code}")]
        for cat_code, cat_name in categories
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🌟 Выбери категорию, чтобы посмотреть звёздных двойников 🔮",
        reply_markup=reply_markup
    )

async def show_twins_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_code = query.data.replace("show_twins_", "")
    user_id = update.effective_user.id

    conn = get_pg_connection()
    cursor = conn.cursor()

    # Получаем имя категории
    cursor.execute("SELECT name FROM astro_twin_categories WHERE code = %s", (category_code,))
    row = cursor.fetchone()
    category_name = row[0] if row else category_code

    # Получаем двойников
    cursor.execute("""
        SELECT p.name_ru, at.similarity_score, at.explanation
        FROM astro_twins at
        JOIN pantheon_enriched p ON at.twin_id = p.id
        WHERE at.user_id = %s AND at.category_code = %s
        ORDER BY at.similarity_score DESC
        LIMIT 5
    """, (user_id, category_code))
    twins = cursor.fetchall()

    cursor.close()
    conn.close()

    if not twins:
        await query.message.reply_text("Нет двойников в этой категории.")
        return

    message = f"🌠 <b>Звёздные двойники в категории «{category_name}»:</b>\n\n"
    for idx, (name, score, explanation) in enumerate(twins, 1):
        message += f"{idx}. <b>{name}</b> — совпадение {round(score * 100)}%\n<i>{explanation}</i>\n\n"

    await query.message.reply_text(message.strip(), parse_mode="HTML")





# Новый callback для "Подписка и баланс"
async def show_balance_and_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from astrology_utils import get_user_balance
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Пополнить АстроКоины 🪙", callback_data="topup_coins")],
        [InlineKeyboardButton("🧾 История транзакций", callback_data='payment_history')]
    ])
    await update.message.reply_text(
        f"💰 Твой текущий баланс: {balance} АстроКоинов 🪙",
        reply_markup=keyboard
    )

# Заглушка: при нажатии "Пополнить АстроКоины" показываются пакеты
async def handle_topup_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, coin_amount, price_rub, description FROM astrocoin_packages WHERE id < 100 ORDER BY coin_amount")
    packages = cursor.fetchall()
    conn.close()

    if not packages:
        await query.message.reply_text("⚠️ Пакеты АстроКоинов временно недоступны.")
        return

    text_lines = ["💰 Выбери пакет АстроКоинов для пополнения:"]
    buttons = []

    for package_id, coin_amount, price_rub, description in packages:
        text_lines.append(f"{description} — *{price_rub} ₽*")
        buttons.append([
            InlineKeyboardButton(f"Выбрать {coin_amount} 🪙", callback_data=f"invoice::{package_id}")
        ])

    text_lines.append("\nПосле выбора ты сможешь оплатить через Telegram.")
    reply_markup = InlineKeyboardMarkup(buttons)

    await query.message.reply_text(
        "\n".join(text_lines),
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

#История оплат
async def handle_payment_history(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    conn = get_pg_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT coin_amount, price_rub, timestamp, description
        FROM coin_transactions
        WHERE user_id = %s
        ORDER BY timestamp DESC
        LIMIT 20
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        text = "🧾 История транзакций пуста."
    else:
        text = "🧾 <b>История транзакций</b>:\n\n"
            
        for coin_amount, price_rub, timestamp, description in rows:
            dt = timestamp.strftime("%d.%m.%Y %H:%M")

            if coin_amount < 0:
                text_line = f" Списание {dt} — <b>{coin_amount} АстроКоинов</b>. {description}. \n"
            else:
                text_line = f" Пополнение {dt} — <b>+{coin_amount} АстроКоинов</b> за <b>{price_rub}₽</b>. \n"

            text += text_line


    await query.edit_message_text(
        text=text,
        parse_mode='HTML',
        reply_markup=await show_menu(update, context)
    )

    return ConversationHandler.END

async def confirm_tariff_and_generate(update, context, next_step):
    from astrology_utils import get_generation_cost, get_user_balance

    user_id = update.effective_user.id
    button_id = context.user_data.get("button_id", 0)
    cost = get_generation_cost(button_id)
    balance = get_user_balance(user_id)
    
    #отладка
    print("confirm+tariff_ok "+str(button_id)+" сost "+str(cost)+"real value button_id = "+str(context.user_data.get("button_id")))
    
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        logging.error("⚠️ Не найден message для ответа в confirm_tariff_and_generate")
        return ConversationHandler.END

        # ⬇️ Скрываем обычную клавиатуру (если была)
    await message.reply_text("Проверяю баланс Астрокоинов...", reply_markup=ReplyKeyboardRemove())
    
    if cost == 0:
        return await next_step()

    if balance < cost:
        await message.reply_text(
            f"🚫 Недостаточно средств. Стоимость: {cost}, ваш баланс: {balance}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_coins")],
                [InlineKeyboardButton("📋 Главное меню", callback_data="/start")]
            ])
        )
        return ConversationHandler.END

    context.user_data["__next_step"] = next_step
    context.user_data["__tariff_cost"] = cost

    await message.reply_text(
        f"💸 С баланса спишется: {cost} АстроКоинов 🪙\nВаш баланс: {balance}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Продолжить", callback_data="confirm_tariff_ok")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="/start")]
        ])
    )

    return ConversationHandler.END


async def handle_confirm_tariff_ok(update, context):


    user_id = update.effective_user.id
    cost = context.user_data.pop("__tariff_cost", 0)
    update_user_balance(user_id, -cost)
    button_id = context.user_data.get("button_id", 0)
    
    insert_coin_transaction(user_id, -cost, 0, package_id=103, description="ID услуги: "+str(button_id))
    
    callback = context.user_data.pop("__next_step", None)
    if callback:
        await callback()
    else:
        await update.callback_query.message.reply_text("⚠️ Что-то пошло не так.")
        


async def handle_buy_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    query = update.callback_query
    await query.answer()

    try:
        _, package_id_str = query.data.split("::")
        package_id = int(package_id_str)
    except Exception:
        await query.message.reply_text("⚠️ Неверный формат запроса.")
        return

    # Получаем данные пакета
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coin_amount, price_rub FROM astrocoin_packages WHERE id = %s", (package_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await query.message.reply_text("⚠️ Пакет не найден.")
        return

    coin_amount, price_rub = row
    user_id = update.effective_user.id

    # Создание платежа
    try:
        payment = Payment.create({
            "amount": {
                "value": f"{price_rub:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{context.bot.username}?start=thank_you"
            },
            "capture": True,
            "description": f"Пополнение {coin_amount} АстроКоинов (user_id={user_id})",
            "metadata": {
                "user_id": str(user_id),
                "coin_amount": str(coin_amount),
                "package_id": str(package_id)
            }
        }, uuid.uuid4())

        payment_url = payment.confirmation.confirmation_url

        # Сохраняем для последующей сверки в вебхуке
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pending_payments (payment_id, user_id, coin_amount, price_rub, package_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (payment.id, user_id, coin_amount, price_rub, package_id))
        conn.commit()
        conn.close()

        await query.message.reply_text(
            f"💳 Для пополнения на *{coin_amount} АстроКоинов* перейдите по ссылке ниже:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Оплатить через ЮKassa", url=payment_url)]
            ])
        )

    except Exception as e:
        await query.message.reply_text("❌ Не удалось создать платёж. Попробуйте позже.")
        print(f"[ЮKassa] Ошибка создания платежа: {e}")

    async def handle_show_planet_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        planet_text = context.user_data.get("user_planets_info", "Информация о планетах недоступна.")
        await query.message.reply_text(f"🔭 Расшифровка натальной карты:\n\n{planet_text}")

        context.user_data["chain_id"] = 104
        context.user_data["question_step"] = 0
        context.user_data["event_answers"] = {}

        await generate_forecasts_from_chain(update, context)

async def handle_show_planet_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    planet_text = context.user_data.get("user_planets_info", "Информация о планетах недоступна.")
    await query.message.reply_text(f"🔭 Расшифровка натальной карты:\n\n{planet_text}")

    context.user_data["chain_id"] = 104
    context.user_data["question_step"] = 0
    context.user_data["event_answers"] = {}
    context.user_data["button_id"] = 100
    await generate_forecasts_from_chain(update, context)



# Запуск
def main():
    
    load_static_data()  # <--- Загружаем все константы из БД
    
    # --- перед запуском polling --- запускаем задачу рассылки
    async def startup_tasks():
        await send_update_notification_to_all_chats(app)
    
    app = (
        ApplicationBuilder()
        .token(os.getenv("ASTROLOG_BOT"))
        .concurrent_updates(True)
        .post_init(full_post_init)  # <<< ВОТ ТУТ ДОБАВЛЯЕМ
        .build()
    ) 
    
    # Сохраняем функции в bot_data для календаря
    app.bot_data["save_answer_to_db"] = save_answer_to_db
    app.bot_data["ask_question"] = ask_question
    app.bot_data["ASK_BIRTHPLACE"] = ASK_BIRTHPLACE
    app.bot_data["save_user_data"] = save_user_data


    # Запуск разогрева модели при старте бота
    threading.Thread(target=run_model_warmup_in_thread).start()
    
    

    # Обновляем ConversationHandler
    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(reset_user_data, pattern="^confirm_resetdata$"),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Прогноз на завтра$"), forecast_tomorrow
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Узнать о совместимости$"), ask_vip_date
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Изменить личные данные$"), reset_user_data
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Прогноз на событие$"),
                detailed_vip_forecast,
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Астро-Психология$"), astro_stages
            ),            
            MessageHandler(
                filters.Regex(r"(?i)^/resetdata$"), reset_user_data  # ← Добавь эту строку!
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Задай свой вопрос$"), ask_star_question
            ),
            MessageHandler(filters.Regex("(?i)^показать больше вопросов$"), show_next_inline_questions
            ),
            MessageHandler(
                filters.Regex(r"(?i)^.{1,2}Звёздный двойник$"), handle_star_twin_menu
            ),
            MessageHandler(filters.Regex(r"(?i)^.{1,2}Подписка и баланс$"), show_balance_and_subscription
            ), 
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, handle_dynamic_button
            ),

        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthdate)],
            ASK_BIRTHPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthplace)],
            ASK_BIRTHTIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthtime),
                CallbackQueryHandler(get_birthtime, pattern="^birthtime_unknown$"),
            ],
            WAIT_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_wait_answer)],
            CONFIRM_RESET: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_reset)],

        },
        fallbacks=[MessageHandler(filters.Regex("(?i)^отменить$"), cancel)],
    )

    app.add_handler(conv_handler)

    app.add_handler(MessageHandler(filters.Regex("(?i)^меню$"), show_menu))
    app.add_handler(MessageHandler(filters.Regex("📋 Главное меню"), handle_main_menu))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))  # У тебя уже есть функция show_menu
    app.add_handler(CommandHandler("help", show_help))  # Нужно будет сделать функцию show_help
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CallbackQueryHandler(handle_start_callback, pattern="^/start$"))
    app.add_handler(CallbackQueryHandler(calendar_handler, pattern="^calendar_"))
    app.add_handler(CallbackQueryHandler(handle_cancel_resetdata, pattern="^cancel_resetdata$"))
    app.add_handler(CallbackQueryHandler(handle_inline_button_forecast, pattern="^inline_ask::"))
    app.add_handler(CallbackQueryHandler(handle_show_compat_result, pattern="^show_compat_result::"))
    app.add_handler(CallbackQueryHandler(handle_topup_coins, pattern="^topup_coins$"))
    app.add_handler(CallbackQueryHandler(handle_confirm_tariff_ok, pattern="^confirm_tariff_ok$"))
    app.add_handler(CallbackQueryHandler(handle_buy_package, pattern="^buy_package::"))
    app.add_handler(InlineQueryHandler(inlinequery))
    app.add_handler(CallbackQueryHandler(handle_question_theme_choice, pattern="^theme::"))
    app.add_handler(CallbackQueryHandler(handle_payment_history, pattern="^payment_history$"))
    app.add_handler(CallbackQueryHandler(handle_invoice_callback, pattern="^invoice::"))
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    app.add_handler(CallbackQueryHandler(handle_show_planet_info, pattern="^show_planet_info$"))
    app.add_handler(CallbackQueryHandler(show_twins_by_category, pattern=r"^show_twins_"))

    
    app.run_polling()

if __name__ == "__main__":
    main()


# %%
