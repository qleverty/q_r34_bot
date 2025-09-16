import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.storage import StateMemoryStorage
from io import BytesIO
from threading import Lock
import sqlite3
import time

bot = telebot.TeleBot('8172939847:AAFv6Vyb4iyQHfKlnATKlo7MAtE9-W0JzdA', state_storage=StateMemoryStorage())
users_lock = Lock()
file_lock = Lock()
rate_limit = {}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (chat_id INTEGER PRIMARY KEY, query TEXT, image_id INTEGER, page INTEGER, message_id INTEGER)''')
    conn.commit()
    return conn

db_conn = init_db()

def get_user_data(chat_id):
    c = db_conn.cursor()
    c.execute("SELECT query, image_id, page, message_id FROM users WHERE chat_id = ?", (chat_id,))
    result = c.fetchone()
    return {"q": result[0], "id": result[1], "p": result[2], "message_id": result[3]} if result else None

def set_user_data(chat_id, query, image_id, page, message_id=None):
    c = db_conn.cursor()
    if message_id:
        c.execute("INSERT OR REPLACE INTO users (chat_id, query, image_id, page, message_id) VALUES (?, ?, ?, ?, ?)",
                  (chat_id, query, image_id, page, message_id))
    else:
        c.execute("UPDATE users SET query = ?, image_id = ?, page = ? WHERE chat_id = ?",
                  (query, image_id, page, chat_id))
    db_conn.commit()

def get_url(q, id, page):
    try:
        response = requests.get(
            f"https://rule34.us/index.php?r=posts/index&q={q.lower().strip()}&page={page}",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            container = soup.find('div', class_='thumbail-container')
            if container:
                elements = container.find_all('div', recursive=False)
                if elements and id < len(elements):
                    img_tag = elements[id].find('img')
                    if img_tag and 'src' in img_tag.attrs:
                        return img_tag['src'], len(elements)
                return None, len(elements) if elements else 0
            return None, 0
        return None, 0
    except Exception as e:
        return None, 0

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "bla bla bla blew blew blew\njerk off as long as this bot even works")

@bot.message_handler(func=lambda message: True)
def main(message):
    chat_id = message.chat.id
    with users_lock:
        if chat_id in rate_limit and time.time() - rate_limit[chat_id] < 1:
            bot.reply_to(message, "Please wait a moment before sending another request.")
            return
        rate_limit[chat_id] = time.time()

    with file_lock:
        with open("queries.txt", "a") as queries:
            print(f"{message.from_user.username} ({message.chat.id}): {message.text}")
            queries.write(f"{message.from_user.username} ({message.chat.id}): {message.text}\n")

    set_user_data(chat_id, message.text, 0, 0)
    url, total = get_url(message.text, 0, 0)
    if url:
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("◄", callback_data="prev"), InlineKeyboardButton("►", callback_data="next"))
        try:
            sent_message = bot.send_photo(message.chat.id, url, reply_markup=markup)
            set_user_data(chat_id, message.text, 0, 0, sent_message.message_id)
        except Exception:
            bot.reply_to(message, "Failed to load image.")
    else:
        bot.reply_to(message, "No images found.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    with users_lock:
        if chat_id in rate_limit and time.time() - rate_limit[chat_id] < 1:
            bot.answer_callback_query(call.id, "Please wait a moment before sending another request.", show_alert=True)
            return
        rate_limit[chat_id] = time.time()

    user_data = get_user_data(chat_id)
    if not user_data:
        bot.answer_callback_query(call.id, "Session expired. Please start a new search.", show_alert=True)
        return

    q = user_data["q"]
    id = user_data["id"]
    p = user_data["p"]
    message_id = user_data["message_id"]

    if call.data == "next":
        id += 1
        url, total = get_url(q, id, p)
        if url is None:
            if total == 0:
                bot.answer_callback_query(call.id, "No more images", show_alert=True)
                return
            p += 1
            id = 0
            url, total = get_url(q, id, p)
            if url is None:
                bot.answer_callback_query(call.id, "No more images", show_alert=True)
                p -= 1
                return
    elif call.data == "prev":
        id -= 1
        if id < 0:
            if p > 0:
                p -= 1
                _, total = get_url(q, 0, p)
                id = total - 1 if total > 0 else 0
                url, _ = get_url(q, id, p)
                if url is None:
                    bot.answer_callback_query(call.id, "No more images", show_alert=True)
                    return
            else:
                bot.answer_callback_query(call.id, "This is the first image", show_alert=True)
                id = 0
                return
        else:
            url, _ = get_url(q, id, p)
            if url is None:
                bot.answer_callback_query(call.id, "Something went wrong", show_alert=True)
                return

    set_user_data(chat_id, q, id, p, message_id)

    try:
        bot.edit_message_media(
            media=telebot.types.InputMediaPhoto(url),
            chat_id=call.message.chat.id,
            message_id=message_id,
            reply_markup=call.message.reply_markup)
        bot.answer_callback_query(call.id)
    except Exception:
        bot.answer_callback_query(call.id, "Failed to load image.", show_alert=True)

print("the bot is started!")
bot.infinity_polling()
