# invite_links.py

import uuid
import datetime
from astrology_utils import get_pg_connection  # предполагается, что у вас есть доступ к БД
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from astrology_utils import update_user_balance, get_user_balance


def create_portrait_invite(user_id: int) -> str:
    """
    Генерирует токен приглашения в формате portrait_<uuid> и сохраняет в БД.
    Возвращает токен (НЕ ссылку) для использования в switch_inline_query.
    """
    token = f"portrait_{str(uuid.uuid4())}"
    created_at = datetime.datetime.utcnow()

    conn = get_pg_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO portrait_links (token, creator_id, created_at, used) "
                    "VALUES (%s, %s, %s, %s)",
                    (token, user_id, created_at, False)
                )
    finally:
        conn.close()

    return token  # ⚠️ Возвращаем токен, а не ссылку

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

def build_share_button(token: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="📤 Пригласить друга",
            switch_inline_query=token  # пользователь выбирает контакт, и бот отправляет инлайн-сообщение
        )
    ]])


async def process_portrait_invite(start_param, user_id, bot):
    #"""
    #Обрабатывает инвайт-ссылку с токеном формата 'portrait_xxx'.
    #Начисляет бонус 250 АстроКоинов пригласившему, если ссылка не была использована.
    #"""

    token = start_param.strip()
    print("Обработка начисления бонуса")


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

                # Начисляем 250 АстроКоинов
                bonus_amount = 250
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
            "🎉 По вашей портретной ссылке зарегистрировался пользователь!\n"
            f"Вы получили +{bonus_amount} АстроКоинов. 💰\n"
            f"Ваш текущий баланс: {new_balance} АстроКоинов."
        )
    )



