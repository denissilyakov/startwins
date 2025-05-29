import swisseph as swe
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Wedge, Patch
from matplotlib.lines import Line2D
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
from io import BytesIO
from skyfield.api import load
from datetime import datetime, timedelta
import math
import matplotlib.font_manager as fm

planet_names = {
    swe.SUN: "Солнце",
    swe.MOON: "Луна",
    swe.MERCURY: "Меркурий",
    swe.VENUS: "Венера",
    swe.MARS: "Марс",
    swe.JUPITER: "Юпитер",
    swe.SATURN: "Сатурн",
    swe.URANUS: "Уран",
    swe.NEPTUNE: "Нептун",
    swe.PLUTO: "Плутон"
}

zodiac_symbols = [
    "♈", "♉", "♊", "♋", "♌", "♍",
    "♎", "♏", "♐", "♑", "♒", "♓"
]

planet_descriptions = {
    "Солнце": "отражает сущность личности, её эго и жизненную силу.",
    "Луна": "описывает эмоции, инстинкты и внутренний мир.",
    "Меркурий": "отвечает за мышление, речь и восприятие информации.",
    "Венера": "связана с чувствами, любовью и эстетикой.",
    "Марс": "отвечает за активность, волю и сексуальность.",
    "Юпитер": "символизирует рост, удачу и мировоззрение.",
    "Сатурн": "представляет структуру, дисциплину и ограничения.",
    "Уран": "отвечает за перемены, оригинальность и бунт.",
    "Нептун": "влияет на интуицию, мечты и иллюзии.",
    "Плутон": "связан с трансформацией, силой и глубиной."
}

zodiac_signs = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
]

zodiac_sign_traits = [
    "инициативный, энергичный, импульсивный",
    "практичный, надёжный, чувственный",
    "общительный, любознательный, умный",
    "эмоциональный, заботливый, интуитивный",
    "лидерский, творческий, харизматичный",
    "анализирующий, трудолюбивый, скромный",
    "гармоничный, дипломатичный, эстетичный",
    "интенсивный, страстный, проницательный",
    "оптимистичный, философский, свободолюбивый",
    "целеустремлённый, ответственный, сдержанный",
    "оригинальный, независимый, дружелюбный",
    "мечтательный, чувствительный, духовный"
]

house_names = [
    "Личность и внешность", 
    "Деньги и ценности", 
    "Образование и коммуникации", 
    "Семья и дом", 
    "Творчество, дети и любовь", 
    "Работа и здоровье", 
    "Партнерства и браки", 
    "Трансформация и ресурсы других людей", 
    "Философия, путешествия и высшее образование", 
    "Карьера, статус и амбиции", 
    "Друзья и социальные связи", 
    "Подсознание и тайные враги"
]

def get_astrology_text_for_date(
    date_str: str,
    time_str: str = "12:00",
    mode: str = "pretty",
    tz_offset: int = 0
) -> str:
    from skyfield.api import load
    from skyfield.positionlib import ICRF
    import numpy as np

    full_dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    birth_date = full_dt - timedelta(hours=tz_offset)

    jd = swe.julday(birth_date.year, birth_date.month, birth_date.day,
                    birth_date.hour + birth_date.minute / 60)

    planets = list(planet_names.keys())
    planet_info = []
    degrees = {}

    for planet in planets:
        pos, _ = swe.calc(jd, planet)
        total_deg = pos[0]
        sign_index = int(total_deg / 30)
        sign_degree = total_deg % 30
        name = planet_names[planet]
        sign = zodiac_signs[sign_index]
        trait = zodiac_sign_traits[sign_index]
        summary = planet_descriptions[name]
        degrees[name] = total_deg

        if mode == "pretty":
            planet_info.append(
                f"\U0001F31F {name} в знаке {sign} ({sign_degree:.1f}°)\n"
                f"• {summary}\n"
                f"• Проявляется как {trait}.\n"
            )
        elif mode == "short":
            planet_info.append(f"{name} в {sign} ({sign_degree:.1f}°)")
        elif mode == "model":
            planet_info.append(f"{name}: знак {sign} ({sign_degree:.1f}°), черты: {trait}, описание: {summary}")
        else:
            planet_info.append(f"{name}: {sign} {sign_degree:.1f}° — {summary} — черты: {trait}")

    aspect_texts = []
    aspect_names = {0: "Конъюнкция", 60: "Секстиль", 90: "Квадрат", 120: "Тригон", 180: "Оппозиция"}

    planet_items = list(degrees.items())
    for i in range(len(planet_items)):
        for j in range(i + 1, len(planet_items)):
            p1, d1 = planet_items[i]
            p2, d2 = planet_items[j]
            diff = abs(d1 - d2)
            if diff > 180:
                diff = 360 - diff
            for aspect_deg, aspect_name in aspect_names.items():
                if abs(diff - aspect_deg) <= 3:
                    aspect_texts.append(f"{p1} и {p2}: {aspect_name} ({diff:.1f}°)")

    lat, lon = 0.0, 0.0
    houses, _ = swe.houses(jd, lat, lon, b'A')
    house_texts = [f"Дом {i+1} ({house_names[i]}): {houses[i]:.2f}°" for i in range(12)]

    node_pos, _ = swe.calc(jd, swe.MEAN_NODE)
    north = node_pos[0]
    south = (north + 180) % 360

    if mode == "pretty":
        return (
            f"\U0001F4C5 Дата: {date_str}, {time_str} (UTC{tz_offset:+})\n\n"
            f"\U0001FA90 Положение планет:\n" + "\n".join(planet_info) + "\n"
            f"⚖ Аспекты:\n" + ("\n".join(aspect_texts) if aspect_texts else "Нет значимых аспектов.") + "\n"
            f"\U0001F3E0 Дома:\n" + "\n".join(house_texts) + "\n\n"
            f"\U0001F319 Северный узел: {north:.2f}°\n"
            f"\U0001F311 Южный узел: {south:.2f}°\n"
        )
    elif mode == "short":
        return (
            f"Астрологическая справка на {date_str} (UTC{tz_offset:+}):\n"
            f"Положение планет: " + ", ".join(planet_info)
        )
    elif mode == "model":
        return (
            f"Астрологические данные для даты {date_str}, время {time_str} (UTC{tz_offset:+}):\n"
            #f"Планеты:\n" + " | ".join(planet_info) + "\n"
            f"Аспекты:\n" + (" | ".join(aspect_texts) if aspect_texts else "нет аспектов") + "\n"
            f"Дома:\n" + " | ".join(house_texts) + "\n"
            f"Северный узел: {north:.2f}° | Южный узел: {south:.2f}°"
        )
    else:
        return (
            f"Дата: {date_str}, {time_str} (UTC{tz_offset:+})\n"
            f"Планеты:\n" + "; ".join(planet_info) + "\n"
            f"Аспекты:\n" + (", ".join(aspect_texts) if aspect_texts else "нет") + "\n"
            f"Дома:\n" + "; ".join(house_texts) + "\n"
            f"Северный узел: {north:.2f}°; Южный узел: {south:.2f}°"
        )




def generate_chart_image(birthdate: str, birthtime: str, tz_offset: int, user_name: str) -> BytesIO:
    
    plt.rcParams['font.family'] = 'DejaVu Sans'
    # === ДАННЫЕ ===
    roman_numerals = {i + 1: r for i, r in enumerate(["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"])}
    zodiac_signs = ['♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓']
    zodiac_names = ['Овен', 'Телец', 'Близнецы', 'Рак', 'Лев', 'Дева',
                    'Весы', 'Скорпион', 'Стрелец', 'Козерог', 'Водолей', 'Рыбы']
    element_names = ['Огонь', 'Земля', 'Воздух', 'Вода'] * 3
    element_fill = {
        'Огонь': '#ff3333',
        'Земля': '#33cc33',
        'Воздух': '#33ccff',
        'Вода':  '#3399ff'
    }

    aspect_styles = {
        '☍': {'color': 'red', 'ls': '--'},
        '△': {'color': 'green', 'ls': '-'},
        '□': {'color': 'orange', 'ls': ':'},
        #'✶': {'color': 'blue', 'ls': '-.'},
        #'⚻': {'color': 'purple', 'ls': ':'}
    }

    aspect_definitions = {
        '☍': (180, 6),
        '△': (120, 6),
        '□': (90, 6),
        #'✶': (60, 6),
        #'⚻': (150, 6)
    }

    planet_image_files = {
        '☉': ('Солнце', 'planet_images/sun.png'),
        '☽': ('Луна', 'planet_images/moon.png'),
        '☿': ('Меркурий', 'planet_images/mercury.png'),
        '♀': ('Венера', 'planet_images/venus.png'),
        '♂': ('Марс', 'planet_images/mars.png'),
        '♃': ('Юпитер', 'planet_images/jupiter.png'),
        '♄': ('Сатурн', 'planet_images/saturn.png'),
        '♅': ('Уран', 'planet_images/uranus.png'),
        '♆': ('Нептун', 'planet_images/neptune.png'),
        '♇': ('Плутон', 'planet_images/pluto.png'),
        'ASC': ('Асцендент', 'planet_images/ascendant.png'),
        'MC': ('MC', 'planet_images/mc.png'),
        '☊': ('Северный Узел', 'planet_images/north_node.png'),
        '☋': ('Южный Узел', 'planet_images/south_node.png'),
        '⚷': ('Хирон', 'planet_images/chiron.png'),
        '⚸': ('Лилит', 'planet_images/lilith.png')
    }

    # === Расчёт положения планет ===
    planets = load('de421.bsp')
    ts = load.timescale()

    dt = datetime.strptime(f"{birthdate} {birthtime}", "%d.%m.%Y %H:%M")
    dt_utc = dt - timedelta(hours=tz_offset)
    t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute)

    planet_ids = {
        '☉': 10, '☽': 301, '☿': 1, '♀': 2, '♂': 4,
        '♃': 5, '♄': 6, '♅': 7, '♆': 8, '♇': 9
    }

    planet_positions = {}
    for symbol, spk_id in planet_ids.items():
        planet = planets[spk_id]
        astrometric = planet.at(t).ecliptic_position()
        x, y = astrometric.au[0], astrometric.au[1]
        lon = np.degrees(np.arctan2(y, x)) % 360
        planet_positions[symbol] = lon

    # Узлы
    e = planets['earth']
    moon = planets['moon']
    sun = planets['sun']
    astrometric_moon = moon.at(t).observe(e).apparent()
    astrometric_sun = sun.at(t).observe(e).apparent()
    ra_moon, _, _ = astrometric_moon.radec()
    ra_sun, _, _ = astrometric_sun.radec()
    north_node = (ra_moon.hours - ra_sun.hours) * 15 % 360
    south_node = (north_node + 180) % 360
    planet_positions['☊'] = north_node
    planet_positions['☋'] = south_node
    #planet_positions['⚷'] = 160
    #planet_positions['⚸'] = 210
    planet_positions['ASC'] = 0
    planet_positions['MC'] = 90

    # === Расчёт аспектов ===
    aspects = []
    symbols = list(planet_positions.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sym1, sym2 = symbols[i], symbols[j]
            angle1, angle2 = planet_positions[sym1], planet_positions[sym2]
            diff = abs(angle1 - angle2)
            diff = diff if diff <= 180 else 360 - diff
            for asp_symbol, (asp_angle, orb) in aspect_definitions.items():
                if abs(diff - asp_angle) <= orb:
                    aspects.append((sym1, sym2, asp_symbol))
                    break

    # === Построение графика ===
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_xlim(-1.6, 1.5)
    ax.set_ylim(-1.6, 1.8)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('#111122')

    # Сектора домов и зодиаков
    for i in range(12):
        angle_deg = i * 30
        angle_rad = np.radians(angle_deg + 15)
        elem = element_names[i]
        color = element_fill[elem]

        ax.add_patch(Wedge((0, 0), 1.5, angle_deg, angle_deg + 30, facecolor=color, edgecolor='gray', lw=0.5, alpha=0.25))

        x_sign = 1.65 * np.cos(angle_rad)
        y_sign = 1.65 * np.sin(angle_rad)
        x_dom = 1.85 * np.cos(angle_rad)
        y_dom = 1.85 * np.sin(angle_rad)

        ax.text(x_sign, y_sign + 0.06, zodiac_signs[i], color='white', ha='center', fontsize=22)
        ax.text(x_sign, y_sign - 0.05, zodiac_names[i], color='white', ha='center', fontsize=10)
        ax.text(x_dom, y_dom, f"Дом {roman_numerals[i+1]}", color='gold', ha='center', va='center', fontsize=8, weight='bold',
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#222222", edgecolor='gold', alpha=0.8))

    # Планеты с расчётом перекрытий
    planet_screen_positions = {}
    for symbol, lon in planet_positions.items():
        label, img_path = planet_image_files.get(symbol, (symbol, None))
        angle = np.radians(lon)
        if symbol in ['ASC', 'MC']:
            r = 0.9
        elif symbol in ['☊', '☋', '⚷', '⚸']:
            r = 0.6
        else:
            r = 1.2
        x, y = r * np.cos(angle), r * np.sin(angle)
        planet_screen_positions[symbol] = [x, y, r]

    # Проверка перекрытий
    symbols = list(planet_screen_positions.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sym1, sym2 = symbols[i], symbols[j]
            x1, y1, r1 = planet_screen_positions[sym1]
            x2, y2, r2 = planet_screen_positions[sym2]
            distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
            if distance < 0.08:
                # Сдвигаем вторую планету ближе к центру
                new_r2 = r2 - 0.3
                angle2 = math.atan2(y2, x2)
                new_x2 = new_r2 * math.cos(angle2)
                new_y2 = new_r2 * math.sin(angle2)
                planet_screen_positions[sym2] = [new_x2, new_y2, new_r2]

    # Отрисовка планет
    for symbol, (x, y, r) in planet_screen_positions.items():
        label, img_path = planet_image_files.get(symbol, (symbol, None))
        try:
            img = Image.open(img_path).convert("RGBA")
            imagebox = OffsetImage(img, zoom=0.14)
            ab = AnnotationBbox(imagebox, (x, y), frameon=False)
            ax.add_artist(ab)
        except:
            ax.text(x, y, symbol, fontsize=16, color='white', ha='center')

        text_offset = 0.09 * (r / 1.2)
        ax.text(x, y - text_offset, label, fontsize=10, color='deepskyblue', ha='center', weight='bold',
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#111111", edgecolor='deepskyblue', alpha=0.6))

    # Аспекты
    for p1, p2, asp in aspects:
        x1, y1, _ = planet_screen_positions[p1]
        x2, y2, _ = planet_screen_positions[p2]
        style = aspect_styles[asp]
        lw = 2 if 'ASC' in [p1, p2] or 'MC' in [p1, p2] else 1
        ax.add_line(Line2D([x1, x2], [y1, y2], color=style['color'], linestyle=style['ls'], lw=lw, alpha=0.9))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my, asp, color=style['color'], fontsize=8, ha='center')

    # Легенда
    legend_items = [
        Line2D([0], [0], color='red', lw=2, linestyle='--', label='Оппозиция ☍'),
        Line2D([0], [0], color='green', lw=2, linestyle='-', label='Тригон △'),
        Line2D([0], [0], color='orange', lw=2, linestyle=':', label='Квадрат □'),
        #Line2D([0], [0], color='blue', lw=2, linestyle='-.', label='Секстиль ✶'),
        #Line2D([0], [0], color='purple', lw=2, linestyle=':', label='Квинконс ⚻'),
        Patch(facecolor='#ff3333', edgecolor='none', alpha=0.25, label='Стихия: Огонь'),
        Patch(facecolor='#33cc33', edgecolor='none', alpha=0.25, label='Стихия: Земля'),
        Patch(facecolor='#33ccff', edgecolor='none', alpha=0.25, label='Стихия: Воздух'),
        Patch(facecolor='#3399ff', edgecolor='none', alpha=0.25, label='Стихия: Вода')
    ]
    
    legend = ax.legend(
        handles=legend_items,
        loc='lower center',          # ➡️ Легенда будет привязана к центру снизу
        bbox_to_anchor=(0.5, -0.3),   # ➡️ Центр по оси X (0.5 = середина), вниз по оси Y
        fontsize=9,
        facecolor="#222233",
        edgecolor='white'
    )
    for t in legend.get_texts():
        t.set_color("white")

    ax.set_title(user_name, color='gold', fontsize=22, pad=30)

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)

    return buf