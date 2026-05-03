import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import date, datetime

import jdatetime


PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(s) -> str:
    return str(s).translate(PERSIAN_DIGITS)


def jalali_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    j = jdatetime.datetime.fromgregorian(datetime=dt)
    return fa_digits(j.strftime("%Y/%m/%d"))


def jalali_datetime(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    j = jdatetime.datetime.fromgregorian(datetime=dt)
    return fa_digits(j.strftime("%Y/%m/%d %H:%M:%S"))

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ===== شیم ButtonStyle (برای رنگ دکمه‌ها در نسخه‌های پشتیبان) =====
try:
    from aiogram.enums import ButtonStyle as _RealButtonStyle  # type: ignore

    class ButtonStyle:
        PRIMARY = _RealButtonStyle.PRIMARY
        DANGER = _RealButtonStyle.DANGER
        SUCCESS = _RealButtonStyle.SUCCESS
        DEFAULT = None
except Exception:
    class ButtonStyle:
        PRIMARY = "primary"
        DANGER = "danger"
        SUCCESS = "success"
        DEFAULT = None

    _orig_ikb_init = InlineKeyboardButton.__init__

    def _patched_ikb_init(self, **kwargs):
        kwargs.pop("style", None)
        _orig_ikb_init(self, **kwargs)

    InlineKeyboardButton.__init__ = _patched_ikb_init  # type: ignore

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== تنظیمات ثابت ====================
BOT_TOKEN = "8420717247:AAEvAag3RZRDdIRK2MnL20LQkYb7vCpPuPI"
SUPER_ADMIN_IDS = [6849816314, 7770582235,8478999016]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot.db")
SETTINGS_FILE = os.path.join(BASE_DIR, "bot_settings.json")

DEFAULT_SUPPORT_ID = "@v2ray_404"
DEFAULT_CHANNELS = []

# قیمت پیش‌فرض (تومان × ۱۰۰۰ یعنی هزار تومان نمایش داده می‌شود)
DEFAULT_PRICES = {
    "1": 450_000,
    "2": 900_000,
    "3": 1_350_000,
    "5": 2_250_000,
    "10": 4_200_000,
}
PRODUCT_LABEL = {
    "1": "۱ گیگ",
    "2": "۲ گیگ",
    "3": "۳ گیگ",
    "5": "۵ گیگ",
    "10": "۱۰ گیگ",
}

DEFAULT_BUTTON_COLORS = {
    "main_buy": "primary",
    "main_my": "success",
    "main_account": "primary",
    "main_invite": "success",
    "main_support": "default",
    "main_admin": "danger",
    "pay_card": "primary",
    "pay_discount": "success",
    "back": "default",
}

BUTTON_LABELS = {
    "main_buy": "🛒 خرید سرویس جدید",
    "main_my": "📦 سرویس‌های من",
    "main_account": "👤 حساب کاربری",
    "main_invite": "🤝 دعوت دوستان",
    "main_support": "📞 ارتباط با پشتیبانی",
    "main_admin": "🛠 پنل مدیریت",
    "pay_card": "💳 کارت به کارت",
    "pay_discount": "🎁 اعمال کد تخفیف",
    "back": "🔙 بازگشت",
}

# ==================== ذخیره تنظیمات ====================
def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("support_id", DEFAULT_SUPPORT_ID)
    data.setdefault("channels", DEFAULT_CHANNELS.copy())
    data.setdefault("prices", DEFAULT_PRICES.copy())
    data.setdefault("colors", DEFAULT_BUTTON_COLORS.copy())
    data.setdefault("card_number", "")
    data.setdefault("card_holder", "")
    # merge defaults
    for k, v in DEFAULT_PRICES.items():
        data["prices"].setdefault(k, v)
    for k, v in DEFAULT_BUTTON_COLORS.items():
        data["colors"].setdefault(k, v)
    return data


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SETTINGS = load_settings()


def s_get(key, default=None):
    return SETTINGS.get(key, default)


def s_set(key, value):
    SETTINGS[key] = value
    save_settings(SETTINGS)


# ==================== رنگ دکمه‌ها ====================
_COLOR_MAP = {
    "primary": ButtonStyle.PRIMARY,
    "danger": ButtonStyle.DANGER,
    "success": ButtonStyle.SUCCESS,
    "default": ButtonStyle.DEFAULT,
}


def style_of(key: str):
    color = SETTINGS["colors"].get(key, DEFAULT_BUTTON_COLORS.get(key, "default"))
    return _COLOR_MAP.get(color, ButtonStyle.DEFAULT)


def btn(text: str, key: str | None = None, **kwargs) -> InlineKeyboardButton:
    if key:
        return InlineKeyboardButton(text=text, style=style_of(key), **kwargs)
    return InlineKeyboardButton(text=text, **kwargs)


# ==================== دیتابیس ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0,
        invited_by INTEGER,
        balance INTEGER DEFAULT 0,
        referral_discount_used INTEGER DEFAULT 0,
        referral_discount_available INTEGER DEFAULT 0
        )"""
    )
    for col, ddl in [
        ("balance", "ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0"),
        ("referral_discount_used", "ALTER TABLE users ADD COLUMN referral_discount_used INTEGER DEFAULT 0"),
        ("referral_discount_available", "ALTER TABLE users ADD COLUMN referral_discount_available INTEGER DEFAULT 0"),
    ]:
        try: c.execute(ddl)
        except: pass
    c.execute(
        """CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product TEXT,
        username TEXT,
        amount INTEGER,
        photo_id TEXT,
        status TEXT DEFAULT 'pending',
        config TEXT DEFAULT '',
        sub_link TEXT DEFAULT '',
        created_at TEXT
        )"""
    )
    for col, ddl in [
        ("config", "ALTER TABLE receipts ADD COLUMN config TEXT DEFAULT ''"),
        ("sub_link", "ALTER TABLE receipts ADD COLUMN sub_link TEXT DEFAULT ''"),
    ]:
        try: c.execute(ddl)
        except: pass
    c.execute(
        """CREATE TABLE IF NOT EXISTS discounts (
        code TEXT PRIMARY KEY,
        percent INTEGER,
        created_at TEXT
        )"""
    )
    conn.commit()
    conn.close()


def db():
    return sqlite3.connect(DB_PATH)


def db_add_user(user_id, username, full_name, invited_by=None):
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name, join_date, invited_by) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), invited_by),
    )
    new = c.rowcount == 1
    conn.commit()
    conn.close()
    return new


def db_is_banned(user_id) -> bool:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return bool(r and r[0])


def db_set_ban(user_id, val: int):
    conn = db()
    c = conn.cursor()
    # اگر کاربر قبلاً نبوده، اول می‌سازیم
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)",
        (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    c.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (val, user_id))
    conn.commit()
    conn.close()


def db_stats():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM receipts")
    total_r = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM receipts WHERE status='approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM receipts WHERE status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM receipts WHERE status='approved'")
    revenue = c.fetchone()[0]
    today = date.today().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (today + "%",))
    new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM discounts")
    discounts = c.fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "banned": banned,
        "total_receipts": total_r,
        "approved": approved,
        "pending": pending,
        "revenue": revenue,
        "new_today": new_today,
        "discounts": discounts,
    }


def db_create_receipt(user_id, product, username, amount, photo_id) -> int:
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO receipts (user_id, product, username, amount, photo_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, product, username, amount, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def db_get_pending_receipts():
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, product, username, amount FROM receipts WHERE status='pending' ORDER BY id"
    )
    rows = c.fetchall()
    conn.close()
    return rows


def db_approve_receipt(rid):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE receipts SET status='approved' WHERE id = ?", (rid,))
    conn.commit()
    conn.close()


def db_get_user_receipts(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, product, username, amount, status, created_at FROM receipts WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_receipt(rid):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, product, username, amount, photo_id, status, config, sub_link, created_at FROM receipts WHERE id = ?",
        (rid,),
    )
    r = c.fetchone()
    conn.close()
    return r


def db_set_receipt_status(rid, status):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE receipts SET status = ? WHERE id = ?", (status, rid))
    conn.commit()
    conn.close()


def db_set_receipt_config(rid, config="", sub_link=""):
    conn = db()
    c = conn.cursor()
    fields, vals = [], []
    if config:
        fields.append("config = ?"); vals.append(config)
    if sub_link:
        fields.append("sub_link = ?"); vals.append(sub_link)
    if not fields:
        conn.close(); return
    vals.append(rid)
    c.execute(f"UPDATE receipts SET {', '.join(fields)} WHERE id = ?", tuple(vals))
    conn.commit()
    conn.close()


def db_get_user_delivered_services(user_id):
    """سرویس‌هایی که تایید شده‌اند (کانفیگ یا ساب دارند یا تایید شده‌اند)."""
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, product, username, config, sub_link FROM receipts "
        "WHERE user_id = ? AND status='approved' ORDER BY id DESC",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_user_info(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT balance, join_date FROM users WHERE user_id = ?",
        (user_id,),
    )
    r = c.fetchone()
    c.execute(
        "SELECT COUNT(*) FROM receipts WHERE user_id = ? AND status='approved'",
        (user_id,),
    )
    services = c.fetchone()[0]
    conn.close()
    if not r:
        return {"balance": 0, "join_date": None, "services": 0}
    return {"balance": r[0] or 0, "join_date": r[1], "services": services}


def db_count_referrals(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE invited_by = ?", (user_id,))
    n = c.fetchone()[0]
    conn.close()
    return n


def db_get_referral_discount(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT referral_discount_available, referral_discount_used FROM users WHERE user_id = ?",
        (user_id,),
    )
    r = c.fetchone()
    conn.close()
    if not r:
        return 0, 0
    return (r[0] or 0), (r[1] or 0)


def db_grant_referral_discount(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET referral_discount_available = COALESCE(referral_discount_available,0) + 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def db_consume_referral_discount(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET referral_discount_available = MAX(0, COALESCE(referral_discount_available,0) - 1), "
        "referral_discount_used = COALESCE(referral_discount_used,0) + 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def db_save_discount(code, percent):
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO discounts (code, percent, created_at) VALUES (?, ?, ?)",
        (code, percent, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def db_get_discount(code):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT percent FROM discounts WHERE code = ?", (code,))
    r = c.fetchone()
    conn.close()
    return r[0] if r else None


# ==================== کمک‌ها ====================
def is_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS


def fmt_price(amount: int) -> str:
    return f"{amount:,} تومان"


# ==================== کیبوردها ====================
def kb_main(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [btn(BUTTON_LABELS["main_buy"], "main_buy", callback_data="buy_menu")],
        [
            btn(BUTTON_LABELS["main_my"], "main_my", callback_data="my_services"),
            btn(BUTTON_LABELS["main_account"], "main_account", callback_data="account"),
        ],
        [
            btn(BUTTON_LABELS["main_invite"], "main_invite", callback_data="invite"),
            btn(BUTTON_LABELS["main_support"], "main_support", callback_data="support"),
        ],
    ]
    if is_admin(user_id):
        rows.append([btn(BUTTON_LABELS["main_admin"], "main_admin", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_back(target: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[btn(BUTTON_LABELS["back"], "back", callback_data=target)]]
    )


def kb_buy_menu() -> InlineKeyboardMarkup:
    rows = []
    for k in ["1", "2", "3", "5", "10"]:
        price = SETTINGS["prices"].get(k, DEFAULT_PRICES[k])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{PRODUCT_LABEL[k]} — {fmt_price(price)}",
                    callback_data=f"prod_{k}",
                )
            ]
        )
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_invoice(product: str) -> InlineKeyboardMarkup:
    rows = [
        [btn(BUTTON_LABELS["pay_discount"], "pay_discount", callback_data=f"discount_{product}")],
        [btn(BUTTON_LABELS["pay_card"], "pay_card", callback_data=f"paycard_{product}")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="buy_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_join_required() -> InlineKeyboardMarkup:
    rows = []
    for ch in SETTINGS["channels"]:
        url_ch = ch.lstrip("@")
        rows.append(
            [InlineKeyboardButton(text=f"📢 عضویت در {ch}", url=f"https://t.me/{url_ch}")]
        )
    rows.append([InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 آمار ربات", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 پیام همگانی", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="✅ تایید همه رسیدها", callback_data="adm_approve_all")],
        [
            InlineKeyboardButton(text="🚫 بن کردن کاربر", callback_data="adm_ban"),
            InlineKeyboardButton(text="🔓 آنبن کردن کاربر", callback_data="adm_unban"),
        ],
        [InlineKeyboardButton(text="🎁 ساخت کد تخفیف", callback_data="adm_discount")],
        [InlineKeyboardButton(text="💵 تنظیم قیمت کانفیگ", callback_data="adm_prices")],
        [InlineKeyboardButton(text="💳 تنظیم شماره کارت", callback_data="adm_card")],
        [InlineKeyboardButton(text="🛟 تنظیم آیدی پشتیبانی", callback_data="adm_support")],
        [InlineKeyboardButton(text="📡 تنظیم چنل جوین اجباری", callback_data="adm_channels")],
        [InlineKeyboardButton(text="🎨 تنظیم رنگ دکمه‌ها", callback_data="adm_colors")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_prices() -> InlineKeyboardMarkup:
    rows = []
    for k in ["1", "2", "3", "5", "10"]:
        price = SETTINGS["prices"].get(k, DEFAULT_PRICES[k])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{PRODUCT_LABEL[k]} — {fmt_price(price)}",
                    callback_data=f"setprice_{k}",
                )
            ]
        )
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_channels() -> InlineKeyboardMarkup:
    rows = []
    for ch in SETTINGS["channels"]:
        rows.append(
            [
                InlineKeyboardButton(text=f"📢 {ch}", callback_data="noop"),
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"delch_{ch}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ افزودن چنل", callback_data="addch")])
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_colors() -> InlineKeyboardMarkup:
    rows = []
    for key, label in BUTTON_LABELS.items():
        if key == "back":
            continue
        cur = SETTINGS["colors"].get(key, "default")
        emoji = {"primary": "🔵", "success": "🟢", "danger": "🔴", "default": "⚪"}.get(cur, "⚪")
        rows.append(
            [InlineKeyboardButton(text=f"{emoji} {label}", callback_data=f"color_{key}")]
        )
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_color_choice(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔵 آبی", callback_data=f"setcolor_{key}_primary"),
                InlineKeyboardButton(text="🟢 سبز", callback_data=f"setcolor_{key}_success"),
                InlineKeyboardButton(text="🔴 قرمز", callback_data=f"setcolor_{key}_danger"),
            ],
            [InlineKeyboardButton(text="⚪ معمولی (مات)", callback_data=f"setcolor_{key}_default")],
            [btn(BUTTON_LABELS["back"], "back", callback_data="adm_colors")],
        ]
    )


# ==================== متن خوش‌آمد ====================
def welcome_text() -> str:
    return (
        "✨ به فروشگاه VPN ما خوش آمدید!\n\n"
        "🛡 ارائه انواع سرویس‌های VPN با کیفیت عالی\n"
        "✅ تضمین امنیت ارتباطات شما\n"
        "📞 پشتیبانی حرفه‌ای ۲۴ ساعته\n\n"
        "از منوی زیر بخش مورد نظر خود را انتخاب کنید."
    )


# ==================== States ====================
class BuyStates(StatesGroup):
    waiting_username = State()
    waiting_receipt = State()
    waiting_discount_code = State()


class AdminStates(StatesGroup):
    ban_user = State()
    unban_user = State()
    discount_input = State()
    set_price = State()
    set_card_number = State()
    set_card_holder = State()
    set_support = State()
    add_channel = State()
    waiting_config = State()
    waiting_sub = State()
    broadcast_message = State()


# ==================== Bot/Dispatcher ====================
dp = Dispatcher(storage=MemoryStorage())
bot: Bot | None = None


# ===== بررسی عضویت =====
async def check_membership(user_id: int) -> bool:
    if not bot:
        return True
    for ch in SETTINGS["channels"]:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status in ("left", "kicked"):
                return False
        except Exception as e:
            logger.warning(f"membership check failed for {ch}: {e}")
            return False
    return True


# ==================== /start ====================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    u = message.from_user
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            invited_by = int(args[1].split("_")[1])
            if invited_by == u.id:
                invited_by = None
        except Exception:
            pass
    db_add_user(u.id, u.username, u.full_name, invited_by)

    if db_is_banned(u.id) and not is_admin(u.id):
        await message.answer("⛔️ حساب شما مسدود شده است.")
        return

    if not await check_membership(u.id):
        await message.answer(
            "❌ برای استفاده از ربات لازم است در کانال زیر عضو شوید:",
            reply_markup=kb_join_required(),
        )
        return

    await message.answer(welcome_text(), reply_markup=kb_main(u.id))


@dp.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not await check_membership(call.from_user.id):
        await call.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
        return
    await call.message.edit_text(welcome_text(), reply_markup=kb_main(call.from_user.id))


@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text(welcome_text(), reply_markup=kb_main(call.from_user.id))
    except Exception:
        await call.message.answer(welcome_text(), reply_markup=kb_main(call.from_user.id))


@dp.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


# ==================== خرید ====================
@dp.callback_query(F.data == "buy_menu")
async def cb_buy_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    txt = (
        "🛒 سرویس‌های فروشگاه ما\n"
        "با تضمین کیفیت در بدترین شرایط\n\n"
        "یکی از پکیج‌های زیر را انتخاب کنید 👇"
    )
    await call.message.edit_text(txt, reply_markup=kb_buy_menu())


@dp.callback_query(F.data.startswith("prod_"))
async def cb_select_product(call: CallbackQuery, state: FSMContext):
    await call.answer()
    product = call.data.split("_", 1)[1]
    if product not in PRODUCT_LABEL:
        return
    await state.update_data(product=product, discount_percent=0)
    await state.set_state(BuyStates.waiting_username)
    await call.message.edit_text(
        f"🛒 سرویس {PRODUCT_LABEL[product]} انتخاب شد.\n\n"
        "لطفا یک نام کاربری با حروف لاتین به طول حداکثر ۲۰ کاراکتر وارد نمایید 👇",
        reply_markup=kb_back("buy_menu"),
    )


@dp.message(BuyStates.waiting_username)
async def msg_get_username(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", text):
        await message.answer("❌ نام کاربری نامعتبر است. فقط حروف لاتین/عدد، ۳ تا ۲۰ کاراکتر.")
        return
    data = await state.get_data()
    product = data["product"]
    base = SETTINGS["prices"].get(product, DEFAULT_PRICES[product])
    discount = data.get("discount_percent", 0)
    final = int(base * (100 - discount) / 100)
    await state.update_data(username=text, base_price=base, final_price=final)

    invoice = (
        f"🧾 پیش‌فاکتور\n\n"
        f"👤 نام کاربری: <code>{text}</code>\n"
        f"📦 سرویس: {PRODUCT_LABEL[product]}\n"
        f"📅 مدت اعتبار: نامحدود\n"
        f"💾 حجم: {product} گیگابایت\n\n"
    )
    if discount:
        invoice += f"💸 تخفیف: {discount}٪\n"
        invoice += f"💵 قیمت اصلی: {fmt_price(base)}\n"
    invoice += f"💰 مبلغ قابل پرداخت: <b>{fmt_price(final)}</b>\n\n"
    invoice += "سفارش شما آماده پرداخت است."

    await message.answer(invoice, reply_markup=kb_invoice(product), parse_mode=ParseMode.HTML)


# ===== کد تخفیف =====
@dp.callback_query(F.data.startswith("discount_"))
async def cb_apply_discount(call: CallbackQuery, state: FSMContext):
    await call.answer()
    product = call.data.split("_", 1)[1]
    await state.update_data(product=product)
    await state.set_state(BuyStates.waiting_discount_code)
    await call.message.answer("🎁 لطفاً کد تخفیف خود را ارسال کنید 👇")


@dp.message(BuyStates.waiting_discount_code)
async def msg_discount_code(message: Message, state: FSMContext):
    code = (message.text or "").strip()
    percent = db_get_discount(code)
    if percent is None:
        await message.answer("❌ کد تخفیف معتبر نیست.")
        return
    data = await state.get_data()
    product = data.get("product")
    if not product:
        await message.answer("❌ خطا. /start را بزنید.")
        await state.clear()
        return
    base = SETTINGS["prices"].get(product, DEFAULT_PRICES[product])
    final = int(base * (100 - percent) / 100)
    await state.update_data(discount_percent=percent, base_price=base, final_price=final)
    # برمی‌گردیم به مرحله دریافت یوزرنیم اگر هنوز ندارد
    if not data.get("username"):
        await state.set_state(BuyStates.waiting_username)
        await message.answer(
            f"✅ کد تخفیف {percent}٪ اعمال شد.\n\n"
            f"حالا یک نام کاربری با حروف لاتین (۳ تا ۲۰ کاراکتر) ارسال کنید 👇"
        )
    else:
        username = data["username"]
        invoice = (
            f"🧾 پیش‌فاکتور\n\n"
            f"👤 نام کاربری: <code>{username}</code>\n"
            f"📦 سرویس: {PRODUCT_LABEL[product]}\n"
            f"📅 مدت اعتبار: نامحدود\n"
            f"💾 حجم: {product} گیگابایت\n\n"
            f"💸 تخفیف: {percent}٪\n"
            f"💵 قیمت اصلی: {fmt_price(base)}\n"
            f"💰 مبلغ قابل پرداخت: <b>{fmt_price(final)}</b>"
        )
        await message.answer(invoice, reply_markup=kb_invoice(product), parse_mode=ParseMode.HTML)


# ===== کارت به کارت =====
@dp.callback_query(F.data.startswith("paycard_"))
async def cb_pay_card(call: CallbackQuery, state: FSMContext):
    await call.answer()
    product = call.data.split("_", 1)[1]
    data = await state.get_data()
    if not data.get("username"):
        await call.answer("ابتدا نام کاربری را وارد کنید.", show_alert=True)
        return
    final = data.get("final_price") or SETTINGS["prices"].get(product, DEFAULT_PRICES[product])
    card = SETTINGS.get("card_number") or "تنظیم نشده"
    holder = SETTINGS.get("card_holder") or ""
    holder_line = f"به نام: {holder}" if holder else ""
    txt = (
        f"برای افزایش موجودی، مبلغ {fmt_price(final)} را به شماره‌ی حساب زیر واریز کنید 👇🏻\n\n"
        f"====================\n\n"
        f"<code>{card}</code>\n"
        f"{holder_line}\n\n"
        f"====================\n\n"
        f"🟢این تراکنش به مدت یک ساعت اعتبار دارد پس از آن امکان پرداخت این تراکنش امکان ندارد.\n"
        f"‼️مسئولیت واریز اشتباهی با شماست.\n"
        f"🔝بعد از پرداخت دکمه (ادامه مراحل) رو بزنید و عکس رسید خود را ارسال کنید تا موجودیتون افزایش داده بشه."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 ادامه مراحل (ارسال رسید)", callback_data=f"sendreceipt_{product}")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="back_main")],
    ])
    await call.message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)


@dp.callback_query(F.data.startswith("sendreceipt_"))
async def cb_send_receipt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(BuyStates.waiting_receipt)
    await call.message.answer("📸 لطفاً عکس رسید خود را همینجا ارسال کنید 👇")


@dp.message(BuyStates.waiting_receipt, F.photo)
async def msg_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    product = data.get("product")
    username = data.get("username")
    final = data.get("final_price")
    if not (product and username and final):
        await message.answer("❌ خطا. لطفاً از ابتدا اقدام کنید: /start")
        await state.clear()
        return
    photo_id = message.photo[-1].file_id
    rid = db_create_receipt(message.from_user.id, product, username, final, photo_id)
    await message.answer(
        "✅ اوکی! رسید شما دریافت شد.\n"
        "💳 پرداخت شما در سریع‌ترین زمان ممکن تایید می‌شود."
    )
    # ارسال به ادمین‌ها با چهار دکمه
    caption = (
        f"🧾 رسید جدید #{rid}\n"
        f"👤 کاربر: {message.from_user.full_name}\n"
        f"🆔 آیدی: <code>{message.from_user.id}</code>\n"
        f"📦 سرویس: {PRODUCT_LABEL[product]}\n"
        f"🧾 یوزرنیم: <code>{username}</code>\n"
        f"💰 مبلغ: {fmt_price(final)}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید رسید", callback_data=f"adm_approve_{rid}"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"adm_reject_{rid}"),
        ],
        [
            InlineKeyboardButton(text="📦 کانفیگ + ساب", callback_data=f"adm_cfgsub_{rid}"),
            InlineKeyboardButton(text="📦 کانفیگ", callback_data=f"adm_cfg_{rid}"),
        ],
    ])
    for aid in SUPER_ADMIN_IDS:
        try:
            await bot.send_photo(aid, photo_id, caption=caption, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"notify admin {aid} failed: {e}")
    await state.clear()


@dp.message(BuyStates.waiting_receipt)
async def msg_receipt_wrong(message: Message):
    await message.answer("📸 لطفاً عکس رسید را به صورت تصویر ارسال کنید.")


# ==================== سرویس‌های من / حساب / دعوت / پشتیبانی ====================
@dp.callback_query(F.data == "my_services")
async def cb_my_services(call: CallbackQuery):
    await call.answer()
    rows = db_get_user_delivered_services(call.from_user.id)
    if not rows:
        await call.message.edit_text(
            "📦 شما هنوز سرویس فعالی ندارید.\n(فقط سرویس‌های تاییدشده اینجا نمایش داده می‌شوند.)",
            reply_markup=kb_back("back_main"),
        )
        return
    btns = []
    for r in rows[:20]:
        rid, product, username, config, sub_link = r
        btns.append([InlineKeyboardButton(
            text=f"👤 {username}  |  {PRODUCT_LABEL.get(product, product)}",
            callback_data=f"svc_{rid}",
        )])
    btns.append([btn(BUTTON_LABELS["back"], "back", callback_data="back_main")])
    await call.message.edit_text("📦 سرویس‌های شما:\nروی نام کاربری بزنید 👇", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@dp.callback_query(F.data.startswith("svc_"))
async def cb_view_service(call: CallbackQuery):
    await call.answer()
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    _, _, product, username, amount, _, status, config, sub_link, created = r
    txt = (
        f"📦 سرویس شما\n\n"
        f"👤 نام کاربری: <code>{username}</code>\n"
        f"💾 حجم: {product} گیگابایت\n"
        f"📅 مدت اعتبار: نامحدود\n"
        f"💰 مبلغ پرداختی: {fmt_price(amount)}"
    )
    rows = []
    if sub_link:
        rows.append([InlineKeyboardButton(text="🔗 دریافت لینک ساب", callback_data=f"getsub_{rid}")])
    if config:
        rows.append([InlineKeyboardButton(text="📄 دریافت لینک بدون ساب", callback_data=f"getcfg_{rid}")])
    if not rows:
        txt += "\n\n⏳ کانفیگ هنوز برای شما ارسال نشده. لطفاً صبور باشید."
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="my_services")])
    await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("getsub_"))
async def cb_get_sub(call: CallbackQuery):
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    sub = r[8]
    if not sub:
        await call.answer("لینک ساب موجود نیست.", show_alert=True); return
    await call.answer()
    await call.message.answer(f"🔗 لینک ساب شما:\n\n<code>{sub}</code>", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("getcfg_"))
async def cb_get_cfg(call: CallbackQuery):
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    cfg = r[7]
    if not cfg:
        await call.answer("کانفیگ موجود نیست.", show_alert=True); return
    await call.answer()
    await call.message.answer(f"📄 کانفیگ شما:\n\n<code>{cfg}</code>", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "account")
async def cb_account(call: CallbackQuery):
    await call.answer()
    u = call.from_user
    info = db_get_user_info(u.id)
    # تبدیل تاریخ ورود
    if info["join_date"]:
        try:
            jd = datetime.strptime(info["join_date"], "%Y-%m-%d %H:%M:%S")
            join_str = jalali_date(jd)
        except Exception:
            join_str = "—"
    else:
        join_str = "—"
    now_str = jalali_datetime()
    txt = (
        "👨🏻‍💻اطلاعات حساب کاربری شما:\n\n"
        f"💰 موجودی: {fa_digits('{:,}'.format(info['balance']))} تومان\n\n"
        f"🕴🏻آیدی عددی : {fa_digits(u.id)}\n"
        f"🛍 تعداد سرویس ها: {fa_digits(info['services'])}\n"
        f"🗓 تاریخ ورود به بات: {join_str}\n\n"
        f"📆 {now_str}"
    )
    await call.message.edit_text(txt, reply_markup=kb_back("back_main"))


@dp.callback_query(F.data == "invite")
async def cb_invite(call: CallbackQuery):
    await call.answer()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{call.from_user.id}"
    refs = db_count_referrals(call.from_user.id)
    avail, used = db_get_referral_discount(call.from_user.id)
    txt = (
        "🤝 دعوت دوستان\n\n"
        "با هر رفرالی که می‌آورید، اگر آن کاربر از ربات خرید کند، یک کد تخفیف "
        "<b>۱۰٪</b> به شما تعلق می‌گیرد که فقط <b>یک بار</b> روی <b>یک محصول</b> قابل استفاده است.\n\n"
        f"👥 تعداد رفرال‌های شما: {fa_digits(refs)}\n"
        f"🎁 تخفیف‌های آماده استفاده: {fa_digits(avail)}\n"
        f"✅ تخفیف‌های استفاده‌شده: {fa_digits(used)}\n\n"
        f"🔗 لینک دعوت شما:\n<code>{link}</code>"
    )
    await call.message.edit_text(txt, reply_markup=kb_back("back_main"), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.answer()
    sup = SETTINGS.get("support_id") or DEFAULT_SUPPORT_ID
    txt = f"📞 ارتباط با پشتیبانی\n\nآیدی پشتیبانی: {sup}"
    await call.message.edit_text(txt, reply_markup=kb_back("back_main"))


# ==================== پنل مدیریت ====================
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید.", show_alert=True)
        return
    await call.message.edit_text("👑 پنل مدیریت", reply_markup=kb_admin())


# آمار
@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    s = db_stats()
    txt = (
        "📊 آمار ربات\n\n"
        f"👥 کل کاربران: {s['total_users']}\n"
        f"🆕 کاربران امروز: {s['new_today']}\n"
        f"⛔ کاربران بن: {s['banned']}\n\n"
        f"🧾 کل رسیدها: {s['total_receipts']}\n"
        f"✅ تاییدشده: {s['approved']}\n"
        f"⏳ در انتظار: {s['pending']}\n"
        f"💰 مجموع فروش تاییدشده: {fmt_price(s['revenue'])}\n\n"
        f"🎁 کدهای تخفیف فعال: {s['discounts']}"
    )
    await call.message.edit_text(txt, reply_markup=kb_back("admin_panel"))


# تایید همه رسیدها
@dp.callback_query(F.data == "adm_approve_all")
async def cb_adm_approve_all(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    pending = db_get_pending_receipts()
    count = 0
    for rid, uid, product, username, amount in pending:
        db_approve_receipt(rid)
        count += 1
        try:
            await bot.send_message(
                uid,
                f"✅ رسید #{rid} شما تایید شد!\n"
                f"📦 سرویس: {PRODUCT_LABEL.get(product, product)}\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"💰 مبلغ: {fmt_price(amount)}\n\n"
                f"به‌زودی سرویس برای شما ارسال می‌شود.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    await call.message.edit_text(
        f"✅ {count} رسید تایید شد و به کاربران اطلاع داده شد.",
        reply_markup=kb_back("admin_panel"),
    )


async def _grant_referral_if_first_purchase(buyer_id: int):
    """اولین خرید تاییدشده‌ی دعوت‌شده ⇒ یک تخفیف ۱۰٪ به دعوت‌کننده."""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT invited_by FROM users WHERE user_id = ?", (buyer_id,))
    r = c.fetchone()
    if not r or not r[0]:
        conn.close(); return None
    inviter = r[0]
    c.execute("SELECT COUNT(*) FROM receipts WHERE user_id = ? AND status = 'approved'", (buyer_id,))
    approved_count = c.fetchone()[0]
    conn.close()
    if approved_count == 1:
        db_grant_referral_discount(inviter)
        return inviter
    return None


@dp.callback_query(F.data.startswith("adm_approve_"))
async def cb_adm_approve_one(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    rid = int(call.data.split("_")[2])
    r = db_get_receipt(rid)
    if not r:
        await call.answer("یافت نشد", show_alert=True); return
    _, uid, product, username, amount, _, status, _, _, _ = r
    if status == "approved":
        await call.answer("قبلاً تایید شده", show_alert=True); return
    db_approve_receipt(rid)
    try:
        await bot.send_message(
            uid,
            f"✅ رسید #{rid} شما تایید شد!\n"
            f"📦 سرویس: {PRODUCT_LABEL.get(product, product)}\n"
            f"👤 یوزرنیم: <code>{username}</code>\n"
            f"💰 مبلغ: {fmt_price(amount)}\n\n"
            f"⏳ به‌زودی سرور برای شما ارسال می‌شود.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    inviter = await _grant_referral_if_first_purchase(uid)
    if inviter:
        try:
            await bot.send_message(
                inviter,
                "🎉 یکی از دوستانی که دعوت کردی خرید کرد!\n"
                "🎁 یک کد تخفیف ۱۰٪ یک‌بارمصرف برای یک محصول به حسابت اضافه شد.",
            )
        except Exception:
            pass
    await call.answer("✅ تایید شد", show_alert=False)
    try:
        await call.message.edit_caption(
            (call.message.caption or "") + "\n\n✅ تایید شد",
            reply_markup=None,
        )
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


@dp.callback_query(F.data.startswith("adm_reject_"))
async def cb_adm_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    rid = int(call.data.split("_")[2])
    r = db_get_receipt(rid)
    if not r:
        await call.answer("یافت نشد", show_alert=True); return
    _, uid, product, username, amount, _, status, _, _, _ = r
    if status == "rejected":
        await call.answer("قبلاً رد شده", show_alert=True); return
    db_set_receipt_status(rid, "rejected")
    try:
        await bot.send_message(
            uid,
            f"❌ رسید #{rid} شما توسط ادمین رد شد.\n"
            f"📦 سرویس: {PRODUCT_LABEL.get(product, product)}\n"
            f"💰 مبلغ: {fmt_price(amount)}\n\n"
            "در صورت سوال با پشتیبانی در تماس باشید.",
        )
    except Exception:
        pass
    await call.answer("❌ رد شد")
    try:
        await call.message.edit_caption((call.message.caption or "") + "\n\n❌ رد شد", reply_markup=None)
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


# ==================== پیام همگانی ====================
@dp.callback_query(F.data == "adm_broadcast")
async def cb_adm_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.broadcast_message)
    await call.message.edit_text(
        "📢 پیام همگانی\n\n"
        "متن یا عکسی که می‌خواهید برای همه کاربران ربات ارسال شود را بفرستید 👇",
        reply_markup=kb_back("admin_panel"),
    )


@dp.message(AdminStates.broadcast_message)
async def msg_adm_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    conn = db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE COALESCE(is_banned,0)=0")
    users = [row[0] for row in c.fetchall()]
    conn.close()

    sent, failed = 0, 0
    status = await message.answer(f"⏳ در حال ارسال به {len(users)} کاربر...")
    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    try:
        await status.edit_text(
            f"✅ پیام همگانی ارسال شد.\n\n"
            f"📤 موفق: {sent}\n"
            f"❌ ناموفق: {failed}",
            reply_markup=kb_admin(),
        )
    except Exception:
        await message.answer(
            f"✅ پیام همگانی ارسال شد.\n\n📤 موفق: {sent}\n❌ ناموفق: {failed}",
            reply_markup=kb_admin(),
        )


@dp.callback_query(F.data.startswith("adm_cfgsub_"))
async def cb_adm_cfgsub(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    rid = int(call.data.split("_")[2])
    await state.update_data(deliver_rid=rid, deliver_mode="cfgsub")
    await state.set_state(AdminStates.waiting_config)
    await call.message.answer(f"📦 برای رسید #{rid}\n\n📄 کانفیگ را ارسال کنید 👇")


@dp.callback_query(F.data.startswith("adm_cfg_"))
async def cb_adm_cfg(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    rid = int(call.data.split("_")[2])
    await state.update_data(deliver_rid=rid, deliver_mode="cfg")
    await state.set_state(AdminStates.waiting_config)
    await call.message.answer(f"📦 برای رسید #{rid}\n\n📄 کانفیگ را ارسال کنید 👇")


@dp.message(AdminStates.waiting_config)
async def msg_adm_config(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    cfg = (message.text or "").strip()
    if not cfg:
        await message.answer("❌ متن خالی است."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    mode = data.get("deliver_mode")
    if not rid:
        await state.clear(); return
    db_set_receipt_config(rid, config=cfg)
    if mode == "cfgsub":
        await state.set_state(AdminStates.waiting_sub)
        await message.answer("✅ کانفیگ ثبت شد.\n\n🔗 حالا لطفاً ساب را ارسال کنید 👇")
        return
    # فقط کانفیگ
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; username = r[3]; product = r[2]
        try:
            await bot.send_message(
                uid,
                f"📦 سرویس شما آماده شد!\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"💾 حجم: {product} گیگابایت\n\n"
                f"📄 کانفیگ:\n<code>{cfg}</code>",
                parse_mode=ParseMode.HTML,
            )
            await _grant_referral_if_first_purchase(uid)
        except Exception as e:
            logger.warning(f"send config to {uid} failed: {e}")
    await state.clear()
    await message.answer(f"✅ کانفیگ برای کاربر ارسال شد. (رسید #{rid})")


@dp.message(AdminStates.waiting_sub)
async def msg_adm_sub(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    sub = (message.text or "").strip()
    if not sub:
        await message.answer("❌ متن خالی است."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    if not rid:
        await state.clear(); return
    db_set_receipt_config(rid, sub_link=sub)
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; username = r[3]; product = r[2]; cfg = r[7]
        try:
            await bot.send_message(
                uid,
                f"📦 سرویس شما آماده شد!\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"💾 حجم: {product} گیگابایت\n\n"
                f"📄 کانفیگ:\n<code>{cfg}</code>\n\n"
                f"🔗 ساب:\n<code>{sub}</code>",
                parse_mode=ParseMode.HTML,
            )
            await _grant_referral_if_first_purchase(uid)
        except Exception as e:
            logger.warning(f"send config+sub to {uid} failed: {e}")
    await state.clear()
    await message.answer(f"✅ کانفیگ + ساب برای کاربر ارسال شد. (رسید #{rid})")


# بن
@dp.callback_query(F.data == "adm_ban")
async def cb_adm_ban(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.ban_user)
    await call.message.edit_text("🚫 آیدی عددی کاربر برای بن را ارسال کنید 👇", reply_markup=kb_back("admin_panel"))


@dp.message(AdminStates.ban_user)
async def msg_adm_ban(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        uid = int((message.text or "").strip())
    except Exception:
        await message.answer("❌ آیدی عددی نامعتبر است."); return
    db_set_ban(uid, 1)
    await state.clear()
    await message.answer(f"✅ کاربر <code>{uid}</code> بن شد.", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "adm_unban")
async def cb_adm_unban(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.unban_user)
    await call.message.edit_text("🔓 آیدی عددی کاربر برای آنبن را ارسال کنید 👇", reply_markup=kb_back("admin_panel"))


@dp.message(AdminStates.unban_user)
async def msg_adm_unban(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        uid = int((message.text or "").strip())
    except Exception:
        await message.answer("❌ آیدی عددی نامعتبر است."); return
    db_set_ban(uid, 0)
    await state.clear()
    await message.answer(f"✅ کاربر <code>{uid}</code> آنبن شد.", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)


# کد تخفیف
@dp.callback_query(F.data == "adm_discount")
async def cb_adm_discount(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.discount_input)
    await call.message.edit_text(
        "🎁 لطفاً کد تخفیف را به این صورت ارسال کنید:\n\n"
        "<b>Badboy50</b>\n\n"
        "یعنی کلمه + درصد در انتها (۱ تا ۱۰۰).\n"
        "این کد روی همه محصولات اعمال خواهد شد.",
        reply_markup=kb_back("admin_panel"),
        parse_mode=ParseMode.HTML,
    )


@dp.message(AdminStates.discount_input)
async def msg_adm_discount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    text = (message.text or "").strip()
    m = re.match(r"^(.+?)(\d{1,3})$", text)
    if not m:
        await message.answer("❌ فرمت نامعتبر. مثال: Badboy50"); return
    code, percent = m.group(1) + m.group(2), int(m.group(2))
    if not (1 <= percent <= 100):
        await message.answer("❌ درصد باید بین ۱ تا ۱۰۰ باشد."); return
    db_save_discount(code, percent)
    await state.clear()
    await message.answer(
        f"✅ کد تخفیف <code>{code}</code> با {percent}٪ ساخته شد.",
        reply_markup=kb_admin(),
        parse_mode=ParseMode.HTML,
    )


# تنظیم قیمت
@dp.callback_query(F.data == "adm_prices")
async def cb_adm_prices(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "💵 برای تنظیم قیمت، روی محصول مورد نظر بزنید:",
        reply_markup=kb_admin_prices(),
    )


@dp.callback_query(F.data.startswith("setprice_"))
async def cb_set_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    p = call.data.split("_", 1)[1]
    if p not in PRODUCT_LABEL: return
    await state.update_data(target_product=p)
    await state.set_state(AdminStates.set_price)
    cur = SETTINGS["prices"].get(p, DEFAULT_PRICES[p])
    await call.message.edit_text(
        f"💵 قیمت فعلی {PRODUCT_LABEL[p]}: {fmt_price(cur)}\n\n"
        "قیمت جدید را به تومان (فقط عدد) ارسال کنید 👇",
        reply_markup=kb_back("adm_prices"),
    )


@dp.message(AdminStates.set_price)
async def msg_set_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    txt = re.sub(r"[^\d]", "", message.text or "")
    if not txt:
        await message.answer("❌ فقط عدد ارسال کنید."); return
    new_price = int(txt)
    data = await state.get_data()
    p = data.get("target_product")
    if not p:
        await state.clear(); return
    SETTINGS["prices"][p] = new_price
    save_settings(SETTINGS)
    await state.clear()
    await message.answer(
        f"✅ قیمت {PRODUCT_LABEL[p]} به {fmt_price(new_price)} تنظیم شد.",
        reply_markup=kb_admin_prices(),
    )


# تنظیم شماره کارت
@dp.callback_query(F.data == "adm_card")
async def cb_adm_card(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    cur_card = SETTINGS.get("card_number") or "تنظیم نشده"
    cur_holder = SETTINGS.get("card_holder") or "تنظیم نشده"
    await state.set_state(AdminStates.set_card_number)
    await call.message.edit_text(
        f"💳 وضعیت فعلی\nکارت: <code>{cur_card}</code>\nبه‌نام: {cur_holder}\n\n"
        "لطفاً شماره کارت جدید را ارسال کنید 👇",
        reply_markup=kb_back("admin_panel"),
        parse_mode=ParseMode.HTML,
    )


@dp.message(AdminStates.set_card_number)
async def msg_card_number(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    card = re.sub(r"\s+", "", message.text or "")
    if not re.fullmatch(r"\d{12,20}", card):
        await message.answer("❌ شماره کارت نامعتبر است."); return
    await state.update_data(card_number=card)
    await state.set_state(AdminStates.set_card_holder)
    await message.answer("✅ شماره کارت ثبت شد.\n\n👤 حالا نام کاربری/نام صاحب کارت را ارسال کنید 👇")


@dp.message(AdminStates.set_card_holder)
async def msg_card_holder(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    holder = (message.text or "").strip()
    if not holder:
        await message.answer("❌ نام نمی‌تواند خالی باشد."); return
    data = await state.get_data()
    SETTINGS["card_number"] = data.get("card_number", "")
    SETTINGS["card_holder"] = holder
    save_settings(SETTINGS)
    await state.clear()
    await message.answer(
        f"✅ ذخیره شد.\n💳 <code>{SETTINGS['card_number']}</code>\n👤 {holder}",
        reply_markup=kb_admin(),
        parse_mode=ParseMode.HTML,
    )


# تنظیم پشتیبانی
@dp.callback_query(F.data == "adm_support")
async def cb_adm_support(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    cur = SETTINGS.get("support_id") or DEFAULT_SUPPORT_ID
    await state.set_state(AdminStates.set_support)
    await call.message.edit_text(
        f"🛟 آیدی پشتیبانی فعلی: {cur}\n\nآیدی جدید را ارسال کنید (مثلاً @v2ray_404) 👇",
        reply_markup=kb_back("admin_panel"),
    )


@dp.message(AdminStates.set_support)
async def msg_set_support(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    sid = (message.text or "").strip()
    if not sid:
        await message.answer("❌"); return
    if not sid.startswith("@"):
        sid = "@" + sid
    s_set("support_id", sid)
    await state.clear()
    await message.answer(f"✅ آیدی پشتیبانی به {sid} تغییر کرد.", reply_markup=kb_admin())


# تنظیم چنل‌ها
@dp.callback_query(F.data == "adm_channels")
async def cb_adm_channels(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "📡 مدیریت چنل‌های جوین اجباری:",
        reply_markup=kb_admin_channels(),
    )


@dp.callback_query(F.data.startswith("delch_"))
async def cb_delch(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    ch = call.data.split("_", 1)[1]
    chs = SETTINGS.get("channels", [])
    if ch in chs:
        chs.remove(ch)
        s_set("channels", chs)
    await call.answer("حذف شد")
    await call.message.edit_reply_markup(reply_markup=kb_admin_channels())


@dp.callback_query(F.data == "addch")
async def cb_addch(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.add_channel)
    await call.message.edit_text(
        "📡 یوزرنیم چنل را ارسال کنید (مثلاً @v2ray_404 یا لینک کامل):",
        reply_markup=kb_back("adm_channels"),
    )


@dp.message(AdminStates.add_channel)
async def msg_addch(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    text = (message.text or "").strip()
    m = re.search(r"(?:t\.me/)?@?([A-Za-z][A-Za-z0-9_]{3,})", text)
    if not m:
        await message.answer("❌ فرمت نامعتبر."); return
    ch = "@" + m.group(1)
    chs = SETTINGS.get("channels", [])
    if ch not in chs:
        chs.append(ch)
        s_set("channels", chs)
    await state.clear()
    await message.answer(f"✅ {ch} اضافه شد.", reply_markup=kb_admin_channels())


# رنگ دکمه‌ها
@dp.callback_query(F.data == "adm_colors")
async def cb_adm_colors(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "🎨 یکی از دکمه‌ها را برای تغییر رنگ انتخاب کنید:",
        reply_markup=kb_admin_colors(),
    )


@dp.callback_query(F.data.startswith("color_"))
async def cb_color_pick(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    key = call.data.split("_", 1)[1]
    label = BUTTON_LABELS.get(key, key)
    await call.message.edit_text(
        f"🎨 رنگ دلخواه برای دکمه «{label}» را انتخاب کنید:",
        reply_markup=kb_color_choice(key),
    )


@dp.callback_query(F.data.startswith("setcolor_"))
async def cb_set_color(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    parts = call.data.split("_")
    # setcolor_<key>_<color>
    color = parts[-1]
    key = "_".join(parts[1:-1])
    if color not in ("primary", "success", "danger", "default"):
        await call.answer("نامعتبر", show_alert=True); return
    SETTINGS["colors"][key] = color
    save_settings(SETTINGS)
    await call.answer("✅ ذخیره شد")
    await call.message.edit_text(
        "🎨 یکی از دکمه‌ها را برای تغییر رنگ انتخاب کنید:",
        reply_markup=kb_admin_colors(),
    )


# ==================== /menuvip — لیست مشتری‌ها (شیشه‌ای بالا) ====================
VIP_PAGE_SIZE = 10


def db_get_all_customers():
    """همه مشتری‌هایی که حداقل یک رسید تاییدشده دارند.
    خروجی هر سطر:
        (user_id, full_name, username, total_spent, total_configs, is_vip, is_banned)
    is_vip = 1 اگر حداقل یک خرید ۱۰ گیگ (شیشه‌ای) داشته باشد.
    مرتب‌سازی: شیشه‌ای‌ها بالا، سپس مجموع خرید نزولی.
    """
    conn = db()
    c = conn.cursor()
    c.execute(
        """
        SELECT
            u.user_id,
            COALESCE(u.full_name, ''),
            COALESCE(u.username, ''),
            COALESCE(SUM(r.amount), 0) AS total_spent,
            COUNT(r.id) AS total_configs,
            MAX(CASE WHEN r.product = '10' THEN 1 ELSE 0 END) AS is_vip,
            COALESCE(u.is_banned, 0) AS is_banned
        FROM users u
        INNER JOIN receipts r
            ON r.user_id = u.user_id AND r.status = 'approved'
        GROUP BY u.user_id
        ORDER BY is_vip DESC, total_spent DESC, total_configs DESC
        """
    )
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_customer_full(user_id):
    """اطلاعات کامل یک مشتری به همراه تفکیک خریدها."""
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT user_id, full_name, username, balance, join_date, is_banned "
        "FROM users WHERE user_id = ?",
        (user_id,),
    )
    u = c.fetchone()
    if not u:
        conn.close()
        return None
    c.execute(
        "SELECT product, COUNT(*), COALESCE(SUM(amount),0) "
        "FROM receipts WHERE user_id = ? AND status='approved' "
        "GROUP BY product",
        (user_id,),
    )
    breakdown = c.fetchall()
    c.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) "
        "FROM receipts WHERE user_id = ? AND status='approved'",
        (user_id,),
    )
    total_spent, total_configs = c.fetchone()
    conn.close()
    vip_count = sum(cnt for prod, cnt, _amt in breakdown if prod == "10")
    return {
        "user_id": u[0],
        "full_name": u[1] or "—",
        "username": u[2] or "",
        "balance": u[3] or 0,
        "join_date": u[4],
        "is_banned": bool(u[5]),
        "total_spent": total_spent,
        "total_configs": total_configs,
        "vip_count": vip_count,
        "breakdown": breakdown,
    }


def db_get_user_configs(user_id):
    """همه کانفیگ/ساب‌های تاییدشده‌ی یک کاربر."""
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, product, username, config, sub_link FROM receipts "
        "WHERE user_id = ? AND status='approved' ORDER BY id DESC",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def _vip_header(customers) -> str:
    vip_count = sum(1 for c in customers if c[5])
    return (
        "👥 <b>لیست مشتریان</b>\n\n"
        f"💎 شیشه‌ای: {fa_digits(vip_count)}\n"
        f"👤 کل: {fa_digits(len(customers))}\n\n"
        "روی نام کاربر بزنید تا مشخصات و گزینه‌ها نمایش داده شود 👇"
    )


def kb_vip_customers(page: int = 0) -> InlineKeyboardMarkup:
    customers = db_get_all_customers()
    total = len(customers)
    start = page * VIP_PAGE_SIZE
    end = start + VIP_PAGE_SIZE
    page_rows = customers[start:end]
    rows = []
    for cust in page_rows:
        uid, full_name, username, total_spent, total_configs, is_vip, is_banned = cust
        badge = "💎" if is_vip else "👤"
        if is_banned:
            badge = "⛔" + badge
        name = full_name or username or str(uid)
        if username:
            label = f"{badge} {name} (@{username}) — {fa_digits(total_configs)} کانفیگ"
        else:
            label = f"{badge} {name} — {fa_digits(total_configs)} کانفیگ"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"vipuser_{uid}")]
        )
    nav = []
    if start > 0:
        nav.append(
            InlineKeyboardButton(text="◀️ قبلی", callback_data=f"vippage_{page-1}")
        )
    if end < total:
        nav.append(
            InlineKeyboardButton(text="بعدی ▶️", callback_data=f"vippage_{page+1}")
        )
    if nav:
        rows.append(nav)
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_vip_user_actions(uid: int, is_banned: bool) -> InlineKeyboardMarkup:
    rows = []
    if is_banned:
        rows.append(
            [InlineKeyboardButton(text="🔓 آنبن کردن", callback_data=f"vipunban_{uid}")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🚫 بن کردن", callback_data=f"vipban_{uid}")]
        )
    rows.append(
        [InlineKeyboardButton(text="📦 دریافت کانفیگ‌ها", callback_data=f"vipcfg_{uid}")]
    )
    rows.append(
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="vipback_0")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _vip_user_text(info: dict) -> str:
    if info["join_date"]:
        try:
            jd = datetime.strptime(info["join_date"], "%Y-%m-%d %H:%M:%S")
            join_str = jalali_date(jd)
        except Exception:
            join_str = "—"
    else:
        join_str = "—"
    is_vip = info["vip_count"] > 0
    badge = "💎 <b>مشتری شیشه‌ای</b>" if is_vip else "👤 مشتری معمولی"
    status = "⛔ بن شده" if info["is_banned"] else "✅ فعال"
    username_line = f"@{info['username']}" if info["username"] else "—"
    txt = (
        f"{badge}\n\n"
        f"👤 نام: {info['full_name']}\n"
        f"🔗 یوزرنیم: {username_line}\n"
        f"🆔 آیدی عددی: <code>{info['user_id']}</code>\n"
        f"🗓 تاریخ ورود: {join_str}\n"
        f"📌 وضعیت: {status}\n\n"
        f"🛍 تعداد کل کانفیگ‌ها: {fa_digits(info['total_configs'])}\n"
        f"💰 مجموع خرید: {fa_digits('{:,}'.format(info['total_spent']))} تومان\n"
        f"💎 خرید شیشه‌ای (۱۰ گیگ): {fa_digits(info['vip_count'])}\n"
    )
    if info["breakdown"]:
        txt += "\n📦 <b>تفکیک خریدها:</b>\n"
        for prod, cnt, amt in info["breakdown"]:
            label = PRODUCT_LABEL.get(prod, prod)
            txt += (
                f"• {label}: {fa_digits(cnt)} عدد — "
                f"{fa_digits('{:,}'.format(amt))} تومان\n"
            )
    return txt


@dp.message(Command("menuvip"))
async def cmd_menuvip(message: Message):
    if not is_admin(message.from_user.id):
        return
    customers = db_get_all_customers()
    if not customers:
        await message.answer("🗂 هنوز هیچ مشتری تاییدشده‌ای ثبت نشده است.")
        return
    await message.answer(
        _vip_header(customers),
        reply_markup=kb_vip_customers(page=0),
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data.startswith("vippage_"))
async def cb_vip_page(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    await call.answer()
    try:
        page = int(call.data.split("_", 1)[1])
    except Exception:
        page = 0
    customers = db_get_all_customers()
    try:
        await call.message.edit_text(
            _vip_header(customers),
            reply_markup=kb_vip_customers(page=page),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await call.message.answer(
            _vip_header(customers),
            reply_markup=kb_vip_customers(page=page),
            parse_mode=ParseMode.HTML,
        )


@dp.callback_query(F.data.startswith("vipback_"))
async def cb_vip_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    await call.answer()
    try:
        page = int(call.data.split("_", 1)[1])
    except Exception:
        page = 0
    customers = db_get_all_customers()
    try:
        await call.message.edit_text(
            _vip_header(customers),
            reply_markup=kb_vip_customers(page=page),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await call.message.answer(
            _vip_header(customers),
            reply_markup=kb_vip_customers(page=page),
            parse_mode=ParseMode.HTML,
        )


@dp.callback_query(F.data.startswith("vipuser_"))
async def cb_vip_user(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    await call.answer()
    try:
        uid = int(call.data.split("_", 1)[1])
    except Exception:
        await call.answer("نامعتبر", show_alert=True)
        return
    info = db_get_customer_full(uid)
    if not info:
        await call.answer("کاربر یافت نشد", show_alert=True)
        return
    await call.message.edit_text(
        _vip_user_text(info),
        reply_markup=kb_vip_user_actions(uid, info["is_banned"]),
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data.startswith("vipban_"))
async def cb_vip_ban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    try:
        uid = int(call.data.split("_", 1)[1])
    except Exception:
        await call.answer("نامعتبر", show_alert=True)
        return
    db_set_ban(uid, 1)
    await call.answer("✅ کاربر بن شد")
    info = db_get_customer_full(uid)
    if info:
        try:
            await call.message.edit_text(
                _vip_user_text(info),
                reply_markup=kb_vip_user_actions(uid, info["is_banned"]),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            try:
                await call.message.edit_reply_markup(
                    reply_markup=kb_vip_user_actions(uid, info["is_banned"])
                )
            except Exception:
                pass


@dp.callback_query(F.data.startswith("vipunban_"))
async def cb_vip_unban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    try:
        uid = int(call.data.split("_", 1)[1])
    except Exception:
        await call.answer("نامعتبر", show_alert=True)
        return
    db_set_ban(uid, 0)
    await call.answer("✅ کاربر آنبن شد")
    info = db_get_customer_full(uid)
    if info:
        try:
            await call.message.edit_text(
                _vip_user_text(info),
                reply_markup=kb_vip_user_actions(uid, info["is_banned"]),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            try:
                await call.message.edit_reply_markup(
                    reply_markup=kb_vip_user_actions(uid, info["is_banned"])
                )
            except Exception:
                pass


@dp.callback_query(F.data.startswith("vipcfg_"))
async def cb_vip_get_configs(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True)
        return
    await call.answer()
    try:
        uid = int(call.data.split("_", 1)[1])
    except Exception:
        await call.answer("نامعتبر", show_alert=True)
        return
    rows = db_get_user_configs(uid)
    if not rows:
        await call.message.answer("📦 این کاربر هیچ کانفیگ تاییدشده‌ای ندارد.")
        return
    out = f"📦 کانفیگ‌های کاربر <code>{uid}</code>:\n\n"
    for r in rows:
        rid, product, username, config, sub_link = r
        plabel = PRODUCT_LABEL.get(product, product)
        chunk = "━━━━━━━━━━━━━━━\n"
        chunk += f"🆔 رسید #{rid}\n"
        chunk += f"📦 سرویس: {plabel}\n"
        chunk += f"👤 یوزرنیم: <code>{username}</code>\n"
        if config:
            chunk += f"📄 کانفیگ:\n<code>{config}</code>\n"
        if sub_link:
            chunk += f"🔗 ساب:\n<code>{sub_link}</code>\n"
        if not config and not sub_link:
            chunk += "⏳ هنوز کانفیگ ثبت نشده.\n"
        chunk += "\n"
        if len(out) + len(chunk) > 3500:
            await call.message.answer(out, parse_mode=ParseMode.HTML)
            out = ""
        out += chunk
    if out.strip():
        await call.message.answer(out, parse_mode=ParseMode.HTML)


# ==================== Main ====================
async def main():
    global bot
    init_db()
    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username}")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
