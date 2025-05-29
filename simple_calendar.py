from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
import calendar
from telegram import ReplyKeyboardRemove
from astrology_utils import get_zodiac_and_chinese_sign
from astrology_module import get_astrology_text_for_date

class SimpleCalendar:
    def __init__(self, min_date=None, max_date=None, mode="year_selection", center_year=None):
        self.min_date = min_date
        self.max_date = max_date
        self.mode = mode
        self.center_year = center_year or datetime.now().year

    def get_month_name(self, month):
        months = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        return months[month - 1]

    def build_calendar(self, year=None, month=None):
        now = datetime.now()
        year = year or now.year
        month = month or now.month

        if self.mode == "year_selection":
            return self.build_year_selection(self.center_year)
        if self.mode == "month_selection":
            return self.build_month_selection(year)

        keyboard = []
        keyboard.append([
            InlineKeyboardButton("<<", callback_data=f"calendar_prev_year_{year}_{month}"),
            InlineKeyboardButton(f"{year}", callback_data="calendar_select_year"),
            InlineKeyboardButton(self.get_month_name(month), callback_data="calendar_select_month")
        ])
        keyboard.append([
            InlineKeyboardButton("<", callback_data=f"calendar_prev_month_{year}_{month}"),
            InlineKeyboardButton(" ", callback_data="ignore"),
            InlineKeyboardButton(">", callback_data=f"calendar_next_month_{year}_{month}")
        ])

        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])

        month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        for week in month_calendar:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    button_date = datetime(year, month, day)
                    if self.is_in_range(button_date):
                        row.append(InlineKeyboardButton(
                            str(day),
                            callback_data=f"calendar_confirm_{year}_{month}_{day}"
                        ))
                    else:
                        row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            keyboard.append(row)

        return InlineKeyboardMarkup(keyboard)

    def build_year_selection(self, center_year=None):
        keyboard = []
        center_year = center_year or self.center_year
        start_year = center_year - 7
        years = [start_year + i for i in range(15)]

        row = []
        for i, y in enumerate(years, start=1):
            year_start = datetime(y, 1, 1)
            year_end = datetime(y, 12, 31)
            if self.is_in_range(year_start) or self.is_in_range(year_end):
                row.append(InlineKeyboardButton(str(y), callback_data=f"calendar_year_select_{y}"))
            else:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            if i % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton("<<", callback_data=f"calendar_prev_years_{start_year}"),
            InlineKeyboardButton(" ", callback_data="ignore"),
            InlineKeyboardButton(">>", callback_data=f"calendar_next_years_{start_year + 14}")
        ])

        return InlineKeyboardMarkup(keyboard)


    def build_month_selection(self, year):
        months = [
            ("Янв", 1), ("Фев", 2), ("Мар", 3),
            ("Апр", 4), ("Май", 5), ("Июн", 6),
            ("Июл", 7), ("Авг", 8), ("Сен", 9),
            ("Окт", 10), ("Ноя", 11), ("Дек", 12),
        ]

        keyboard = []
        row = []
        for i, (name, num) in enumerate(months, start=1):
            first_day = datetime(year, num, 1)
            last_day = datetime(year, num, calendar.monthrange(year, num)[1])
            if self.is_in_range(first_day) or self.is_in_range(last_day):
                row.append(InlineKeyboardButton(name, callback_data=f"calendar_month_{year}_{num}"))
            if i % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        return InlineKeyboardMarkup(keyboard)

    def is_in_range(self, date):
        if self.min_date and date < self.min_date:
            return False
        if self.max_date and date > self.max_date:
            return False
        return True

    def is_prev_disabled(self, year, month):
        if not self.min_date:
            return False
        prev_month = month - 1 or 12
        prev_year = year - 1 if month == 1 else year
        first_day_prev = datetime(prev_year, prev_month, 1)
        return first_day_prev < self.min_date.replace(day=1)

    def is_next_disabled(self, year, month):
        if not self.max_date:
            return False
        next_month = month + 1 if month < 12 else 1
        next_year = year + 1 if month == 12 else year
        first_day_next = datetime(next_year, next_month, 1)
        return first_day_next > self.max_date.replace(day=1)


# === ОБРАБОТЧИК КАЛЕНДАРЯ ===

def get_calendar_object(options_str):
    if "DATE" in options_str:
        return SimpleCalendar(min_date=datetime.now() + timedelta(days=1))
    elif "PASTDT" in options_str:
        return SimpleCalendar(max_date=datetime.now() - timedelta(days=1))
    
    elif "BIRTHDT" in options_str:
        return SimpleCalendar(
            min_date=datetime(1925, 1, 1),
            max_date=datetime(2015, 12, 31),
            center_year=2000
        )
        
    else:
        return SimpleCalendar()


async def calendar_handler(update, context):
    query = update.callback_query
    await query.answer()

    save_answer_to_db = context.bot_data["save_answer_to_db"]
    ask_question = context.bot_data["ask_question"]

    data = query.data
    options_str = context.user_data.get("current_options_str", "")
    cal = get_calendar_object(options_str)
    user_id = query.from_user.id

    try:
        
        if data == "calendar_select_year":
            cal.mode = "year_selection"
            selected_date = context.user_data.get("selected_date")
            if selected_date:
                _, _, year = selected_date.split(".")
                center_year = int(year)
            else:
                center_year = datetime.now().year

            await query.edit_message_reply_markup(
                reply_markup=cal.build_year_selection(center_year)
            )


        elif data.startswith("calendar_year_select_"):
            _, _, _, year = data.split("_")
            year = int(year)
            context.user_data["calendar_year"] = year
            cal.mode = "month_selection"
            await query.edit_message_reply_markup(reply_markup=cal.build_month_selection(year))

        elif data.startswith("calendar_month_"):
            _, _, year, month = data.split("_")
            year = int(year)
            month = int(month)
            context.user_data["calendar_month"] = month
            cal.mode = "default"
            await query.edit_message_reply_markup(reply_markup=cal.build_calendar(year, month))

        elif data.startswith("calendar_confirm_"):
            _, _, year, month, day = data.split("_")
            selected_date = f"{int(day):02}.{int(month):02}.{year}"
            context.user_data["selected_date"] = selected_date

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data="calendar_final_confirm")],
                [InlineKeyboardButton("✏️ Изменить", callback_data="calendar_select_year")]
            ])
            await query.edit_message_text(
                f"Вы выбрали дату: {selected_date}",
                reply_markup=keyboard
            )
            
            
        elif data == "calendar_final_confirm":
            selected_date = context.user_data.get("selected_date")
            if not selected_date:
                await query.edit_message_text("Ошибка: дата не выбрана.")
                return

            # ✅ Если это цепочка
            if "chain_id" in context.user_data and "question_step" in context.user_data:
                query_step = context.user_data["question_step"]
                context.user_data["event_answers"][query_step] = selected_date

                save_answer_to_db(
                    query.from_user.id,
                    context.user_data["chain_id"],
                    query_step,
                    selected_date,
                )

                context.user_data["question_step"] += 1

                    # ✅ Если в цепочке указан BIRTHDT — вычисляем зодиаки, но НЕ трогаем профиль
                if any(opt in context.user_data.get("current_options_str", "") for opt in ["BIRTHDT"]):
                    zodiac, chinese = get_zodiac_and_chinese_sign(selected_date)
                    context.user_data["bdate_zodiac"] = zodiac
                    context.user_data["bdate_chinese"] = chinese
                    
                                # Получаем текст для планет, как делалось в user_wait_answer
                if any(opt in context.user_data.get("current_options_str", "") for opt in ["DATE", "PASTDT", "BIRTHDT"]):
                    if "planets_info_counter" not in context.user_data:
                        context.user_data["planets_info_counter"] = 0
                    else:
                        context.user_data["planets_info_counter"] += 1

                    planets_key = f"planets_info_{context.user_data['planets_info_counter']}"
                    planets_info = get_astrology_text_for_date(
                        selected_date,
                        time_str="12:00",
                        mode="model",
                        tz_offset=context.user_data.get("tz_offset", 0)
                    )
                    context.user_data[planets_key] = planets_info

                return await ask_question(update, context)

            # ✅ Если это регистрация — и только регистрация
            if "chain_id" not in context.user_data:
                zodiac, chinese = get_zodiac_and_chinese_sign(selected_date)
                context.user_data["birthdate"] = selected_date
                context.user_data["zodiac"] = zodiac
                context.user_data["chinese_year"] = chinese

                save_user_data = context.bot_data["save_user_data"]
                save_user_data(user_id, context.user_data)

                await query.message.reply_text(
                    f"Принято! Знак зодиака: {zodiac}, Восточный знак: {chinese}.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await query.message.reply_text(
                    "📍 Укажите место рождения (пример: деревня Лазурная, Конаковский район, Тверская область):"
                )
                return context.bot_data["ASK_BIRTHPLACE"]




        elif data.startswith("calendar_prev_years_") or data.startswith("calendar_next_years_"):
            _, action, _, start_year = data.split("_")
            start_year = int(start_year)

            if action == "prev":
                new_start_year = start_year - 15
            else:
                new_start_year = start_year + 15

            center_year = new_start_year + 7
            cal = get_calendar_object(options_str)
            cal.mode = "year_selection"
            await query.edit_message_reply_markup(
                reply_markup=cal.build_year_selection(center_year)
            )

    except Exception as e:
        print(f"Ошибка в calendar_handler: {e}")
        await query.edit_message_text("⚠️ Ошибка при обработке календаря")
