import telebot
from telebot import types
from skyfield.api import load, Topos
from skyfield import almanac
from datetime import datetime, timedelta, timezone
import numpy as np
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# ---------------- Загрузка эфемерид ----------------
print("Загрузка эфемерид...")
planets = load('de421.bsp')
earth = planets['earth']
sun = planets['sun']
moon = planets['moon']
ts = load.timescale()
print("Эфемериды готовы")

# ---------------- BOT ----------------
TOKEN = "8248272716:AAGgypGFGkmjgaOFjSaLRmXSJ8yLBFgMAU0"
bot = telebot.TeleBot(TOKEN)

# ---------------- Scheduler ----------------
scheduler = BackgroundScheduler(timezone=pytz.utc)
scheduler.start()

# ---------------- Пользователи ----------------
user_data = {}

DEFAULT_LAT, DEFAULT_LON = 55.7558, 37.6176

OBJECT_MAP = {
    'sun': 'sun',
    'moon': 'moon',
    'mars': 'mars barycenter',
    'jupiter': 'jupiter barycenter',
    'saturn': 'saturn barycenter'
}

# ---------------------------------------------------
def get_user(chat_id):
    if chat_id not in user_data:
        user_data[chat_id] = {}
    return user_data[chat_id]

def reset_user(chat_id):
    if chat_id in user_data:
        del user_data[chat_id]

# ---------------- АСТРОНОМИЯ ----------------

def get_next_sunrise(lat, lon):
    topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
    t0 = ts.now()
    t1 = ts.utc(t0.utc_datetime() + timedelta(days=2))

    t, events = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(planets, topos))
    for ti, event in zip(t, events):
        if event == 1 and ti.utc_datetime() > datetime.now(timezone.utc):
            return ti.utc_datetime()
    return None


def get_next_sunset(lat, lon):
    topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
    t0 = ts.now()
    t1 = ts.utc(t0.utc_datetime() + timedelta(days=2))

    t, events = almanac.find_discrete(t0, t1, almanac.sunrise_sunset(planets, topos))
    for ti, event in zip(t, events):
        if event == 0 and ti.utc_datetime() > datetime.now(timezone.utc):
            return ti.utc_datetime()
    return None


def get_moon_phase_name():
    t = ts.now()
    phase = almanac.moon_phase(planets, t)
    deg = (phase.radians * 180 / np.pi) % 360

    if deg < 45: return "Новолуние"
    elif deg < 90: return "Растущий серп"
    elif deg < 135: return "Первая четверть"
    elif deg < 180: return "Растущая Луна"
    elif deg < 225: return "Полнолуние"
    elif deg < 270: return "Убывающая Луна"
    elif deg < 315: return "Последняя четверть"
    else: return "Убывающий серп"


def get_next_moon_phase_change():
    t0 = ts.now()
    t1 = ts.utc(t0.utc_datetime() + timedelta(days=10))
    t, _ = almanac.find_discrete(t0, t1, almanac.moon_phases(planets))
    if len(t) > 0:
        return t[0].utc_datetime()
    return None


def get_object_altitude_azimuth(obj, lat, lon):
    try:
        key = OBJECT_MAP.get(obj)
        if not key:
            return None

        body = planets[key]
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)
        observer = earth + topos
        t = ts.now()

        astrometric = observer.at(t).observe(body)
        apparent = astrometric.apparent()
        alt, az, _ = apparent.altaz()

        return alt.degrees, az.degrees
    except Exception as e:
        print("AltAz error:", e)
        return None

# ---------------- Ответ ----------------

def compute_answer(user):
    try:
        req_type = user.get('request_type')
        lat = user.get('lat', DEFAULT_LAT)
        lon = user.get('lon', DEFAULT_LON)

        if req_type == 'other':
            return "Вы выбрали 'Другое'."

        if user.get('exact_query') == 'sunrise':
            t = get_next_sunrise(lat, lon)
            user['event_time'] = t
            return f"🌅 Восход: {t.strftime('%d.%m.%Y %H:%M UTC')}"

        if user.get('exact_query') == 'sunset':
            t = get_next_sunset(lat, lon)
            user['event_time'] = t
            return f"🌇 Закат: {t.strftime('%d.%m.%Y %H:%M UTC')}"
    if user.get('exact_query') == 'moonphase':
        phase = get_moon_phase_name()
        t = get_next_moon_phase_change()
        user['event_time'] = t
        return f"🌙 Фаза Луны: {phase}\nСледующая смена: {t.strftime('%d.%m.%Y %H:%M UTC')}"

    if req_type == 'object':
        obj = user.get('exact_query')
        altaz = get_object_altitude_azimuth(obj, lat, lon)
        if altaz:
            alt, az = altaz
            return f"🪐 {obj.capitalize()}\nВысота: {alt:.1f}°\nАзимут: {az:.1f}°"
        else:
            return "Не удалось определить положение объекта."

    return "Не удалось обработать запрос."
    except Exception as e:
    print("Compute error:", e)
    return "⚠️ Ошибка вычисления."


# ---------------- Напоминание ----------------

def schedule_reminder(chat_id, event_time, minutes_before):
    if not event_time:
        return

    notify_time = event_time - timedelta(minutes=minutes_before)

    def send_notification():
        bot.send_message(chat_id, "⏰ Напоминание! Событие скоро!")

    scheduler.add_job(send_notification, 'date', run_date=notify_time)


# ---------------- Команды ----------------

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    reset_user(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("События", callback_data="events"))
    bot.send_message(chat_id, "Привет 🌌", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "events")
def choose_event(call):
    chat_id = call.message.chat.id
    user = get_user(chat_id)
    user['request_type'] = 'event'

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Восход", callback_data="sunrise"),
        types.InlineKeyboardButton("Закат", callback_data="sunset"),
        types.InlineKeyboardButton("Фаза Луны", callback_data="moonphase")
    )

    bot.send_message(chat_id, "Выбери:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ["sunrise", "sunset", "moonphase"])
def process_event(call):
    chat_id = call.message.chat.id
    user = get_user(chat_id)

    user['exact_query'] = call.data
    user['lat'] = DEFAULT_LAT
    user['lon'] = DEFAULT_LON

    answer = compute_answer(user)
    bot.send_message(chat_id, answer)

    if 'event_time' in user and user['event_time']:
        schedule_reminder(chat_id, user['event_time'], 10)
        bot.send_message(chat_id, "⏰ Напоминание за 10 минут установлено!")


# ---------------- Запуск ----------------
print("Бот запущен")
bot.infinity_polling()