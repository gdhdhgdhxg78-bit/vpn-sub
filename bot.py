import logging
import sqlite3
import os
import json
from datetime import datetime, date

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== تنظیمات ====================
BOT_TOKEN        = "8757886517:AAEjQkxtSIm3-Hg1pzdwQlSlvkJrP0wXQ4M"
SUPER_ADMIN_IDS  = [8478999016, 6189730344]   # ادمین‌های اصلی - دسترسی کامل
COINS_PER_REFERRAL  = 1
COINS_TO_GET_CONFIG = 3

_BASE_DIR   = "/storage/emulated/0/coinsfil" if os.path.exists("/storage/emulated/0") else os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(_BASE_DIR, "bot.db")
STATUS_FILE = os.path.join(_BASE_DIR, "bot_status.json")

ALL_PERMS = ["toggle_bot", "stats", "users", "add_config", "broadcast", "coins", "channels", "support_id", "texts", "buttons"]
PERM_NAMES = {
    "toggle_bot": "🔴🟢 خاموش/روشن ربات",
    "stats":      "📊 آمار کلی",
    "users":      "👥 لیست کاربران",
    "add_config": "➕ افزودن کانفیگ",
    "broadcast":  "📢 ارسال همگانی",
    "coins":      "💰 مدیریت سکه",
    "channels":   "📡 مدیریت چنل‌ها",
    "support_id": "🛟 تنظیم پشتیبانی",
    "texts":      "✏️ مدیریت متن‌ها",
    "buttons":    "🔘 مدیریت دکمه‌ها",
}

# ==================== کانفیگ ====================
DEFAULT_TEXTS = {
    "start": "🔐 با هر بار دعوت یه دوست = 1 سکه 🪙\n🎁 با 3 سکه → یه اتصال رایگان دریافت کن!\n━━━━━━━━━━━━━━━\n\nاز منوی پایین شروع کن 👇",
    "join_required": "❌ برای استفاده از ربات باید در کانال ما عضو بشی:",
    "join_required_short": "❌ برای استفاده باید عضو کانال باشی:",
    "not_joined": "❌ هنوز عضو نشدی!",
    "help": "⚠️ راهنمای استفاده از ربات\n━━━━━━━━━━━━━━━\n\n1️⃣ لینک دعوت خودتو از بخش «لینک دعوت» بگیر\n2️⃣ لینکتو برای دوستات بفرست\n3️⃣ به ازای هر دوست = 1 سکه 🪙 می‌گیری\n4️⃣ با 3 سکه → یه اتصال رایگان دریافت کن!\n\n━━━━━━━━━━━━━━━\n⚠️ توجه:\n• کانفیگ‌ها محدودن\n• هر کانفیگ فقط یه بار قابل استفاده‌ست\n• در صورت سوء استفاده، حساب مسدود میشه",
    "support": "🟢 پشتیبانی\n━━━━━━━━━━━━━━━\n\n📌 در چه مواردی کمک می‌کنیم:\n• مشکل در دریافت کانفیگ\n• مشکل در لینک دعوت\n• اشکال در عملکرد ربات\n\n❌ موارد پشتیبانی نمی‌شه:\n• درخواست کانفیگ رایگان بدون سکه\n• مشکلات اینترنت شخصی\n\n━━━━━━━━━━━━━━━\nنوع درخواست خودت رو انتخاب کن 👇",
    "sponsor_prompt": "💼 درخواست اسپانسر\n━━━━━━━━━━━━━━━\n\nپیام خود را برای اسپانسر شدن بنویسید:\n\n💡 لطفاً ذکر کنید:\n• معرفی کانال/گروه\n• تعداد اعضا\n• نوع همکاری\n\nپیام خود را ارسال کنید 👇",
    "support_question_prompt": "❓ سوال / مشکل\n━━━━━━━━━━━━━━━\n\nسوال یا مشکل خود را بنویسید 👇",
}

TEXT_NAMES = {
    "start": "متن شروع / منوی اصلی",
    "join_required": "متن الزام عضویت",
    "join_required_short": "متن الزام عضویت کوتاه",
    "not_joined": "متن هنوز عضو نشدی",
    "help": "متن راهنما",
    "support": "متن پشتیبانی",
    "sponsor_prompt": "متن درخواست اسپانسر",
    "support_question_prompt": "متن سوال / مشکل",
}

DEFAULT_BUTTONS = {
    "main_get_config": "اتصال رایگان 🤩",
    "main_account": "حساب من 👤",
    "main_referral": "لینک دعوت 🔗",
    "main_support": "پشتیبانی 🟢",
    "main_help": "راهنما 📖",
    "main_admin": "🛠 پنل مدیریت",
    "admin_toggle_on": "🟢 ربات روشن | خاموش کن",
    "admin_toggle_off": "🔴 ربات خاموش | روشن کن",
    "admin_support": "🛟 پشتیبانی:",
    "admin_stats": "📊 آمار کلی",
    "admin_users": "👥 لیست کاربران",
    "admin_add_config": "➕ افزودن کانفیگ",
    "admin_broadcast": "📢 ارسال همگانی",
    "admin_addcoins": "💰 انتقال سکه",
    "admin_subcoins": "➖ کسر سکه",
    "admin_channels": "📡 مدیریت چنل‌ها",
    "admin_texts": "✏️ مدیریت متن‌ها",
    "admin_buttons": "🔘 مدیریت دکمه‌ها",
    "admin_manage_admins": "👤 مدیریت ادمین‌ها",
    "back_main": "🔙 بازگشت",
    "back_panel": "🔙 بازگشت به پنل",
    "cancel": "❌ لغو",
    "cancel_action": "❌ انصراف",
    "check_join": "✅ عضو شدم",
    "join_channel": "عضویت در",
    "ban_user": "🚫 بن کاربر",
    "unban_user": "🔓 آنبن کاربر",
    "msg_user": "✉️ پیام به کاربر",
    "send_coin_user": "➕ فرستادن سکه",
    "sub_coin_user": "➖ کسر سکه",
    "delete_admin": "🗑 حذف این ادمین",
    "get_referral": "🔗 دریافت لینک رفرال",
    "support_sponsor": "💼 اسپانسر",
    "support_question": "❓ سوالات غیر اسپانسری",
    "bot_off": "🔴 خاموش",
    "bot_on": "🟢 روشن",
    "prev_page": "◀️ قبلی",
    "next_page": "بعدی ▶️",
    "add_channel": "➕ اضافه کردن چنل",
    "delete_channel": "🗑 حذف",
    "add_admin": "➕ اضافه کردن ادمین",
}

BUTTON_NAMES = {
    "main_get_config": "دکمه اتصال رایگان",
    "main_account": "دکمه حساب من",
    "main_referral": "دکمه لینک دعوت",
    "main_support": "دکمه پشتیبانی",
    "main_help": "دکمه راهنما",
    "main_admin": "دکمه پنل مدیریت",
    "admin_toggle_on": "دکمه وضعیت ربات وقتی روشن است",
    "admin_toggle_off": "دکمه وضعیت ربات وقتی خاموش است",
    "admin_support": "دکمه تنظیم پشتیبانی",
    "admin_stats": "دکمه آمار کلی",
    "admin_users": "دکمه لیست کاربران",
    "admin_add_config": "دکمه افزودن کانفیگ",
    "admin_broadcast": "دکمه ارسال همگانی",
    "admin_addcoins": "دکمه انتقال سکه",
    "admin_subcoins": "دکمه کسر سکه",
    "admin_channels": "دکمه مدیریت چنل‌ها",
    "admin_texts": "دکمه مدیریت متن‌ها",
    "admin_buttons": "دکمه مدیریت دکمه‌ها",
    "admin_manage_admins": "دکمه مدیریت ادمین‌ها",
    "back_main": "دکمه بازگشت",
    "back_panel": "دکمه بازگشت به پنل",
    "cancel": "دکمه لغو",
    "cancel_action": "دکمه انصراف",
    "check_join": "دکمه عضو شدم",
    "join_channel": "دکمه عضویت در کانال",
    "ban_user": "دکمه بن کاربر",
    "unban_user": "دکمه آنبن کاربر",
    "msg_user": "دکمه پیام به کاربر",
    "send_coin_user": "دکمه فرستادن سکه",
    "sub_coin_user": "دکمه کسر سکه از کاربر",
    "delete_admin": "دکمه حذف ادمین",
    "get_referral": "دکمه دریافت لینک رفرال",
    "support_sponsor": "دکمه اسپانسر",
    "support_question": "دکمه سوالات غیر اسپانسری",
    "bot_off": "دکمه خاموش کردن",
    "bot_on": "دکمه روشن کردن",
    "prev_page": "دکمه صفحه قبلی",
    "next_page": "دکمه صفحه بعدی",
    "add_channel": "دکمه اضافه کردن چنل",
    "delete_channel": "دکمه حذف چنل",
    "add_admin": "دکمه اضافه کردن ادمین",
}

def load_config() -> dict:
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["texts"] = {**DEFAULT_TEXTS, **data.get("texts", {})}
                data["buttons"] = {**DEFAULT_BUTTONS, **data.get("buttons", {})}
                return data
    except:
        pass
    return {"enabled": True, "support_id": "", "channels": ["@LyricPixelArt"], "sub_admins": {}, "texts": DEFAULT_TEXTS.copy(), "buttons": DEFAULT_BUTTONS.copy()}

def save_config(data: dict):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

_config      = load_config()
BOT_ENABLED  = _config.get("enabled", True)
SUPPORT_ID   = _config.get("support_id", "")
CHANNEL_IDS: list = _config.get("channels", ["@LyricPixelArt"])
SUB_ADMINS: dict  = _config.get("sub_admins", {})   # {str(user_id): {perm: bool}}
BOT_TEXTS: dict    = {**DEFAULT_TEXTS, **_config.get("texts", {})}
BOT_BUTTONS: dict  = {**DEFAULT_BUTTONS, **_config.get("buttons", {})}

def get_bot_text(key: str) -> str:
    return BOT_TEXTS.get(key, DEFAULT_TEXTS.get(key, ""))

def save_bot_text(key: str, value: str):
    BOT_TEXTS[key] = value
    cfg = load_config()
    cfg["texts"] = BOT_TEXTS
    save_config(cfg)

def get_button_text(key: str) -> str:
    return BOT_BUTTONS.get(key, DEFAULT_BUTTONS.get(key, ""))

def save_button_text(key: str, value: str):
    BOT_BUTTONS[key] = value
    cfg = load_config()
    cfg["buttons"] = BOT_BUTTONS
    save_config(cfg)

# ==================== توابع دسترسی ====================
def is_any_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS or str(user_id) in SUB_ADMINS

def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS

def has_perm(user_id: int, perm: str) -> bool:
    if user_id in SUPER_ADMIN_IDS:
        return True
    perms = SUB_ADMINS.get(str(user_id), {})
    return perms.get(perm, False)

# ==================== FSM States ====================
class AdminStates(StatesGroup):
    waiting_config_count = State()
    waiting_config_item  = State()
    broadcast            = State()
    add_coins_id         = State()
    add_coins_amount     = State()
    sub_coins_id         = State()
    sub_coins_amount     = State()
    msg_user_text        = State()
    set_support_id       = State()
    add_channel          = State()
    add_admin_id         = State()
    edit_bot_text        = State()
    edit_button_text     = State()

class UserStates(StatesGroup):
    sponsor_msg  = State()
    support_msg  = State()

# ==================== دیتابیس ====================
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        coins INTEGER DEFAULT 0, referred_by INTEGER DEFAULT NULL,
        join_date TEXT, is_banned INTEGER DEFAULT 0, configs_received INTEGER DEFAULT 0,
        referral_credited INTEGER DEFAULT 0)""")
    try:
        c.execute("ALTER TABLE users ADD COLUMN referral_credited INTEGER DEFAULT 0")
    except:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
        is_used INTEGER DEFAULT 0, used_by INTEGER DEFAULT NULL, used_at TEXT DEFAULT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)""")
    for key in ("total_users", "configs_given", "total_referrals"):
        c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, 0)", (key,))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone(); conn.close(); return row

def add_user(user_id, username, full_name, referred_by=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users
        (user_id, username, full_name, coins, referred_by, join_date, is_banned, configs_received)
        VALUES (?, ?, ?, 0, ?, ?, 0, 0)""",
        (user_id, username, full_name, referred_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    inserted = c.rowcount; conn.commit(); conn.close(); return inserted == 1

def get_all_users_paginated(page, per_page=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, coins, is_banned, configs_received FROM users LIMIT ? OFFSET ?",
              (per_page, page * per_page))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]; conn.close(); return rows, total

def get_user_detail(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT user_id, username, full_name, coins, is_banned, configs_received,
               (SELECT COUNT(*) FROM users WHERE referred_by = ?) FROM users WHERE user_id = ?""",
               (user_id, user_id))
    row = c.fetchone(); conn.close(); return row

def update_coins(user_id, delta):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?", (delta, user_id))
    conn.commit(); conn.close()

def ban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    conn.commit(); conn.close()

def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit(); conn.close()

def get_stat(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM stats WHERE key = ?", (key,))
    row = c.fetchone(); conn.close(); return row[0] if row else 0

def increment_stat(key, amount=1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, 0)", (key,))
    c.execute("UPDATE stats SET value = value + ? WHERE key = ?", (amount, key))
    conn.commit(); conn.close()

def get_free_config():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, content FROM configs WHERE is_used = 0 LIMIT 1")
    row = c.fetchone(); conn.close(); return row

def mark_config_used(config_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE configs SET is_used=1, used_by=?, used_at=? WHERE id=?",
              (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config_id))
    c.execute("UPDATE users SET configs_received=configs_received+1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()

def add_config(content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO configs (content) VALUES (?)", (content.strip(),))
    conn.commit(); conn.close()

def get_referral_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
    count = c.fetchone()[0]; conn.close(); return count

def credit_referral(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT referred_by, referral_credited FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row or not row[0] or row[1]:
        conn.close()
        return None
    referred_by = row[0]
    ref_user_row = c.execute("SELECT is_banned FROM users WHERE user_id = ?", (referred_by,)).fetchone()
    if not ref_user_row or ref_user_row[0]:
        conn.close()
        return None
    c.execute("UPDATE users SET referral_credited = 1 WHERE user_id = ?", (user_id,))
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (COINS_PER_REFERRAL, referred_by))
    conn.commit()
    conn.close()
    increment_stat("total_referrals")
    return referred_by

def get_configs_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM configs WHERE is_used = 0")
    free = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs")
    total = c.fetchone()[0]; conn.close(); return free, total

def get_today_stats():
    today = date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (today + "%",))
    new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs WHERE used_at LIKE ?", (today + "%",))
    configs_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM configs WHERE is_used = 1")
    total_used = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE coins < ? AND is_banned = 0", (COINS_TO_GET_CONFIG,))
    waiting = c.fetchone()[0]; conn.close()
    return new_today, configs_today, total_used, waiting

# ==================== بررسی عضویت ====================
async def check_membership(user_id: int, bot: Bot) -> bool:
    for channel in CHANNEL_IDS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logger.warning(f"خطا در بررسی عضویت {channel}: {e}")
            return False
    return True

# ==================== کیبوردها ====================
def main_keyboard(show_admin_btn: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=get_button_text("main_get_config"), callback_data="get_config", style=ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton(text=get_button_text("main_account"), callback_data="my_account", style=ButtonStyle.DANGER),
            InlineKeyboardButton(text=get_button_text("main_referral"), callback_data="referral", style=ButtonStyle.DANGER),
        ],
        [
            InlineKeyboardButton(text=get_button_text("main_support"), callback_data="support", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton(text=get_button_text("main_help"), callback_data="help", style=ButtonStyle.SUCCESS),
        ],
    ]
    if show_admin_btn:
        rows.append([InlineKeyboardButton(text=get_button_text("main_admin"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if has_perm(user_id, "toggle_bot"):
        status_text = get_button_text("admin_toggle_on") if BOT_ENABLED else get_button_text("admin_toggle_off")
        rows.append([InlineKeyboardButton(text=status_text, callback_data="admin_toggle_bot")])
    sup = SUPPORT_ID if SUPPORT_ID else "تنظیم نشده"
    if has_perm(user_id, "support_id"):
        rows.append([InlineKeyboardButton(text=f"{get_button_text('admin_support')} {sup}", callback_data="admin_set_support")])
    if has_perm(user_id, "stats"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_stats"), callback_data="admin_stats")])
    if has_perm(user_id, "users"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_users"), callback_data="admin_users_0")])
    row2 = []
    if has_perm(user_id, "add_config"):
        row2.append(InlineKeyboardButton(text=get_button_text("admin_add_config"), callback_data="admin_add_config"))
    if has_perm(user_id, "broadcast"):
        row2.append(InlineKeyboardButton(text=get_button_text("admin_broadcast"), callback_data="admin_broadcast"))
    if row2:
        rows.append(row2)
    row3 = []
    if has_perm(user_id, "coins"):
        row3.append(InlineKeyboardButton(text=get_button_text("admin_addcoins"), callback_data="admin_addcoins"))
        row3.append(InlineKeyboardButton(text=get_button_text("admin_subcoins"), callback_data="admin_subcoins"))
    if row3:
        rows.append(row3)
    if has_perm(user_id, "channels"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_channels"), callback_data="admin_channels")])
    if has_perm(user_id, "texts"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_texts"), callback_data="admin_texts")])
    if has_perm(user_id, "buttons"):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_buttons"), callback_data="admin_buttons_0")])
    if is_super_admin(user_id):
        rows.append([InlineKeyboardButton(text=get_button_text("admin_manage_admins"), callback_data="admin_manage_admins")])
    rows.append([InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def bot_texts_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, name in TEXT_NAMES.items():
        rows.append([InlineKeyboardButton(text=name, callback_data=f"admin_edittext_{key}")])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def bot_buttons_keyboard(page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    items = list(BUTTON_NAMES.items())
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    rows = []
    for key, name in items[start:start + per_page]:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"admin_editbutton_{key}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_buttons_{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_buttons_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def join_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in CHANNEL_IDS:
        buttons.append([InlineKeyboardButton(text=f"{get_button_text('join_channel')} {ch}", url=f"https://t.me/{ch.lstrip('@')}", style=ButtonStyle.DANGER)])
    buttons.append([InlineKeyboardButton(text=get_button_text("check_join"), callback_data="check_join", style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def user_detail_keyboard(uid, is_banned) -> InlineKeyboardMarkup:
    ban_btn = (InlineKeyboardButton(text=get_button_text("unban_user"), callback_data=f"admin_unban_{uid}")
               if is_banned else InlineKeyboardButton(text=get_button_text("ban_user"), callback_data=f"admin_ban_{uid}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [InlineKeyboardButton(text=get_button_text("msg_user"), callback_data=f"admin_msguser_{uid}")],
        [InlineKeyboardButton(text=get_button_text("send_coin_user"), callback_data=f"admin_addcoin_{uid}"),
         InlineKeyboardButton(text=get_button_text("sub_coin_user"), callback_data=f"admin_subcoin_{uid}")],
        [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="admin_users_0")],
    ])

def support_action_keyboard(uid, is_banned) -> InlineKeyboardMarkup:
    ban_btn = (InlineKeyboardButton(text=get_button_text("unban_user"), callback_data=f"admin_unban_{uid}")
               if is_banned else InlineKeyboardButton(text=get_button_text("ban_user"), callback_data=f"admin_ban_{uid}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [InlineKeyboardButton(text=get_button_text("msg_user"), callback_data=f"admin_msguser_{uid}")],
        [InlineKeyboardButton(text=get_button_text("send_coin_user"), callback_data=f"admin_addcoin_{uid}"),
         InlineKeyboardButton(text=get_button_text("sub_coin_user"), callback_data=f"admin_subcoin_{uid}")],
    ])

def sub_admin_perms_keyboard(target_id: int) -> InlineKeyboardMarkup:
    perms = SUB_ADMINS.get(str(target_id), {})
    rows = []
    for perm, name in PERM_NAMES.items():
        has = perms.get(perm, False)
        icon = "✅" if has else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {name}",
            callback_data=f"admin_toggleperm_{target_id}_{perm}"
        )])
    rows.append([InlineKeyboardButton(text=get_button_text("delete_admin"), callback_data=f"admin_removeadmin_{target_id}", style=ButtonStyle.DANGER)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_main"), callback_data="admin_manage_admins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

dp  = Dispatcher(storage=MemoryStorage())
bot: Bot = None

# ==================== /start ====================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1].split("_")[1])
            if referred_by == user.id: referred_by = None
        except: pass

    is_new = add_user(user.id, user.username, user.full_name, referred_by)
    if is_new: increment_stat("total_users")

    if not BOT_ENABLED and not is_any_admin(user.id):
        await message.answer("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return

    is_member = await check_membership(user.id, bot)
    if not is_member:
        await message.answer(get_bot_text("join_required"), reply_markup=join_keyboard()); return

    db_user = get_user(user.id)
    if db_user and db_user[6]:
        await message.answer("⛔️ حساب شما مسدود شده است."); return

    referred_by_credited = credit_referral(user.id)
    if referred_by_credited:
        try:
            await bot.send_message(referred_by_credited,
                f"🎉 یه نفر با لینک دعوت تو وارد ربات شد و عضو کانال شد!\n+{COINS_PER_REFERRAL} سکه به حسابت اضافه شد 🪙")
        except: pass

    await message.answer(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(user.id)))

# ==================== باز کردن پنل ادمین ====================
@dp.callback_query(F.data == "open_admin_panel")
async def cb_open_admin_panel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    if not is_any_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.message.edit_text("👑 پنل مدیریت", reply_markup=admin_keyboard(call.from_user.id))

# ==================== check_join ====================
@dp.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not BOT_ENABLED and not is_any_admin(call.from_user.id):
        await call.message.edit_text("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return
    is_member = await check_membership(call.from_user.id, bot)
    if not is_member:
        await call.message.edit_text(get_bot_text("not_joined"), reply_markup=join_keyboard()); return
    db_user = get_user(call.from_user.id)
    if db_user and db_user[6]:
        await call.message.edit_text("⛔️ حساب شما مسدود شده است."); return

    referred_by = credit_referral(call.from_user.id)
    if referred_by:
        try:
            await bot.send_message(referred_by,
                f"🎉 یه نفر با لینک دعوت تو وارد ربات شد و عضو کانال شد!\n+{COINS_PER_REFERRAL} سکه به حسابت اضافه شد 🪙")
        except: pass

    await call.message.edit_text(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(call.from_user.id)))

# ==================== back_main ====================
@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(get_bot_text("start"), reply_markup=main_keyboard(show_admin_btn=is_any_admin(call.from_user.id)))

# ==================== get_config ====================
@dp.callback_query(F.data == "get_config")
async def cb_get_config(call: CallbackQuery):
    await call.answer()
    user = call.from_user
    if not BOT_ENABLED and not is_any_admin(user.id):
        await call.message.edit_text("🔴 ربات درحال بروزرسانی هست\nبزودی روشن می‌شود 🙏"); return
    is_member = await check_membership(user.id, bot)
    if not is_member:
        await call.message.edit_text(get_bot_text("join_required_short"), reply_markup=join_keyboard()); return
    db_user = get_user(user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    if db_user[6]:
        await call.answer("⛔️ حساب شما مسدود است.", show_alert=True); return
    coins = db_user[3]
    if coins < COINS_TO_GET_CONFIG:
        needed = COINS_TO_GET_CONFIG - coins
        await call.message.edit_text(
            f"❌ سکه کافی نداری رفیق!\n\n🪙 سکه فعلی تو: {coins}\n🎯 نیاز داری: {COINS_TO_GET_CONFIG} سکه\n📉 کمبود داری: {needed} سکه\n\n👥 دوستاتو دعوت کن!\nهر دعوت = {COINS_PER_REFERRAL} سکه 🪙",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("get_referral"), callback_data="referral", style=ButtonStyle.PRIMARY)],
                [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")],
            ])); return
    config = get_free_config()
    if not config:
        await call.message.edit_text("😔 متأسفانه در حال حاضر کانفیگ موجود نیست.\nکمی صبر کن!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]])); return
    update_coins(user.id, -COINS_TO_GET_CONFIG)
    mark_config_used(config[0], user.id)
    increment_stat("configs_given")
    await call.message.edit_text(
        f"✅ اتصال رایگان تو اینه رفیق!\n\n<code>{config[1]}</code>\n\n🪙 {COINS_TO_GET_CONFIG} سکه از حسابت کسر شد.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== referral ====================
@dp.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery):
    await call.answer()
    db_user = get_user(call.from_user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    ref_count = get_referral_count(call.from_user.id)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{call.from_user.id}"
    await call.message.edit_text(
        f"🔗 لینک دعوت تو:\n\n<code>{ref_link}</code>\n\n━━━━━━━━━━━━━━━\n"
        f"👥 تعداد دعوت‌شده‌ها: {ref_count} نفر\n🪙 سکه‌های فعلی: {db_user[3]}\n"
        f"🎯 نیاز داری: {COINS_TO_GET_CONFIG} سکه\n━━━━━━━━━━━━━━━\n\n"
        f"هر دعوت = {COINS_PER_REFERRAL} سکه 🪙\nلینکتو برای دوستات بفرست!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== my_account ====================
@dp.callback_query(F.data == "my_account")
async def cb_my_account(call: CallbackQuery):
    await call.answer()
    db_user = get_user(call.from_user.id)
    if not db_user:
        await call.answer("ابتدا /start بزن.", show_alert=True); return
    ref_count = get_referral_count(call.from_user.id)
    status = "🚫 مسدود" if db_user[6] else "✅ فعال"
    await call.message.edit_text(
        f"👤 حساب من\n━━━━━━━━━━━━━━━\n🆔 آیدی: <code>{db_user[0]}</code>\n📛 نام: {db_user[2]}\n"
        f"🪙 سکه: {db_user[3]}\n👥 زیرمجموعه: {ref_count} نفر\n"
        f"📉 سکه مصرف‌شده: {db_user[7]*COINS_TO_GET_CONFIG}\n🎁 اتصال دریافت‌شده: {db_user[7]}\n"
        f"📌 وضعیت: {status}\n━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== help ====================
@dp.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        get_bot_text("help"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== پشتیبانی ====================
@dp.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        get_bot_text("support"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("support_sponsor"), callback_data="support_sponsor", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text=get_button_text("support_question"), callback_data="support_question", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")],
        ]))

@dp.callback_query(F.data == "support_sponsor")
async def cb_support_sponsor(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.sponsor_msg)
    await call.message.edit_text(
        get_bot_text("sponsor_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="back_main")]]))

@dp.message(UserStates.sponsor_msg)
async def hdl_sponsor_msg(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_user = get_user(user.id)
    coins = db_user[3] if db_user else 0
    is_banned = db_user[6] if db_user else 0
    username = f"@{user.username}" if user.username else "ندارد"
    admin_text = (f"💼 درخواست اسپانسر جدید\n━━━━━━━━━━━━━━━\n\n"
                  f"👤 نام: {user.full_name}\n📛 یوزرنیم: {username}\n"
                  f"🆔 آیدی: <code>{user.id}</code>\n🪙 سکه: {coins}\n"
                  f"━━━━━━━━━━━━━━━\n\n📝 پیام اسپانسر:\n{message.text}")
    for aid in SUPER_ADMIN_IDS:
        try: await bot.send_message(aid, admin_text, parse_mode=ParseMode.HTML, reply_markup=support_action_keyboard(user.id, is_banned))
        except: pass
    await message.answer("✅ درخواست اسپانسر شما ارسال شد!\nبه زودی با شما تماس می‌گیریم 🙏",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

@dp.callback_query(F.data == "support_question")
async def cb_support_question(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.support_msg)
    await call.message.edit_text(get_bot_text("support_question_prompt"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="back_main")]]))

@dp.message(UserStates.support_msg)
async def hdl_support_msg(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db_user = get_user(user.id)
    coins = db_user[3] if db_user else 0
    is_banned = db_user[6] if db_user else 0
    username = f"@{user.username}" if user.username else "ندارد"
    admin_text = (f"❓ سوال / مشکل جدید\n━━━━━━━━━━━━━━━\n\n"
                  f"👤 نام: {user.full_name}\n📛 یوزرنیم: {username}\n"
                  f"🆔 آیدی: <code>{user.id}</code>\n🪙 سکه: {coins}\n"
                  f"━━━━━━━━━━━━━━━\n\n📝 پیام:\n{message.text}")
    for aid in SUPER_ADMIN_IDS:
        try: await bot.send_message(aid, admin_text, parse_mode=ParseMode.HTML, reply_markup=support_action_keyboard(user.id, is_banned))
        except: pass
    await message.answer("✅ پیام شما ارسال شد!\nبه زودی پاسخ می‌گیرید 🙏",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_main"), callback_data="back_main")]]))

# ==================== خاموش/روشن ====================
@dp.callback_query(F.data == "admin_toggle_bot")
async def cb_toggle_bot(call: CallbackQuery):
    if not has_perm(call.from_user.id, "toggle_bot"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    status_text = "🟢 روشن" if BOT_ENABLED else "🔴 خاموش"
    await call.message.edit_text(f"⚙️ وضعیت ربات\n\nوضعیت فعلی: {status_text}\n\nیکی رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("bot_off"), callback_data="admin_bot_off")],
            [InlineKeyboardButton(text=get_button_text("bot_on"), callback_data="admin_bot_on")],
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")],
        ]))

@dp.callback_query(F.data == "admin_bot_on")
async def cb_bot_on(call: CallbackQuery):
    global BOT_ENABLED
    if not has_perm(call.from_user.id, "toggle_bot"): return
    await call.answer()
    BOT_ENABLED = True
    cfg = load_config(); cfg["enabled"] = True; save_config(cfg)
    await call.message.edit_text("✅ ربات روشن شد!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

@dp.callback_query(F.data == "admin_bot_off")
async def cb_bot_off(call: CallbackQuery):
    global BOT_ENABLED
    if not has_perm(call.from_user.id, "toggle_bot"): return
    await call.answer()
    BOT_ENABLED = False
    cfg = load_config(); cfg["enabled"] = False; save_config(cfg)
    await call.message.edit_text("🔴 ربات خاموش شد!\nکاربران پیام «درحال بروزرسانی» می‌بینن.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

# ==================== آمار ====================
@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not has_perm(call.from_user.id, "stats"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    total_users = get_stat("total_users")
    free_configs, _ = get_configs_count()
    new_today, configs_today, total_used, waiting = get_today_stats()
    bot_status = "🟢 روشن" if BOT_ENABLED else "🔴 خاموش"
    sup = SUPPORT_ID if SUPPORT_ID else "تنظیم نشده"
    await call.message.edit_text(
        f"وضعیت ربات: {bot_status}\nآیدی پشتیبانی فعلی: {sup}\n\n📊 آمار کلی:\n"
        f"👥 تعداد کل کاربران: {total_users}\n🔥 کاربران فعال امروز: {new_today}\n"
        f"🌱 ورودی‌های جدید امروز: {new_today}\n\n✅ کانفیگ های موجود فعلی: {free_configs}\n"
        f"🟢 کانفیگ‌های مصرف‌شده امروز: {configs_today}\n🔴 کل کانفیگ‌های منقضی/مصرف‌شده: {total_used}\n\n"
        f"⏳ کاربران در انتظار کانفیگ: {waiting}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]]))

# ==================== مدیریت متن‌ها ====================
@dp.callback_query(F.data == "admin_texts")
async def cb_admin_texts(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_perm(call.from_user.id, "texts"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "✏️ مدیریت متن‌ها\n\nیکی از متن‌ها را انتخاب کن تا متن فعلی را ببینی و متن جدید بفرستی:",
        reply_markup=bot_texts_keyboard())

@dp.callback_query(F.data.startswith("admin_edittext_"))
async def cb_admin_edit_text(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "texts"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    key = call.data.replace("admin_edittext_", "")
    if key not in TEXT_NAMES:
        await call.answer("این متن پیدا نشد.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.edit_bot_text)
    await state.update_data(text_key=key)
    await call.message.edit_text(
        f"✏️ تغییر {TEXT_NAMES[key]}\n\nمتن فعلی:\n\n{get_bot_text(key)}\n\n━━━━━━━━━━━━━━━\nمتن جدید را همینجا بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="admin_texts")]]))

@dp.message(AdminStates.edit_bot_text)
async def hdl_admin_edit_text(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "texts"):
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("text_key")
    if key not in TEXT_NAMES:
        await state.clear()
        await message.answer("❌ خطا در انتخاب متن.", reply_markup=admin_keyboard(message.from_user.id))
        return
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("❌ متن خالی قابل ذخیره نیست. متن جدید را بفرست:")
        return
    save_bot_text(key, new_text)
    await state.clear()
    await message.answer(
        f"✅ {TEXT_NAMES[key]} ذخیره شد.\n\nمتن جدید:\n\n{new_text}",
        reply_markup=bot_texts_keyboard())

# ==================== مدیریت دکمه‌ها ====================
@dp.callback_query(F.data.startswith("admin_buttons_"))
async def cb_admin_buttons(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not has_perm(call.from_user.id, "buttons"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    try:
        page = int(call.data.split("_")[-1])
    except:
        page = 0
    await call.message.edit_text(
        "🔘 مدیریت دکمه‌های شیشه‌ای\n\nیکی از دکمه‌ها را انتخاب کن تا اسم فعلی را ببینی و اسم جدید بفرستی:",
        reply_markup=bot_buttons_keyboard(page))

@dp.callback_query(F.data.startswith("admin_editbutton_"))
async def cb_admin_edit_button(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "buttons"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    key = call.data.replace("admin_editbutton_", "")
    if key not in BUTTON_NAMES:
        await call.answer("این دکمه پیدا نشد.", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.edit_button_text)
    await state.update_data(button_key=key)
    await call.message.edit_text(
        f"🔘 تغییر {BUTTON_NAMES[key]}\n\nاسم فعلی:\n\n{get_button_text(key)}\n\n━━━━━━━━━━━━━━━\nاسم جدید دکمه را بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel_action"), callback_data="admin_buttons_0")]]))

@dp.message(AdminStates.edit_button_text)
async def hdl_admin_edit_button(message: Message, state: FSMContext):
    if not has_perm(message.from_user.id, "buttons"):
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("button_key")
    if key not in BUTTON_NAMES:
        await state.clear()
        await message.answer("❌ خطا در انتخاب دکمه.", reply_markup=admin_keyboard(message.from_user.id))
        return
    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("❌ اسم خالی قابل ذخیره نیست. اسم جدید دکمه را بفرست:")
        return
    save_button_text(key, new_text)
    await state.clear()
    await message.answer(
        f"✅ {BUTTON_NAMES[key]} ذخیره شد.\n\nاسم جدید:\n\n{new_text}",
        reply_markup=bot_buttons_keyboard())

# ==================== لیست کاربران ====================
@dp.callback_query(F.data.startswith("admin_users_"))
async def cb_admin_users(call: CallbackQuery):
    if not has_perm(call.from_user.id, "users"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    page = int(call.data.split("_")[-1])
    users, total = get_all_users_paginated(page, 20)
    if not users:
        await call.message.edit_text("هیچ کاربری یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")]])); return
    buttons = []
    for u in users:
        banned = "🚫" if u[3] else ""
        buttons.append([InlineKeyboardButton(text=f"{banned}{u[1]} | 🪙{u[2]}", callback_data=f"admin_userdetail_{u[0]}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text=get_button_text("prev_page"), callback_data=f"admin_users_{page-1}"))
    if (page+1)*20 < total: nav.append(InlineKeyboardButton(text=get_button_text("next_page"), callback_data=f"admin_users_{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(f"👥 لیست کاربران (صفحه {page+1})\nکل: {total} کاربر",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("admin_userdetail_"))
async def cb_user_detail_view(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    u = get_user_detail(target_id)
    if not u:
        await call.answer("کاربر یافت نشد.", show_alert=True); return
    status = "🚫 مسدود" if u[4] else "✅ فعال"
    await call.message.edit_text(
        f"👤 جزئیات کاربر\n━━━━━━━━━━━━━━━\n🆔 آیدی: <code>{u[0]}</code>\n"
        f"📛 یوزرنیم: @{u[1] or 'ندارد'}\n👤 نام: {u[2]}\n🪙 سکه: {u[3]}\n"
        f"📌 وضعیت: {status}\n🎁 کانفیگ دریافتی: {u[5]}\n👥 زیرمجموعه: {u[6]}\n━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML, reply_markup=user_detail_keyboard(u[0], u[4]))

@dp.callback_query(F.data.startswith("admin_ban_"))
async def cb_ban(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    target_id = int(call.data.split("_")[-1])
    ban_user(target_id)
    await call.answer(f"✅ کاربر {target_id} بن شد.", show_alert=True)
    u = get_user_detail(target_id)
    if u:
        try: await call.message.edit_reply_markup(reply_markup=user_detail_keyboard(u[0], u[4]))
        except:
            try: await call.message.edit_reply_markup(reply_markup=support_action_keyboard(u[0], u[4]))
            except: pass

@dp.callback_query(F.data.startswith("admin_unban_"))
async def cb_unban(call: CallbackQuery):
    if not is_any_admin(call.from_user.id): return
    target_id = int(call.data.split("_")[-1])
    unban_user(target_id)
    await call.answer(f"✅ کاربر {target_id} آنبن شد.", show_alert=True)
    u = get_user_detail(target_id)
    if u:
        try: await call.message.edit_reply_markup(reply_markup=user_detail_keyboard(u[0], u[4]))
        except:
            try: await call.message.edit_reply_markup(reply_markup=support_action_keyboard(u[0], u[4]))
            except: pass

# ==================== افزودن کانفیگ ====================
@dp.callback_query(F.data == "admin_add_config")
async def cb_add_config(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "add_config"): return
    await call.answer()
    await state.set_state(AdminStates.waiting_config_count)
    await call.message.edit_text("➕ افزودن کانفیگ\n\nچند تا کانفیگ می‌خوای اضافه کنی؟\nعدد بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.waiting_config_count)
async def hdl_config_count(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    count = int(message.text.strip())
    await state.update_data(config_count=count, config_received=0)
    await state.set_state(AdminStates.waiting_config_item)
    await message.answer(f"✅ {count} تا کانفیگ ثبت می‌کنیم.\n\nکانفیگ شماره 1 رو بفرست:")

@dp.message(AdminStates.waiting_config_item)
async def hdl_config_item(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    data = await state.get_data()
    add_config(message.text.strip())
    received = data["config_received"] + 1
    await state.update_data(config_received=received)
    if received >= data["config_count"]:
        await state.clear()
        await message.answer(f"✅ همه {data['config_count']} کانفیگ اضافه شدن!", reply_markup=admin_keyboard(message.from_user.id)); return
    await message.answer(f"✅ کانفیگ {received} ثبت شد.\n\nکانفیگ شماره {received+1} رو بفرست:")

# ==================== سکه ====================
@dp.callback_query(F.data == "admin_addcoins")
async def cb_add_coins(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "coins"): return
    await call.answer()
    await state.set_state(AdminStates.add_coins_id)
    await call.message.edit_text("💰 انتقال سکه\n\nآیدی عددی کاربر رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.callback_query(F.data.startswith("admin_addcoin_"))
async def cb_add_coin_direct(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(add_coins_target=target_id)
    await state.set_state(AdminStates.add_coins_amount)
    await call.message.edit_text(f"💰 چند سکه به کاربر {target_id} اضافه کنم?\nعدد بفرست:")

@dp.message(AdminStates.add_coins_id)
async def hdl_add_coins_id(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    u = get_user(int(message.text.strip()))
    if not u:
        await message.answer("❌ کاربر یافت نشد:"); return
    await state.update_data(add_coins_target=int(message.text.strip()))
    await state.set_state(AdminStates.add_coins_amount)
    await message.answer(f"✅ کاربر: {u[2]}\n🪙 سکه فعلی: {u[3]}\n\nچند سکه اضافه کنم?")

@dp.message(AdminStates.add_coins_amount)
async def hdl_add_coins_amount(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    data = await state.get_data()
    update_coins(data["add_coins_target"], int(message.text.strip()))
    u = get_user(data["add_coins_target"])
    await state.clear()
    await message.answer(f"✅ {message.text.strip()} سکه به {data['add_coins_target']} اضافه شد.\n🪙 سکه جدید: {u[3]}",
        reply_markup=admin_keyboard(message.from_user.id))

@dp.callback_query(F.data == "admin_subcoins")
async def cb_sub_coins(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "coins"): return
    await call.answer()
    await state.set_state(AdminStates.sub_coins_id)
    await call.message.edit_text("➖ کسر سکه\n\nآیدی عددی کاربر رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.callback_query(F.data.startswith("admin_subcoin_"))
async def cb_sub_coin_direct(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(sub_coins_target=target_id)
    await state.set_state(AdminStates.sub_coins_amount)
    await call.message.edit_text(f"➖ چند سکه از کاربر {target_id} کسر کنم?\nعدد بفرست:")

@dp.message(AdminStates.sub_coins_id)
async def hdl_sub_coins_id(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit():
        await message.answer("❌ آیدی عددی معتبر بفرست:"); return
    u = get_user(int(message.text.strip()))
    if not u:
        await message.answer("❌ کاربر یافت نشد:"); return
    await state.update_data(sub_coins_target=int(message.text.strip()))
    await state.set_state(AdminStates.sub_coins_amount)
    await message.answer(f"✅ کاربر: {u[2]}\n🪙 سکه فعلی: {u[3]}\n\nچند سکه کسر کنم?")

@dp.message(AdminStates.sub_coins_amount)
async def hdl_sub_coins_amount(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❌ عدد معتبر بفرست:"); return
    data = await state.get_data()
    update_coins(data["sub_coins_target"], -int(message.text.strip()))
    u = get_user(data["sub_coins_target"])
    await state.clear()
    await message.answer(f"✅ {message.text.strip()} سکه از {data['sub_coins_target']} کسر شد.\n🪙 سکه جدید: {u[3]}",
        reply_markup=admin_keyboard(message.from_user.id))

# ==================== پیام به کاربر ====================
@dp.callback_query(F.data.startswith("admin_msguser_"))
async def cb_msg_user(call: CallbackQuery, state: FSMContext):
    if not is_any_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.split("_")[-1])
    await state.update_data(msg_user_target=target_id)
    await state.set_state(AdminStates.msg_user_text)
    await call.message.edit_text(f"✉️ پیام به کاربر {target_id}\n\nمتن پیام رو بفرست:")

@dp.message(AdminStates.msg_user_text)
async def hdl_msg_user_text(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    data = await state.get_data()
    try:
        await bot.send_message(data["msg_user_target"], f"📩 پیام از ادمین:\n\n{message.text}")
        await message.answer("✅ پیام ارسال شد.", reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ ارسال ناموفق: {e}", reply_markup=admin_keyboard(message.from_user.id))
    await state.clear()

# ==================== ارسال همگانی ====================
@dp.callback_query(F.data == "admin_broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "broadcast"): return
    await call.answer()
    await state.set_state(AdminStates.broadcast)
    await call.message.edit_text("📢 ارسال همگانی\n\nمتن پیام رو بفرست:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.broadcast)
async def hdl_broadcast(message: Message, state: FSMContext):
    if not is_any_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = c.fetchall(); conn.close()
    sent = failed = 0
    for (uid,) in users:
        try: await bot.send_message(uid, f"📢 پیام ادمین:\n\n{message.text}"); sent += 1
        except: failed += 1
    await state.clear()
    await message.answer(f"✅ ارسال همگانی تموم شد.\n📤 ارسال‌شده: {sent}\n❌ ناموفق: {failed}",
        reply_markup=admin_keyboard(message.from_user.id))

# ==================== تنظیم ایدی پشتیبانی ====================
@dp.callback_query(F.data == "admin_set_support")
async def cb_set_support(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "support_id"): return
    await call.answer()
    await state.set_state(AdminStates.set_support_id)
    await call.message.edit_text(
        f"🛟 تنظیم ایدی پشتیبانی\n\nایدی فعلی: {SUPPORT_ID or 'تنظیم نشده'}\n\nایدی جدید رو بفرست (مثلاً @username):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_cancel")]]))

@dp.message(AdminStates.set_support_id)
async def hdl_set_support_id(message: Message, state: FSMContext):
    global SUPPORT_ID
    if not is_any_admin(message.from_user.id): return
    new_id = message.text.strip()
    if not new_id.startswith("@"): new_id = "@" + new_id
    SUPPORT_ID = new_id
    cfg = load_config(); cfg["support_id"] = new_id; save_config(cfg)
    await state.clear()
    await message.answer(f"✅ ایدی پشتیبانی به {new_id} تغییر کرد!", reply_markup=admin_keyboard(message.from_user.id))

# ==================== مدیریت چنل‌ها ====================
def channels_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in CHANNEL_IDS:
        buttons.append([InlineKeyboardButton(text=f"{get_button_text('delete_channel')} {ch}", callback_data=f"admin_delchannel_{ch.lstrip('@')}", style=ButtonStyle.DANGER)])
    buttons.append([InlineKeyboardButton(text=get_button_text("add_channel"), callback_data="admin_addchannel", style=ButtonStyle.SUCCESS)])
    buttons.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(F.data == "admin_channels")
async def cb_admin_channels(call: CallbackQuery):
    if not has_perm(call.from_user.id, "channels"):
        await call.answer("❌ دسترسی ندارید.", show_alert=True); return
    await call.answer()
    ch_list = "\n".join([f"• {ch}" for ch in CHANNEL_IDS]) if CHANNEL_IDS else "هیچ چنلی ثبت نشده"
    await call.message.edit_text(
        f"📡 مدیریت چنل‌های عضویت اجباری\n━━━━━━━━━━━━━━━\n\nچنل‌های فعلی:\n{ch_list}\n\n"
        f"برای حذف روی چنل بزن:", reply_markup=channels_keyboard())

@dp.callback_query(F.data == "admin_addchannel")
async def cb_add_channel(call: CallbackQuery, state: FSMContext):
    if not has_perm(call.from_user.id, "channels"): return
    await call.answer()
    await state.set_state(AdminStates.add_channel)
    await call.message.edit_text("➕ اضافه کردن چنل\n\nیوزرنیم چنل رو با @ بفرست:\nمثال: @mychannel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_channels")]]))

@dp.message(AdminStates.add_channel)
async def hdl_add_channel(message: Message, state: FSMContext):
    global CHANNEL_IDS
    if not is_any_admin(message.from_user.id): return
    ch = message.text.strip()
    if not ch.startswith("@"): ch = "@" + ch
    if ch not in CHANNEL_IDS:
        CHANNEL_IDS.append(ch)
        cfg = load_config(); cfg["channels"] = CHANNEL_IDS; save_config(cfg)
        await message.answer(f"✅ چنل {ch} اضافه شد!", reply_markup=channels_keyboard())
    else:
        await message.answer(f"⚠️ چنل {ch} قبلاً ثبت شده!", reply_markup=channels_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("admin_delchannel_"))
async def cb_del_channel(call: CallbackQuery):
    global CHANNEL_IDS
    if not has_perm(call.from_user.id, "channels"): return
    await call.answer()
    ch = "@" + call.data.replace("admin_delchannel_", "")
    if ch in CHANNEL_IDS:
        CHANNEL_IDS.remove(ch)
        cfg = load_config(); cfg["channels"] = CHANNEL_IDS; save_config(cfg)
    ch_list = "\n".join([f"• {c}" for c in CHANNEL_IDS]) if CHANNEL_IDS else "هیچ چنلی ثبت نشده"
    await call.message.edit_text(f"✅ چنل {ch} حذف شد!\n\n📡 چنل‌های فعلی:\n{ch_list}\n\nبرای حذف روی چنل بزن:",
        reply_markup=channels_keyboard())

# ==================== مدیریت ادمین‌ها ====================
@dp.callback_query(F.data == "admin_manage_admins")
async def cb_manage_admins(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ فقط ادمین اصلی دسترسی دارد.", show_alert=True); return
    await call.answer()
    rows = []
    for uid_str, perms in SUB_ADMINS.items():
        active = sum(1 for v in perms.values() if v)
        rows.append([InlineKeyboardButton(text=f"👤 {uid_str} | {active}/{len(ALL_PERMS)} دسترسی",
            callback_data=f"admin_editadmin_{uid_str}")])
    rows.append([InlineKeyboardButton(text=get_button_text("add_admin"), callback_data="admin_addadmin", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    count = len(SUB_ADMINS)
    await call.message.edit_text(
        f"👤 مدیریت ادمین‌ها\n━━━━━━━━━━━━━━━\n\nادمین‌های فعلی: {count} نفر\n\nروی ادمین بزن تا دسترسی‌هاشو تنظیم کنی:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data == "admin_addadmin")
async def cb_add_admin(call: CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminStates.add_admin_id)
    await call.message.edit_text(
        "➕ اضافه کردن ادمین جدید\n\nآیدی عددی یا یوزرنیم @ کاربر رو بفرست:\nمثال: 123456789 یا @username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_button_text("cancel"), callback_data="admin_manage_admins")]]))

@dp.message(AdminStates.add_admin_id)
async def hdl_add_admin_id(message: Message, state: FSMContext):
    global SUB_ADMINS
    if not is_super_admin(message.from_user.id): return
    text = message.text.strip().lstrip("@")
    if not text.isdigit():
        await message.answer("❌ لطفاً آیدی عددی بفرست (نه یوزرنیم):"); return
    uid_str = text
    if uid_str not in SUB_ADMINS:
        SUB_ADMINS[uid_str] = {p: False for p in ALL_PERMS}
        cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    await state.clear()
    await message.answer(
        f"✅ ادمین {uid_str} اضافه شد!\nالان دسترسی‌هاشو تنظیم کن:",
        reply_markup=sub_admin_perms_keyboard(int(uid_str)))

@dp.callback_query(F.data.startswith("admin_editadmin_"))
async def cb_edit_admin(call: CallbackQuery):
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    target_id = int(call.data.replace("admin_editadmin_", ""))
    perms = SUB_ADMINS.get(str(target_id), {})
    active = sum(1 for v in perms.values() if v)
    await call.message.edit_text(
        f"👤 ادمین: {target_id}\n━━━━━━━━━━━━━━━\n"
        f"دسترسی‌های فعال: {active}/{len(ALL_PERMS)}\n\nروی هر گزینه بزن تا آن/آف بشه:",
        reply_markup=sub_admin_perms_keyboard(target_id))

@dp.callback_query(F.data.startswith("admin_toggleperm_"))
async def cb_toggle_perm(call: CallbackQuery):
    global SUB_ADMINS
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    parts = call.data.replace("admin_toggleperm_", "").split("_", 1)
    target_id = parts[0]
    perm = parts[1]
    if target_id not in SUB_ADMINS:
        SUB_ADMINS[target_id] = {p: False for p in ALL_PERMS}
    current = SUB_ADMINS[target_id].get(perm, False)
    SUB_ADMINS[target_id][perm] = not current
    cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    active = sum(1 for v in SUB_ADMINS[target_id].values() if v)
    await call.message.edit_text(
        f"👤 ادمین: {target_id}\n━━━━━━━━━━━━━━━\n"
        f"دسترسی‌های فعال: {active}/{len(ALL_PERMS)}\n\nروی هر گزینه بزن تا آن/آف بشه:",
        reply_markup=sub_admin_perms_keyboard(int(target_id)))

@dp.callback_query(F.data.startswith("admin_removeadmin_"))
async def cb_remove_admin(call: CallbackQuery):
    global SUB_ADMINS
    if not is_super_admin(call.from_user.id): return
    await call.answer()
    target_id = call.data.replace("admin_removeadmin_", "")
    SUB_ADMINS.pop(target_id, None)
    cfg = load_config(); cfg["sub_admins"] = SUB_ADMINS; save_config(cfg)
    rows = []
    for uid_str, perms in SUB_ADMINS.items():
        active = sum(1 for v in perms.values() if v)
        rows.append([InlineKeyboardButton(text=f"👤 {uid_str} | {active}/{len(ALL_PERMS)} دسترسی",
            callback_data=f"admin_editadmin_{uid_str}")])
    rows.append([InlineKeyboardButton(text=get_button_text("add_admin"), callback_data="admin_addadmin", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text=get_button_text("back_panel"), callback_data="open_admin_panel")])
    await call.message.edit_text(
        f"✅ ادمین {target_id} حذف شد!\n\n👤 مدیریت ادمین‌ها\nادمین‌های فعلی: {len(SUB_ADMINS)} نفر",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

# ==================== لغو ====================
@dp.callback_query(F.data == "admin_cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text("❌ عملیات لغو شد.", reply_markup=admin_keyboard(call.from_user.id))

# ==================== main ====================
async def main():
    global bot
    init_db()
    bot = Bot(token=BOT_TOKEN)
    print("✅ ربات شروع به کار کرد...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
