
from datetime import datetime
import os
import psycopg2
from telegram import LabeledPrice, Update
from telegram.ext import ContextTypes
from telegram.ext import PreCheckoutQueryHandler, MessageHandler, filters
from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update

ZODIAC_SIGNS = []
CHINESE_SIGNS = []
load_dotenv()
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
#PROVIDER_TOKEN = "381764678:TEST:126120"

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

def get_pg_connection():
    db_url = os.getenv("ASTROLOG_DB")
    if db_url is None:
        raise ValueError("Переменная окружения ASTROLOG_DB не установлена")
    return psycopg2.connect(db_url)

def load_zodiac_and_chinese_from_db():
    global ZODIAC_SIGNS, CHINESE_SIGNS
    conn = get_pg_connection()
    cursor = conn.cursor()

    # Загрузка ZODIAC_SIGNS
    cursor.execute("SELECT cutoff_date, name FROM zodiac_signs ORDER BY cutoff_date")
    ZODIAC_SIGNS = cursor.fetchall()  # [(120, "Козерог"), (218, "Водолей"), ...]

    # Загрузка CHINESE_SIGNS
    cursor.execute("SELECT name FROM chinese_signs ORDER BY id")
    CHINESE_SIGNS = [row[0] for row in cursor.fetchall()]

    conn.close()

# Загружаем при импорте
load_zodiac_and_chinese_from_db()

def get_zodiac_and_chinese_sign(date_str):
    day, month, year = map(int, date_str.split("."))
    mmdd = int(f"{month:02}{day:02}")
    zodiac = next(sign for cutoff, sign in ZODIAC_SIGNS if mmdd <= cutoff)
    chinese = CHINESE_SIGNS[(year - 1900) % 12]
    return zodiac, chinese

def get_inline_questions(inline_id: int, topic: int) -> list[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM inline_questions
                WHERE inline_id = %s AND topic =%s
                ORDER BY order_index
            """, (inline_id,topic))
            return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_user_asked_inline_questions(user_id: int, inline_id: int, topic: int) -> set[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM user_inline_logs
                WHERE user_id = %s AND inline_id = %s AND topic =%s
            """, (user_id, inline_id, topic))
            return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def log_user_inline_question(user_id: int, inline_id: int, question: str, topic: int) -> None:
    conn = get_pg_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_inline_logs (user_id, inline_id, question, topic)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (user_id, inline_id, question, topic))
    finally:
        conn.close()

def get_user_inline_question_texts(user_id: int, topic: int) -> list[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM user_inline_logs
                WHERE user_id = %s AND topic = %s
                ORDER BY asked_at DESC
                LIMIT 50
            """, (user_id, topic))
            rows = cursor.fetchall()
            return [row[0] for row in rows] if rows else []
    finally:
        conn.close()


# Получить баланс пользователя
def get_user_balance(user_id: int) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()

# Обновить баланс пользователя (прибавить или вычесть)
def update_user_balance(user_id: int, delta: int) -> None:
    conn = get_pg_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users SET balance = COALESCE(balance, 0) + %s
                    WHERE user_id = %s
                """, (delta, user_id))
    finally:
        conn.close()

# Получить стоимость генерации по id кнопки dynamic_menu
def get_generation_cost(button_id: int) -> int:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT cost FROM generation_costs WHERE menu_id = %s", (button_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()

# Пополнить баланс на фиксированное значение (например, 20 АстроКоинов)
def top_up_balance(user_id: int, amount: int = 20) -> None:
    update_user_balance(user_id, amount)

def insert_coin_transaction(user_id, coin_amount, price_rub, package_id=None, description=None):
    """
    Добавляет запись в таблицу coin_transactions.

    :param user_id: ID пользователя
    :param coin_amount: Количество начисляемых АстроКоинов
    :param price_rub: Стоимость в рублях (0 для бонусов)
    :param package_id: Идентификатор пакета (например, 101 для бонуса)
    :param description: Текстовое описание (опционально)
    """
    conn = get_pg_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO coin_transactions (user_id, coin_amount, price_rub, timestamp, package_id, description)
        VALUES (%s, %s, %s, NOW(), %s, %s)
    """, (user_id, coin_amount, price_rub, package_id, description))

    conn.commit()
    conn.close()

def add_welcome_bonus_if_needed(user_id):
    """
    Начисляет приветственный бонус пользователю, если он ещё не получал его.
    Бонус — 100 АстроКоинов, package_id = 101.
    """
    conn = get_pg_connection()
    cur = conn.cursor()

    # Проверка: уже начислялся ли бонус
    cur.execute("""
        SELECT 1 FROM coin_transactions
        WHERE user_id = %s AND package_id = 101
    """, (user_id,))
    already_given = cur.fetchone() is not None

    if not already_given:
        # Начисляем бонус
        cur.execute("""
            INSERT INTO coin_transactions (user_id, coin_amount, price_rub, timestamp, package_id)
            VALUES (%s, %s, %s, NOW(), %s)
        """, (user_id, 100, 0, 101))  # 0 рублей, т.к. бонус

        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

async def handle_invoice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, package_id = query.data.split("::")
        package_id = int(package_id)
    except:
        await query.message.reply_text("⚠️ Ошибка формата.")
        return

    # Получаем пакет
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, coin_amount, price_rub FROM astrocoin_packages WHERE id = %s and id <100", (package_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await query.message.reply_text("⚠️ Пакет не найден.")
        return

    id,title, coin_amount, price_rub = row
    price_kop = int(price_rub*100)

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=f"Покупка {coin_amount} АстроКоинов",
        payload=f"astrocoin::{package_id}",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=title, amount=price_kop)],
        need_email=True,
        send_email_to_provider=True,
        start_parameter="astro_start"
    )

async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user_id = update.effective_user.id

    try:
        _, package_id = payload.split("::")
        package_id = int(package_id)
    except:
        await update.message.reply_text("⚠️ Не удалось определить пакет.")
        return

    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coin_amount, price_rub FROM astrocoin_packages WHERE id = %s", (package_id,))
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("⚠️ Пакет не найден.")
        return

    coin_amount, price_rub = row
    from astrology_utils import top_up_balance, get_user_balance
    top_up_balance(user_id, coin_amount)

    cursor.execute("""
        INSERT INTO coin_transactions (user_id, coin_amount, price_rub, package_id)
        VALUES (%s, %s, %s, %s)
    """, (user_id, coin_amount, price_rub, package_id))
    conn.commit()
    conn.close()

    
    new_balance = get_user_balance(user_id)
    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n"
        f"🪙 Зачислено: {coin_amount} АстроКоинов\n"
        f"💰 Новый баланс: {new_balance}",
        reply_markup=menu_keyboard
    )


