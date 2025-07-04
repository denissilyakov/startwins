import asyncio
import pytz
import logging
from datetime import datetime, timedelta, time
from astrology_utils import get_pg_connection
from bot import get_question_chain_prompts, replace_variables_in_prompt, decorate_with_emojis, load_static_data
from copy import deepcopy
from datetime import datetime, timezone
from httpx import AsyncClient
from dotenv import load_dotenv

# Подгружаем model endpoint
MODEL_API_URL = "http://localhost:11434/api/generate"
proxies = {
    "http": None,
    "https": None,
}
load_dotenv()


async def generate_forecast_text(context, chain_id):
    prompts = get_question_chain_prompts(chain_id)
    full_text = ""

    for prompt, tone, temperature, _ in prompts:
        updated_prompt = replace_variables_in_prompt(prompt, context)

        payload = {
            "model": "gemma3:latest",
            "prompt": updated_prompt,
            "stream": False,
            "temperature": temperature,
            "system": tone
        }

        success = False
        for attempt in range(2):  # максимум 2 попытки
            try:
                async with AsyncClient(timeout=60.0, trust_env=False) as client:
                    response = await client.post(MODEL_API_URL, json=payload)
                    response.raise_for_status()
                    chunk = response.json().get("response", "")
                    full_text += chunk.strip() + "\n\n"
                    success = True
                    break  # успешная генерация — выходим из retry
            except Exception as e:
                if attempt == 0:
                    print(f"[⚠️] Ошибка генерации, повтор через 60 секунд: {e}")
                    await asyncio.sleep(60)
                else:
                    print(f"[❌] Повтор не удался: {e}")
                    raise e  # пробрасываем ошибку — обработается в handle_forecast_for_user

    decorated_text = decorate_with_emojis(full_text.strip())
    return decorated_text

async def generate_and_store_forecasts(chain_id):
    conn = get_pg_connection()
    cursor = conn.cursor()

    # Выбираем пользователей с установленным current_tz_offset
    cursor.execute("""
        SELECT user_id, chat_id, current_tz_offset, name, birthdate, gender, zodiac, chinese_year
        FROM users
        WHERE current_tz_offset IS NOT NULL
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    tasks = []
    for user_id, chat_id, tz_offset, name, birthdate, gender, zodiac, chinese_year in users:
        now_local = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
        forecast_date = now_local.date()
        
        # Эмуляция context.user_data
        user_data = {
            "user_id": user_id,
            "chat_id": chat_id,
            "forecast_date": forecast_date.strftime("%d.%m.%Y"),
            "tz_offset": tz_offset,
            "name": name,
            "birthdate": birthdate,
            "gender": gender,
            "zodiac": zodiac,
            "chinese_year": chinese_year,
        }

        task = asyncio.create_task(handle_forecast_for_user(user_id, chat_id, user_data, forecast_date, chain_id))
        tasks.append(task)

    await asyncio.gather(*tasks)

class DummyContext:
    def __init__(self, user_data):
        self.user_data = user_data

async def handle_forecast_for_user(user_id, chat_id, user_data_dict, forecast_date, chain_id):
    try:
        dummy_context = DummyContext(user_data_dict)
        forecast_text = await generate_forecast_text(dummy_context, chain_id)

        conn = get_pg_connection()
        cursor = conn.cursor()

        # Проверка: уже есть прогноз?
        cursor.execute("""
            SELECT 1 FROM scheduled_forecasts
            WHERE user_id = %s AND forecast_date = %s AND chain_id = %s
        """, (user_id, forecast_date, chain_id))

        if cursor.fetchone():
            cursor.close()
            conn.close()
            logging.info(f"[⏭️] Прогноз уже существует для user {user_id} на {forecast_date}")
            return

        # Запись прогноза
        cursor.execute("""
            INSERT INTO scheduled_forecasts (user_id, forecast_text, forecast_date, chain_id)
            VALUES (%s, %s, %s, %s)
        """, (user_id, forecast_text, forecast_date, chain_id))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        logging.error(f"[❌] Ошибка генерации для user {user_id}: {e}")

async def insert_outbox_messages():
    conn = get_pg_connection()
    cursor = conn.cursor()

    now_utc = datetime.now(timezone.utc)

    # Выбираем пользователей, у кого сейчас 9 утра по локальному времени
    cursor.execute("""
        SELECT sf.user_id, u.chat_id, sf.forecast_text
        FROM scheduled_forecasts sf
        JOIN users u ON sf.user_id = u.user_id
        WHERE sf.forecast_date = %s
        AND (
            (NOW() AT TIME ZONE 'UTC') + (u.current_tz_offset || ' hours')::interval
        )::time >= TIME '09:00'
        AND sf.forecast_text IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM outbox_messages o
            WHERE o.chat_id = u.chat_id AND o.text = sf.forecast_text AND o.created_at::date = CURRENT_DATE
        )
    """, (datetime.now(timezone.utc).date(),))

    rows = cursor.fetchall()

    for user_id, chat_id, text in rows:
        cursor.execute("""
            INSERT INTO outbox_messages (chat_id, text, status, created_at)
            VALUES (%s, %s, 0, NOW())
        """, (chat_id, text))

    conn.commit()
    cursor.close()
    conn.close()


async def main():
    chain_id = 110  # Пример chain_id
    load_static_data()

    while True:
        now = datetime.now().time()

        # Генерация только ночью
        if time(0, 1) <= now <= time(8, 0):
            logging.info("⏳ Ночное окно: выполняем генерацию прогнозов")
            await generate_and_store_forecasts(chain_id)
        else:
            logging.info("🌙 Вне окна генерации: генерация пропущена")

        # Отправка сообщений — всегда
        await insert_outbox_messages()

        # Повтор каждые 5 минут
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
