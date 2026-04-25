import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import date, datetime

import jdatetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

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


# ===== شیم ButtonStyle =====
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
BOT_TOKEN = "8604621783:AAGlE2dcAwUsauxPHXWS5ChkmczV4-HZO38"
SUPER_ADMIN_IDS = [8478999016, 243261217]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot@parhawmz.db")
SETTINGS_FILE = os.path.join(BASE_DIR, "bot_settings.json")

DEFAULT_SUPPORT_ID = "@Px7Vpn"
DEFAULT_CHANNELS = []

# ==================== سرویس‌ها ====================
SERVICES = {
    "v2ray": {
        "label": "V2Ray",
        "volumes": ["1", "2", "3", "4", "5", "10"],
        "spec": "نامحدود زمانی",
    },
    "openvpn": {
        "label": "Open VPN",
        "volumes": ["1", "5", "10", "20"],
        "spec": "یک ماه — ۲ کاربره",
    },
    "l2tp": {
        "label": "L2TP",
        "volumes": ["1", "5", "10", "20"],
        "spec": "یک ماه — ۲ کاربره",
    },
}

# نام‌های فارسی نمایش داده شده در پنل ادمین
SERVICE_FA_LABELS = {
    "v2ray": "ویتوری",
    "openvpn": "اوپن",
    "l2tp": "L2tp",
}

DEFAULT_PRICES = {
    "v2ray": {
        "1": 50_000,
        "2": 90_000,
        "3": 130_000,
        "4": 170_000,
        "5": 200_000,
        "10": 380_000,
    },
    "openvpn": {
        "1": 80_000,
        "5": 300_000,
        "10": 550_000,
        "20": 1_000_000,
    },
    "l2tp": {
        "1": 80_000,
        "5": 300_000,
        "10": 550_000,
        "20": 1_000_000,
    },
}


def product_label(service: str, vol: str) -> str:
    return f"{SERVICES[service]['label']} — {fa_digits(vol)} گیگ"


def parse_product(p: str):
    """تبدیل رشته‌ی محصول به (service, volume). برای رکوردهای قدیمی پیش‌فرض v2ray."""
    if "_" in p:
        s, v = p.split("_", 1)
        if s in SERVICES:
            return s, v
    # سازگاری با رکوردهای قدیمی
    return "v2ray", p


DEFAULT_BUTTON_COLORS = {
    "main_buy": "primary",
    "main_my": "success",
    "main_account": "primary",
    "main_invite": "success",
    "main_support": "default",
    "main_tut_openvpn": "primary",
    "main_tut_v2ray": "primary",
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
    "main_tut_openvpn": "📚 آموزش Open VPN",
    "main_tut_v2ray": "📚 آموزش V2Ray",
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
    data.setdefault("prices", {})
    data.setdefault("colors", DEFAULT_BUTTON_COLORS.copy())
    data.setdefault("card_number", "")
    data.setdefault("card_holder", "")
    data.setdefault("tutorials", {"v2ray": [], "openvpn": []})
    # merge default prices per service
    for svc, prices in DEFAULT_PRICES.items():
        data["prices"].setdefault(svc, {})
        for k, v in prices.items():
            data["prices"][svc].setdefault(k, v)
    for k, v in DEFAULT_BUTTON_COLORS.items():
        data["colors"].setdefault(k, v)
    # tutorials shape
    for svc in ("v2ray", "openvpn"):
        data["tutorials"].setdefault(svc, [])
    # volumes overrides per service (برای افزودن/حذف محصولات)
    data.setdefault("service_volumes", {})
    return data


def _apply_service_volumes_overrides():
    """اعمال لیست حجم‌های ذخیره‌شده روی دیکشنری SERVICES."""
    overrides = SETTINGS.get("service_volumes") or {}
    for svc, vols in overrides.items():
        if svc in SERVICES and isinstance(vols, list) and vols:
            SERVICES[svc]["volumes"] = list(vols)


def _persist_service_volumes(service: str):
    """ذخیره لیست فعلی حجم‌های یک سرویس در SETTINGS."""
    SETTINGS.setdefault("service_volumes", {})[service] = list(
        SERVICES[service]["volumes"]
    )
    save_settings(SETTINGS)


def add_product(service: str, vol: str, price: int) -> bool:
    """افزودن محصول جدید (حجم) به یک سرویس و تنظیم قیمت آن."""
    if service not in SERVICES:
        return False
    vols = SERVICES[service]["volumes"]
    if vol in vols:
        # اگر از قبل وجود دارد فقط قیمت را به‌روز می‌کنیم
        set_price(service, vol, price)
        return True
    vols.append(vol)
    _persist_service_volumes(service)
    set_price(service, vol, price)
    return True


def remove_product(service: str, vol: str) -> bool:
    """حذف یک حجم از سرویس."""
    if service not in SERVICES:
        return False
    vols = SERVICES[service]["volumes"]
    if vol not in vols:
        return False
    vols.remove(vol)
    _persist_service_volumes(service)
    # حذف قیمت ذخیره‌شده
    if "prices" in SETTINGS and service in SETTINGS["prices"]:
        SETTINGS["prices"][service].pop(vol, None)
        save_settings(SETTINGS)
    return True


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SETTINGS = load_settings()
_apply_service_volumes_overrides()


def s_get(key, default=None):
    return SETTINGS.get(key, default)


def s_set(key, value):
    SETTINGS[key] = value
    save_settings(SETTINGS)


def get_price(service: str, vol: str) -> int:
    return SETTINGS["prices"].get(service, {}).get(
        vol, DEFAULT_PRICES.get(service, {}).get(vol, 0)
    )


def set_price(service: str, vol: str, value: int):
    SETTINGS["prices"].setdefault(service, {})[vol] = value
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
        ovpn_file_id TEXT DEFAULT '',
        ovpn_user TEXT DEFAULT '',
        ovpn_pass TEXT DEFAULT '',
        ovpn_link TEXT DEFAULT '',
        created_at TEXT
        )"""
    )
    for col, ddl in [
        ("config", "ALTER TABLE receipts ADD COLUMN config TEXT DEFAULT ''"),
        ("sub_link", "ALTER TABLE receipts ADD COLUMN sub_link TEXT DEFAULT ''"),
        ("ovpn_file_id", "ALTER TABLE receipts ADD COLUMN ovpn_file_id TEXT DEFAULT ''"),
        ("ovpn_user", "ALTER TABLE receipts ADD COLUMN ovpn_user TEXT DEFAULT ''"),
        ("ovpn_pass", "ALTER TABLE receipts ADD COLUMN ovpn_pass TEXT DEFAULT ''"),
        ("ovpn_link", "ALTER TABLE receipts ADD COLUMN ovpn_link TEXT DEFAULT ''"),
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
    """برمی‌گرداند: id, user_id, product, username, amount, photo_id, status,
    config, sub_link, ovpn_file_id, ovpn_user, ovpn_pass, ovpn_link, created_at"""
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, product, username, amount, photo_id, status, "
        "config, sub_link, ovpn_file_id, ovpn_user, ovpn_pass, ovpn_link, created_at "
        "FROM receipts WHERE id = ?",
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


def db_set_receipt_field(rid, **fields):
    if not fields:
        return
    conn = db()
    c = conn.cursor()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [rid]
    c.execute(f"UPDATE receipts SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def db_get_user_delivered_services(user_id):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, product, username FROM receipts "
        "WHERE user_id = ? AND status='approved' ORDER BY id DESC",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def db_get_user_info(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT balance, join_date FROM users WHERE user_id = ?", (user_id,))
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
            btn(BUTTON_LABELS["main_support"], "main_support", callback_data="support"),
        ],
        [
            btn(BUTTON_LABELS["main_tut_openvpn"], "main_tut_openvpn", callback_data="tut_openvpn"),
            btn(BUTTON_LABELS["main_tut_v2ray"], "main_tut_v2ray", callback_data="tut_v2ray"),
        ],
    ]
    if is_admin(user_id):
        rows.append([btn(BUTTON_LABELS["main_admin"], "main_admin", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_back(target: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[btn(BUTTON_LABELS["back"], "back", callback_data=target)]]
    )


def kb_service_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🛡 Open VPN", callback_data="svc_openvpn")],
        [InlineKeyboardButton(text="⚡️ V2Ray", callback_data="svc_v2ray")],
        [InlineKeyboardButton(text="🔐 L2TP", callback_data="svc_l2tp")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_volume_menu(service: str) -> InlineKeyboardMarkup:
    rows = []
    for v in SERVICES[service]["volumes"]:
        price = get_price(service, v)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{fa_digits(v)} گیگ — {fmt_price(price)}",
                    callback_data=f"prod_{service}_{v}",
                )
            ]
        )
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_invoice(product_key: str) -> InlineKeyboardMarkup:
    rows = [
        [btn(BUTTON_LABELS["pay_discount"], "pay_discount", callback_data=f"discount_{product_key}")],
        [btn(BUTTON_LABELS["pay_card"], "pay_card", callback_data=f"paycard_{product_key}")],
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
        [InlineKeyboardButton(text="💵 مدیریت محصولات و قیمت‌ها", callback_data="adm_prices_root")],
        [InlineKeyboardButton(text="📚 آپلود آموزش Open VPN", callback_data="adm_uptut_openvpn")],
        [InlineKeyboardButton(text="📚 آپلود آموزش V2Ray", callback_data="adm_uptut_v2ray")],
        [InlineKeyboardButton(text="💳 تنظیم شماره کارت", callback_data="adm_card")],
        [InlineKeyboardButton(text="🛟 تنظیم آیدی پشتیبانی", callback_data="adm_support")],
        [InlineKeyboardButton(text="📡 تنظیم چنل جوین اجباری", callback_data="adm_channels")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_prices_root() -> InlineKeyboardMarkup:
    """منوی اصلی مدیریت محصولات و قیمت‌ها — انتخاب سرویس."""
    rows = [
        [InlineKeyboardButton(text="⚡️ ویتوری", callback_data="adm_prices_v2ray")],
        [InlineKeyboardButton(text="🛡 اوپن", callback_data="adm_prices_openvpn")],
        [InlineKeyboardButton(text="🔐 L2tp", callback_data="adm_prices_l2tp")],
        [btn(BUTTON_LABELS["back"], "back", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_prices(service: str) -> InlineKeyboardMarkup:
    """مدیریت محصولات یک سرویس: تغییر قیمت + حذف + افزودن محصول جدید."""
    rows = []
    for v in SERVICES[service]["volumes"]:
        price = get_price(service, v)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {fa_digits(v)} گیگ — {fmt_price(price)}",
                    callback_data=f"setprice_{service}_{v}",
                ),
                InlineKeyboardButton(
                    text="🗑 حذف",
                    callback_data=f"delprod_{service}_{v}",
                ),
            ]
        )
    rows.append([
        InlineKeyboardButton(
            text="➕ افزودن محصول جدید (حجم + قیمت)",
            callback_data=f"addprod_{service}",
        )
    ])
    rows.append([btn(BUTTON_LABELS["back"], "back", callback_data="adm_prices_root")])
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


# ==================== متن خوش‌آمد ====================
def welcome_text() -> str:
    return (
        "✨ به فروشگاه Px7 Vpn خوش آمدید!\n\n"
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
    # OpenVPN delivery
    ovpn_waiting_file = State()
    ovpn_waiting_user = State()
    ovpn_waiting_pass = State()
    ovpn_waiting_link = State()
    # Tutorials
    upload_tutorial = State()
    # افزودن محصول جدید
    add_product_vol = State()
    add_product_price = State()


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
    txt = "🛒 کدوم سرویس می‌خوای؟\n\nیکی از سرویس‌های زیر را انتخاب کنید 👇"
    await call.message.edit_text(txt, reply_markup=kb_service_menu())


@dp.callback_query(F.data.startswith("svc_"))
async def cb_select_service(call: CallbackQuery, state: FSMContext):
    await call.answer()
    service = call.data.split("_", 1)[1]
    if service not in SERVICES:
        return
    spec = SERVICES[service]["spec"]
    txt = (
        f"📦 سرویس {SERVICES[service]['label']}\n"
        f"📋 مشخصات: {spec}\n\n"
        f"یکی از حجم‌های زیر را انتخاب کنید 👇"
    )
    await call.message.edit_text(txt, reply_markup=kb_volume_menu(service))


@dp.callback_query(F.data.startswith("prod_"))
async def cb_select_product(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split("_", 2)
    if len(parts) < 3:
        return
    service, vol = parts[1], parts[2]
    if service not in SERVICES or vol not in SERVICES[service]["volumes"]:
        return
    product_key = f"{service}_{vol}"
    await state.update_data(product=product_key, discount_percent=0)
    await state.set_state(BuyStates.waiting_username)
    await call.message.edit_text(
        f"🛒 سرویس {product_label(service, vol)} انتخاب شد.\n\n"
        "لطفا یک نام کاربری با حروف لاتین به طول حداکثر ۲۰ کاراکتر وارد نمایید 👇",
        reply_markup=kb_back(f"svc_{service}"),
    )


@dp.message(BuyStates.waiting_username)
async def msg_get_username(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", text):
        await message.answer("❌ نام کاربری نامعتبر است. فقط حروف لاتین/عدد، ۳ تا ۲۰ کاراکتر.")
        return
    data = await state.get_data()
    product_key = data["product"]
    service, vol = parse_product(product_key)
    base = get_price(service, vol)
    discount = data.get("discount_percent", 0)
    final = int(base * (100 - discount) / 100)
    await state.update_data(username=text, base_price=base, final_price=final)

    spec = SERVICES[service]["spec"]
    invoice = (
        f"🧾 پیش‌فاکتور\n\n"
        f"👤 نام کاربری: <code>{text}</code>\n"
        f"📦 سرویس: {product_label(service, vol)}\n"
        f"📋 مشخصات: {spec}\n"
        f"💾 حجم: {fa_digits(vol)} گیگابایت\n\n"
    )
    if discount:
        invoice += f"💸 تخفیف: {discount}٪\n"
        invoice += f"💵 قیمت اصلی: {fmt_price(base)}\n"
    invoice += f"💰 مبلغ قابل پرداخت: <b>{fmt_price(final)}</b>\n\n"
    invoice += "سفارش شما آماده پرداخت است."

    await message.answer(invoice, reply_markup=kb_invoice(product_key), parse_mode=ParseMode.HTML)


# ===== کد تخفیف =====
@dp.callback_query(F.data.startswith("discount_"))
async def cb_apply_discount(call: CallbackQuery, state: FSMContext):
    await call.answer()
    product_key = call.data.split("_", 1)[1]
    await state.update_data(product=product_key)
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
    product_key = data.get("product")
    if not product_key:
        await message.answer("❌ خطا. /start را بزنید.")
        await state.clear()
        return
    service, vol = parse_product(product_key)
    base = get_price(service, vol)
    final = int(base * (100 - percent) / 100)
    await state.update_data(discount_percent=percent, base_price=base, final_price=final)
    if not data.get("username"):
        await state.set_state(BuyStates.waiting_username)
        await message.answer(
            f"✅ کد تخفیف {percent}٪ اعمال شد.\n\n"
            "حالا یک نام کاربری با حروف لاتین (۳ تا ۲۰ کاراکتر) ارسال کنید 👇"
        )
    else:
        username = data["username"]
        spec = SERVICES[service]["spec"]
        invoice = (
            f"🧾 پیش‌فاکتور\n\n"
            f"👤 نام کاربری: <code>{username}</code>\n"
            f"📦 سرویس: {product_label(service, vol)}\n"
            f"📋 مشخصات: {spec}\n"
            f"💾 حجم: {fa_digits(vol)} گیگابایت\n\n"
            f"💸 تخفیف: {percent}٪\n"
            f"💵 قیمت اصلی: {fmt_price(base)}\n"
            f"💰 مبلغ قابل پرداخت: <b>{fmt_price(final)}</b>"
        )
        await message.answer(invoice, reply_markup=kb_invoice(product_key), parse_mode=ParseMode.HTML)


# ===== کارت به کارت =====
@dp.callback_query(F.data.startswith("paycard_"))
async def cb_pay_card(call: CallbackQuery, state: FSMContext):
    await call.answer()
    product_key = call.data.split("_", 1)[1]
    data = await state.get_data()
    if not data.get("username"):
        await call.answer("ابتدا نام کاربری را وارد کنید.", show_alert=True)
        return
    service, vol = parse_product(product_key)
    final = data.get("final_price") or get_price(service, vol)
    card = SETTINGS.get("card_number") or "تنظیم نشده"
    holder = SETTINGS.get("card_holder") or ""
    holder_line = f"به نام: {holder}" if holder else ""
    txt = (
        f"برای پرداخت، مبلغ {fmt_price(final)} را به شماره‌ی کارت زیر واریز کنید 👇🏻\n\n"
        f"====================\n\n"
        f"<code>{card}</code>\n"
        f"{holder_line}\n\n"
        f"====================\n\n"
        f"🟢 این تراکنش به مدت یک ساعت اعتبار دارد.\n"
        f"‼️ مسئولیت واریز اشتباهی با شماست.\n"
        f"🔝 بعد از پرداخت دکمه (ادامه مراحل) را بزنید و عکس رسید خود را ارسال کنید."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 ادامه مراحل (ارسال رسید)", callback_data=f"sendreceipt_{product_key}")],
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
    product_key = data.get("product")
    username = data.get("username")
    final = data.get("final_price")
    if not (product_key and username and final):
        await message.answer("❌ خطا. لطفاً از ابتدا اقدام کنید: /start")
        await state.clear()
        return
    service, vol = parse_product(product_key)
    photo_id = message.photo[-1].file_id
    rid = db_create_receipt(message.from_user.id, product_key, username, final, photo_id)
    await message.answer(
        "✅ اوکی! رسید شما دریافت شد.\n"
        "💳 پرداخت شما در سریع‌ترین زمان ممکن تایید می‌شود."
    )
    caption = (
        f"🧾 رسید جدید #{rid}\n"
        f"👤 کاربر: {message.from_user.full_name}\n"
        f"🆔 آیدی: <code>{message.from_user.id}</code>\n"
        f"📦 سرویس: {product_label(service, vol)}\n"
        f"🧾 یوزرنیم: <code>{username}</code>\n"
        f"💰 مبلغ: {fmt_price(final)}"
    )
    if service in ("openvpn", "l2tp"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید رسید", callback_data=f"adm_approve_{rid}"),
                InlineKeyboardButton(text="❌ رد رسید", callback_data=f"adm_reject_{rid}"),
            ],
            [
                InlineKeyboardButton(text="📁 فایل + یوزر/پسورد", callback_data=f"adm_ovpnfile_{rid}"),
                InlineKeyboardButton(text="🔗 لینک", callback_data=f"adm_ovpnlink_{rid}"),
            ],
        ])
    else:
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


# ==================== سرویس‌های من ====================
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
        rid, product, username = r
        service, vol = parse_product(product)
        btns.append([InlineKeyboardButton(
            text=f"👤 {username}  |  {product_label(service, vol)}",
            callback_data=f"viewsvc_{rid}",
        )])
    btns.append([btn(BUTTON_LABELS["back"], "back", callback_data="back_main")])
    await call.message.edit_text("📦 سرویس‌های شما:\nروی نام کاربری بزنید 👇", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@dp.callback_query(F.data.startswith("viewsvc_"))
async def cb_view_service(call: CallbackQuery):
    await call.answer()
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    (_, _, product, username, amount, _, status,
     config, sub_link, ovpn_file_id, ovpn_user, ovpn_pass, ovpn_link, _) = r
    service, vol = parse_product(product)
    spec = SERVICES.get(service, {}).get("spec", "")
    txt = (
        f"📦 سرویس شما\n\n"
        f"👤 نام کاربری: <code>{username}</code>\n"
        f"📦 سرویس: {product_label(service, vol)}\n"
        f"📋 مشخصات: {spec}\n"
        f"💾 حجم: {fa_digits(vol)} گیگابایت\n"
        f"💰 مبلغ پرداختی: {fmt_price(amount)}"
    )
    rows = []
    if service == "v2ray":
        if sub_link:
            rows.append([InlineKeyboardButton(text="🔗 دریافت لینک ساب", callback_data=f"getsub_{rid}")])
        if config:
            rows.append([InlineKeyboardButton(text="📄 دریافت کانفیگ", callback_data=f"getcfg_{rid}")])
        if not rows:
            txt += "\n\n⏳ کانفیگ هنوز برای شما ارسال نشده. لطفاً صبور باشید."
    else:  # openvpn / l2tp
        if ovpn_file_id:
            rows.append([InlineKeyboardButton(text="📁 دریافت فایل", callback_data=f"getovpnfile_{rid}")])
        if ovpn_user or ovpn_pass:
            rows.append([InlineKeyboardButton(text="🔑 یوزر/پسورد", callback_data=f"getovpnup_{rid}")])
        if ovpn_link:
            rows.append([InlineKeyboardButton(text="🔗 دریافت لینک", callback_data=f"getovpnlink_{rid}")])
        if not rows:
            txt += "\n\n⏳ سرویس هنوز برای شما ارسال نشده. لطفاً صبور باشید."
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


@dp.callback_query(F.data.startswith("getovpnfile_"))
async def cb_get_ovpn_file(call: CallbackQuery):
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    fid = r[9]
    if not fid:
        await call.answer("فایل موجود نیست.", show_alert=True); return
    await call.answer()
    try:
        await bot.send_document(call.from_user.id, fid, caption="📁 فایل سرویس شما")
    except Exception:
        await call.message.answer("❌ ارسال فایل ناموفق بود.")


@dp.callback_query(F.data.startswith("getovpnup_"))
async def cb_get_ovpn_up(call: CallbackQuery):
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    user = r[10]; pwd = r[11]
    await call.answer()
    await call.message.answer(
        f"🔑 اطلاعات اتصال شما:\n\n"
        f"👤 یوزر: <code>{user}</code>\n"
        f"🔒 پسورد: <code>{pwd}</code>",
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data.startswith("getovpnlink_"))
async def cb_get_ovpn_link(call: CallbackQuery):
    rid = int(call.data.split("_", 1)[1])
    r = db_get_receipt(rid)
    if not r or r[1] != call.from_user.id:
        await call.answer("یافت نشد", show_alert=True); return
    lnk = r[12]
    if not lnk:
        await call.answer("لینک موجود نیست.", show_alert=True); return
    await call.answer()
    await call.message.answer(f"🔗 لینک شما:\n\n<code>{lnk}</code>", parse_mode=ParseMode.HTML)


# ==================== حساب / دعوت / پشتیبانی ====================
@dp.callback_query(F.data == "account")
async def cb_account(call: CallbackQuery):
    await call.answer()
    u = call.from_user
    info = db_get_user_info(u.id)
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
        "👨🏻‍💻 اطلاعات حساب کاربری شما:\n\n"
        f"💰 موجودی: {fa_digits('{:,}'.format(info['balance']))} تومان\n\n"
        f"🕴🏻 آیدی عددی: {fa_digits(u.id)}\n"
        f"🛍 تعداد سرویس‌ها: {fa_digits(info['services'])}\n"
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


# ==================== آموزش ====================
async def _send_tutorials(chat_id: int, service: str):
    items = SETTINGS.get("tutorials", {}).get(service, [])
    if not items:
        await bot.send_message(
            chat_id,
            f"📚 هنوز آموزشی برای {SERVICES[service]['label']} ثبت نشده است.",
        )
        return
    for it in items:
        t = it.get("type")
        fid = it.get("file_id", "")
        cap = it.get("text", "") or None
        try:
            if t == "photo":
                await bot.send_photo(chat_id, fid, caption=cap)
            elif t == "video":
                await bot.send_video(chat_id, fid, caption=cap)
            elif t == "document":
                await bot.send_document(chat_id, fid, caption=cap)
            elif t == "text":
                await bot.send_message(chat_id, cap or "")
            else:
                pass
        except Exception as e:
            logger.warning(f"send tutorial failed: {e}")


@dp.callback_query(F.data == "tut_openvpn")
async def cb_tut_openvpn(call: CallbackQuery):
    await call.answer()
    await call.message.answer(f"📚 آموزش {SERVICES['openvpn']['label']}:")
    await _send_tutorials(call.from_user.id, "openvpn")


@dp.callback_query(F.data == "tut_v2ray")
async def cb_tut_v2ray(call: CallbackQuery):
    await call.answer()
    await call.message.answer(f"📚 آموزش {SERVICES['v2ray']['label']}:")
    await _send_tutorials(call.from_user.id, "v2ray")


# ==================== پنل مدیریت ====================
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.answer("❌ دسترسی ندارید.", show_alert=True)
        return
    await call.message.edit_text("👑 پنل مدیریت", reply_markup=kb_admin())


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
        service, vol = parse_product(product)
        try:
            await bot.send_message(
                uid,
                f"✅ رسید #{rid} شما تایید شد!\n"
                f"📦 سرویس: {product_label(service, vol)}\n"
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
    _, uid, product, username, amount, _, status, *_ = r
    if status == "approved":
        await call.answer("قبلاً تایید شده", show_alert=True); return
    db_approve_receipt(rid)
    service, vol = parse_product(product)
    try:
        await bot.send_message(
            uid,
            f"✅ رسید #{rid} شما تایید شد!\n"
            f"📦 سرویس: {product_label(service, vol)}\n"
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
    _, uid, product, username, amount, _, status, *_ = r
    if status == "rejected":
        await call.answer("قبلاً رد شده", show_alert=True); return
    db_set_receipt_status(rid, "rejected")
    service, vol = parse_product(product)
    try:
        await bot.send_message(
            uid,
            f"❌ رسید #{rid} شما توسط ادمین رد شد.\n"
            f"📦 سرویس: {product_label(service, vol)}\n"
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


# ==================== تحویل V2Ray ====================
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
    db_set_receipt_field(rid, config=cfg)
    if mode == "cfgsub":
        await state.set_state(AdminStates.waiting_sub)
        await message.answer("✅ کانفیگ ثبت شد.\n\n🔗 حالا لطفاً ساب را ارسال کنید 👇")
        return
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; product = r[2]; username = r[3]
        service, vol = parse_product(product)
        try:
            await bot.send_message(
                uid,
                f"📦 سرویس شما آماده شد!\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"📦 سرویس: {product_label(service, vol)}\n\n"
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
    db_set_receipt_field(rid, sub_link=sub)
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; product = r[2]; username = r[3]; cfg = r[7]
        service, vol = parse_product(product)
        try:
            await bot.send_message(
                uid,
                f"📦 سرویس شما آماده شد!\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"📦 سرویس: {product_label(service, vol)}\n\n"
                f"📄 کانفیگ:\n<code>{cfg}</code>\n\n"
                f"🔗 ساب:\n<code>{sub}</code>",
                parse_mode=ParseMode.HTML,
            )
            await _grant_referral_if_first_purchase(uid)
        except Exception as e:
            logger.warning(f"send config+sub to {uid} failed: {e}")
    await state.clear()
    await message.answer(f"✅ کانفیگ + ساب برای کاربر ارسال شد. (رسید #{rid})")


# ==================== تحویل OpenVPN ====================
def _ovpn_tutorial_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 آموزش", callback_data="tut_openvpn")]
    ])


async def _send_ovpn_completion(uid: int, rid: int, intro: str):
    try:
        await bot.send_message(
            uid,
            intro + "\n\nاگر بلد نیستی آموزش ببین 👇",
            reply_markup=_ovpn_tutorial_kb(),
        )
    except Exception as e:
        logger.warning(f"send ovpn completion failed: {e}")


@dp.callback_query(F.data.startswith("adm_ovpnfile_"))
async def cb_adm_ovpn_file(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    rid = int(call.data.split("_")[2])
    await state.update_data(deliver_rid=rid)
    await state.set_state(AdminStates.ovpn_waiting_file)
    await call.message.answer(f"📁 برای رسید #{rid}\n\nلطفاً فایل را بفرستید 👇")


@dp.message(AdminStates.ovpn_waiting_file)
async def msg_ovpn_file(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.document:
        await message.answer("❌ لطفاً فایل (Document) ارسال کنید."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    if not rid:
        await state.clear(); return
    db_set_receipt_field(rid, ovpn_file_id=message.document.file_id)
    await state.set_state(AdminStates.ovpn_waiting_user)
    await message.answer("✅ فایل ثبت شد.\n\n👤 لطفاً یوزر بفرستید 👇")


@dp.message(AdminStates.ovpn_waiting_user)
async def msg_ovpn_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    user = (message.text or "").strip()
    if not user:
        await message.answer("❌ یوزر خالی است."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    if not rid:
        await state.clear(); return
    db_set_receipt_field(rid, ovpn_user=user)
    await state.set_state(AdminStates.ovpn_waiting_pass)
    await message.answer("✅ یوزر ثبت شد.\n\n🔒 لطفاً پسورد بفرستید 👇")


@dp.message(AdminStates.ovpn_waiting_pass)
async def msg_ovpn_pass(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    pwd = (message.text or "").strip()
    if not pwd:
        await message.answer("❌ پسورد خالی است."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    if not rid:
        await state.clear(); return
    db_set_receipt_field(rid, ovpn_pass=pwd)
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; product = r[2]; username = r[3]
        fid = r[9]; user = r[10]
        service, vol = parse_product(product)
        try:
            await bot.send_document(
                uid, fid,
                caption=(
                    f"📦 سرویس شما آماده شد!\n"
                    f"👤 یوزرنیم: {username}\n"
                    f"📦 {product_label(service, vol)}\n"
                    f"📋 {SERVICES[service]['spec']}"
                ),
            )
            await bot.send_message(
                uid,
                f"🔑 اطلاعات اتصال:\n\n"
                f"👤 یوزر: <code>{user}</code>\n"
                f"🔒 پسورد: <code>{pwd}</code>",
                parse_mode=ParseMode.HTML,
            )
            await _send_ovpn_completion(uid, rid, "🎉 سرویس شما تحویل داده شد.")
            await _grant_referral_if_first_purchase(uid)
        except Exception as e:
            logger.warning(f"deliver ovpn file failed: {e}")
    await state.clear()
    await message.answer(f"✅ سرویس OpenVPN (فایل + یوزر/پسورد) برای کاربر ارسال شد. (رسید #{rid})")


@dp.callback_query(F.data.startswith("adm_ovpnlink_"))
async def cb_adm_ovpn_link(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    rid = int(call.data.split("_")[2])
    await state.update_data(deliver_rid=rid)
    await state.set_state(AdminStates.ovpn_waiting_link)
    await call.message.answer(f"🔗 برای رسید #{rid}\n\nلطفاً لینک بفرستید 👇")


@dp.message(AdminStates.ovpn_waiting_link)
async def msg_ovpn_link(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    lnk = (message.text or "").strip()
    if not lnk:
        await message.answer("❌ لینک خالی است."); return
    data = await state.get_data()
    rid = data.get("deliver_rid")
    if not rid:
        await state.clear(); return
    db_set_receipt_field(rid, ovpn_link=lnk)
    db_set_receipt_status(rid, "approved")
    r = db_get_receipt(rid)
    if r:
        uid = r[1]; product = r[2]; username = r[3]
        service, vol = parse_product(product)
        try:
            await bot.send_message(
                uid,
                f"📦 سرویس شما آماده شد!\n"
                f"👤 یوزرنیم: <code>{username}</code>\n"
                f"📦 {product_label(service, vol)}\n"
                f"📋 {SERVICES[service]['spec']}\n\n"
                f"🔗 لینک:\n<code>{lnk}</code>",
                parse_mode=ParseMode.HTML,
            )
            await _send_ovpn_completion(uid, rid, "🎉 سرویس شما تحویل داده شد.")
            await _grant_referral_if_first_purchase(uid)
        except Exception as e:
            logger.warning(f"deliver ovpn link failed: {e}")
    await state.clear()
    await message.answer(f"✅ لینک OpenVPN برای کاربر ارسال شد. (رسید #{rid})")


# ==================== بن/آنبن ====================
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


# ==================== کد تخفیف ====================
@dp.callback_query(F.data == "adm_discount")
async def cb_adm_discount(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await state.set_state(AdminStates.discount_input)
    await call.message.edit_text(
        "🎁 لطفاً کد تخفیف را به این صورت ارسال کنید:\n\n"
        "<b>Badboy50</b>\n\n"
        "یعنی کلمه + درصد در انتها (۱ تا ۱۰۰).",
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


# ==================== مدیریت محصولات و قیمت‌ها ====================
@dp.callback_query(F.data == "adm_prices_root")
async def cb_adm_prices_root(call: CallbackQuery, state: FSMContext):
    """منوی اصلی مدیریت محصولات و قیمت‌ها — انتخاب سرویس."""
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await state.clear()
    await call.answer()
    await call.message.edit_text(
        "💵 مدیریت محصولات و قیمت‌ها\n\n"
        "یکی از سرویس‌های زیر را انتخاب کنید 👇",
        reply_markup=kb_admin_prices_root(),
    )


@dp.callback_query(F.data == "adm_prices_v2ray")
async def cb_adm_prices_v2ray(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "💵 مدیریت محصولات ویتوری (V2Ray)\n\n"
        "✏️ روی هر محصول بزنید تا قیمت آن را تغییر دهید\n"
        "🗑 برای حذف، روی دکمه حذف کنار محصول بزنید\n"
        "➕ برای افزودن محصول جدید، دکمه پایین را بزنید",
        reply_markup=kb_admin_prices("v2ray"),
    )


@dp.callback_query(F.data == "adm_prices_openvpn")
async def cb_adm_prices_openvpn(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "💵 مدیریت محصولات اوپن (Open VPN)\n\n"
        "✏️ روی هر محصول بزنید تا قیمت آن را تغییر دهید\n"
        "🗑 برای حذف، روی دکمه حذف کنار محصول بزنید\n"
        "➕ برای افزودن محصول جدید، دکمه پایین را بزنید",
        reply_markup=kb_admin_prices("openvpn"),
    )


@dp.callback_query(F.data == "adm_prices_l2tp")
async def cb_adm_prices_l2tp(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    await call.message.edit_text(
        "💵 مدیریت محصولات L2tp\n\n"
        "✏️ روی هر محصول بزنید تا قیمت آن را تغییر دهید\n"
        "🗑 برای حذف، روی دکمه حذف کنار محصول بزنید\n"
        "➕ برای افزودن محصول جدید، دکمه پایین را بزنید",
        reply_markup=kb_admin_prices("l2tp"),
    )


@dp.callback_query(F.data.startswith("setprice_"))
async def cb_set_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    parts = call.data.split("_", 2)
    if len(parts) < 3: return
    service, vol = parts[1], parts[2]
    if service not in SERVICES or vol not in SERVICES[service]["volumes"]:
        return
    await state.update_data(target_service=service, target_vol=vol)
    await state.set_state(AdminStates.set_price)
    cur = get_price(service, vol)
    await call.message.edit_text(
        f"💵 قیمت فعلی {product_label(service, vol)}: {fmt_price(cur)}\n\n"
        "قیمت جدید را به تومان (فقط عدد) ارسال کنید 👇",
        reply_markup=kb_back(f"adm_prices_{service}"),
    )


@dp.message(AdminStates.set_price)
async def msg_set_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    txt = re.sub(r"[^\d]", "", message.text or "")
    if not txt:
        await message.answer("❌ فقط عدد ارسال کنید."); return
    new_price = int(txt)
    data = await state.get_data()
    service = data.get("target_service")
    vol = data.get("target_vol")
    if not (service and vol):
        await state.clear(); return
    set_price(service, vol, new_price)
    await state.clear()
    await message.answer(
        f"✅ قیمت {product_label(service, vol)} به {fmt_price(new_price)} تنظیم شد.",
        reply_markup=kb_admin_prices(service),
    )


# ===== حذف محصول =====
@dp.callback_query(F.data.startswith("delprod_"))
async def cb_del_product(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    parts = call.data.split("_", 2)
    if len(parts) < 3:
        await call.answer("❌", show_alert=True); return
    service, vol = parts[1], parts[2]
    if service not in SERVICES:
        await call.answer("سرویس یافت نشد", show_alert=True); return
    label = product_label(service, vol) if vol in SERVICES[service]["volumes"] else f"{vol} گیگ"
    if remove_product(service, vol):
        await call.answer(f"🗑 «{label}» حذف شد", show_alert=False)
    else:
        await call.answer("❌ حذف نشد", show_alert=True)
    try:
        await call.message.edit_reply_markup(reply_markup=kb_admin_prices(service))
    except Exception:
        pass


# ===== افزودن محصول جدید =====
@dp.callback_query(F.data.startswith("addprod_"))
async def cb_add_product(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    service = call.data.split("_", 1)[1]
    if service not in SERVICES:
        await call.answer("سرویس یافت نشد", show_alert=True); return
    await call.answer()
    await state.update_data(addprod_service=service)
    await state.set_state(AdminStates.add_product_vol)
    await call.message.edit_text(
        f"➕ افزودن محصول جدید برای {SERVICES[service]['label']}\n\n"
        "🟢 لطفاً <b>حجم</b> محصول را به‌صورت عدد (به گیگابایت) ارسال کنید.\n"
        "مثال: <code>15</code> یا <code>۲۵</code>",
        reply_markup=kb_back(f"adm_prices_{service}"),
        parse_mode=ParseMode.HTML,
    )


@dp.message(AdminStates.add_product_vol)
async def msg_add_product_vol(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    # تبدیل ارقام فارسی به انگلیسی
    raw_en = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    txt = re.sub(r"[^\d]", "", raw_en)
    if not txt:
        await message.answer("❌ فقط عدد ارسال کنید (به گیگابایت).")
        return
    vol = txt
    data = await state.get_data()
    service = data.get("addprod_service")
    if not service or service not in SERVICES:
        await state.clear(); return
    if vol in SERVICES[service]["volumes"]:
        await message.answer(
            f"⚠️ محصول {fa_digits(vol)} گیگ از قبل وجود دارد.\n"
            "می‌توانید با ارسال قیمت جدید، قیمت آن را به‌روزرسانی کنید 👇"
        )
    await state.update_data(addprod_vol=vol)
    await state.set_state(AdminStates.add_product_price)
    await message.answer(
        f"✅ حجم ثبت شد: <b>{fa_digits(vol)} گیگ</b>\n\n"
        "💰 حالا <b>قیمت</b> را به تومان (فقط عدد) ارسال کنید 👇",
        parse_mode=ParseMode.HTML,
    )


@dp.message(AdminStates.add_product_price)
async def msg_add_product_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    raw_en = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    txt = re.sub(r"[^\d]", "", raw_en)
    if not txt:
        await message.answer("❌ فقط عدد ارسال کنید.")
        return
    price = int(txt)
    data = await state.get_data()
    service = data.get("addprod_service")
    vol = data.get("addprod_vol")
    if not (service and vol) or service not in SERVICES:
        await state.clear()
        return
    add_product(service, vol, price)
    await state.clear()
    await message.answer(
        f"✅ محصول جدید اضافه شد:\n\n"
        f"📦 سرویس: <b>{SERVICES[service]['label']}</b>\n"
        f"💾 حجم: <b>{fa_digits(vol)} گیگ</b>\n"
        f"💰 قیمت: <b>{fmt_price(price)}</b>",
        reply_markup=kb_admin_prices(service),
        parse_mode=ParseMode.HTML,
    )


# ==================== تنظیم شماره کارت ====================
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
    await message.answer("✅ شماره کارت ثبت شد.\n\n👤 حالا نام صاحب کارت را ارسال کنید 👇")


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


# ==================== تنظیم پشتیبانی ====================
@dp.callback_query(F.data == "adm_support")
async def cb_adm_support(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    cur = SETTINGS.get("support_id") or DEFAULT_SUPPORT_ID
    await state.set_state(AdminStates.set_support)
    await call.message.edit_text(
        f"🛟 آیدی پشتیبانی فعلی: {cur}\n\nآیدی جدید را ارسال کنید (مثلاً @VM_GOZARNET) 👇",
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


# ==================== چنل‌ها ====================
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
        "📡 یوزرنیم چنل را ارسال کنید (مثلاً @vm_vpn یا لینک کامل):",
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


# ==================== آپلود آموزش ====================
def _kb_tutorial_admin(service: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 پاک کردن همه آموزش‌ها", callback_data=f"adm_cleartut_{service}")],
        [InlineKeyboardButton(text="✅ تمام", callback_data="admin_panel")],
    ])


@dp.callback_query(F.data.startswith("adm_uptut_"))
async def cb_adm_uptut(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    await call.answer()
    service = call.data.split("_", 2)[2]
    if service not in SERVICES: return
    await state.update_data(tut_service=service)
    await state.set_state(AdminStates.upload_tutorial)
    items = SETTINGS.get("tutorials", {}).get(service, [])
    await call.message.edit_text(
        f"📚 آپلود آموزش {SERVICES[service]['label']}\n\n"
        f"تعداد فعلی آیتم‌ها: {fa_digits(len(items))}\n\n"
        "هر چی می‌خوای (عکس / ویدیو / فایل / متن) رو بفرست تا اضافه بشه.\n"
        "وقتی تموم شد روی «تمام» بزن.",
        reply_markup=_kb_tutorial_admin(service),
    )


@dp.callback_query(F.data.startswith("adm_cleartut_"))
async def cb_adm_cleartut(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌", show_alert=True); return
    service = call.data.split("_", 2)[2]
    if service not in SERVICES: return
    SETTINGS.setdefault("tutorials", {})[service] = []
    save_settings(SETTINGS)
    await call.answer("✅ پاک شد")
    await call.message.edit_text(
        f"📚 آپلود آموزش {SERVICES[service]['label']}\n\n"
        f"تعداد فعلی آیتم‌ها: ۰\n\n"
        "هر چی می‌خوای (عکس / ویدیو / فایل / متن) رو بفرست تا اضافه بشه.\n"
        "وقتی تموم شد روی «تمام» بزن.",
        reply_markup=_kb_tutorial_admin(service),
    )


@dp.message(AdminStates.upload_tutorial)
async def msg_upload_tutorial(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    service = data.get("tut_service")
    if service not in SERVICES:
        await state.clear(); return
    item = None
    if message.photo:
        item = {"type": "photo", "file_id": message.photo[-1].file_id, "text": message.caption or ""}
    elif message.video:
        item = {"type": "video", "file_id": message.video.file_id, "text": message.caption or ""}
    elif message.document:
        item = {"type": "document", "file_id": message.document.file_id, "text": message.caption or ""}
    elif message.text:
        item = {"type": "text", "file_id": "", "text": message.text}
    if not item:
        await message.answer("❌ نوع پیام پشتیبانی نمی‌شود.")
        return
    SETTINGS.setdefault("tutorials", {}).setdefault(service, []).append(item)
    save_settings(SETTINGS)
    items = SETTINGS["tutorials"][service]
    await message.answer(
        f"✅ اضافه شد. تعداد فعلی: {fa_digits(len(items))}\n\n"
        "می‌تونی آیتم بعدی رو بفرستی یا «تمام» رو بزنی.",
        reply_markup=_kb_tutorial_admin(service),
    )


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
