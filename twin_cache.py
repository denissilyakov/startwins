# twin_cache.py
from collections import defaultdict
from astrology_utils import get_pg_connection

twin_data_cache = {}  # twin_id -> {'planets': {...}, 'houses': {...}}
twin_meta = {}        # twin_id -> {'gender': 'мужчина', 'country': 'RU'}

def load_twin_data():
    global twin_data_cache, twin_meta
    twin_data_cache.clear()
    twin_meta.clear()

    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, gender_ru, countrycode FROM pantheon_enriched")
    for twin_id, gender, country in cursor.fetchall():
        twin_meta[twin_id] = {'gender': gender, 'country': country}

    cursor.execute("SELECT person_id, planet_name, degree FROM astrology_planets")
    planet_rows = cursor.fetchall()

    cursor.execute("SELECT person_id, house_number, degree FROM astrology_houses")
    house_rows = cursor.fetchall()

    planets = defaultdict(dict)
    for person_id, name, degree in planet_rows:
        planets[person_id][name] = degree

    houses = defaultdict(dict)
    for person_id, number, degree in house_rows:
        houses[person_id][f"Дом {number}"] = degree

    for twin_id in twin_meta:
        twin_data_cache[twin_id] = {
            'planets': planets.get(twin_id, {}),
            'houses': houses.get(twin_id, {})
        }

    cursor.close()
    conn.close()
    print(f"✅ Twin data loaded: {len(twin_data_cache)} entries.")
