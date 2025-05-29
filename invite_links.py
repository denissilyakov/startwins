# invite_links.py

import uuid
import datetime
from astrology_utils import get_pg_connection  # предполагается, что у вас есть доступ к БД

BOT_USERNAME = "astrotwinstest_bot"  # замените на актуальное имя бота

def create_portrait_invite(user_id):
    token = str(uuid.uuid4())
    link = f"https://t.me/{BOT_USERNAME}?start=portrait_{token}"
    created_at = datetime.datetime.utcnow()

    conn = get_pg_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO portrait_links (token, creator_id, created_at, used) VALUES (%s, %s, %s, %s)",
                (token, user_id, created_at, False)
            )
    finally:
        conn.close()

    return link

def get_portrait_invite(token):
    conn = get_pg_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM portrait_links WHERE token = %s", (token,)
            )
            return cursor.fetchone()
    finally:
        conn.close()

def mark_invite_used(token):
    conn = get_pg_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE portrait_links SET used = TRUE WHERE token = %s", (token,)
            )
    finally:
        conn.close()

def build_share_button(link):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton  # исправлено под telegram.ext

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text="📤 Отправить другу", switch_inline_query=link
        )]
    ])
    return markup
