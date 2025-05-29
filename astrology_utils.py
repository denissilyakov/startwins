
from datetime import datetime
import os
import psycopg2

ZODIAC_SIGNS = []
CHINESE_SIGNS = []

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

def get_inline_questions(inline_id: int) -> list[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM inline_questions
                WHERE inline_id = %s
                ORDER BY order_index
            """, (inline_id,))
            return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_user_asked_inline_questions(user_id: int, inline_id: int) -> set[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM user_inline_logs
                WHERE user_id = %s AND inline_id = %s
            """, (user_id, inline_id))
            return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def log_user_inline_question(user_id: int, inline_id: int, question: str) -> None:
    conn = get_pg_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_inline_logs (user_id, inline_id, question)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (user_id, inline_id, question))
    finally:
        conn.close()

def get_user_inline_question_texts(user_id: int) -> list[str]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT question FROM user_inline_logs
                WHERE user_id = %s
                ORDER BY asked_at DESC
                LIMIT 50
            """, (user_id,))
            return [row[0] for row in cursor.fetchall()]
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
