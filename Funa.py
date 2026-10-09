#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════
#   ⚡ ARYA BOT ⚡
#   ═══════════════════════════════════════════════════════

import asyncio
import os
import random
import re
import time
import logging
import traceback
import io
import json
import gzip
import subprocess
import tempfile
import urllib.parse
import urllib.request
import sys

# ═══════════════════════════════════════════════════════
# AUTO-INSTALLER (Docker me skip hoga)
# ═══════════════════════════════════════════════════════

REQUIRED_PIP = [
    "python-telegram-bot>=20.0",
    "yt-dlp",
    "pillow",
    "rlottie-python",
    "motor",
    "aiohttp",
]


def _run(cmd, check=False, capture=True):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, timeout=600
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def install_pip_packages():
    print("\n📦 Installing Python packages...")
    for pkg in REQUIRED_PIP:
        pkg_name = pkg.split(">=")[0].split("==")[0]
        import_name = {
            "python-telegram-bot": "telegram",
            "pillow": "PIL",
            "yt-dlp": "yt_dlp",
            "rlottie-python": "rlottie_python",
            "motor": "motor",
            "aiohttp": "aiohttp",
        }.get(pkg_name, pkg_name.replace("-", "_"))
        try:
            __import__(import_name)
            print(f"   ✓ {pkg_name}")
            continue
        except ImportError:
            pass
        print(f"   ⏳ Installing {pkg}...")
        rc, out = _run(f"{sys.executable} -m pip install --upgrade {pkg}")
        if rc != 0:
            rc, out = _run(f"{sys.executable} -m pip install --user {pkg}")
        if rc == 0:
            print(f"   ✅ {pkg_name}")
        else:
            print(f"   ❌ {pkg_name} FAIL: {out[-200:]}")


def install_ffmpeg():
    print("\n🎬 Checking ffmpeg...")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            print("   ✓ ffmpeg")
            return
    except Exception:
        pass
    if os.path.exists("/usr/bin/apt"):
        _run("sudo -n apt-get install -y ffmpeg")
    elif os.path.exists("/sbin/apk"):
        _run("apk add --no-cache ffmpeg")
    elif os.path.exists("/usr/bin/dnf"):
        _run("sudo -n dnf install -y ffmpeg")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            print("   ✅ ffmpeg")
        else:
            print("   ⚠️ ffmpeg missing")
    except Exception:
        print("   ⚠️ ffmpeg missing")


def bootstrap():
    print("\n⚡ ARYA BOT — AUTO SETUP")
    install_pip_packages()
    install_ffmpeg()
    print("✅ Setup complete\n")


if not os.path.exists("/.dockerenv"):
    bootstrap()
else:
    print("\n🐳 Docker detected — skipping auto-install\n")

# ═══════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════

try:
    from telegram import (
        Update, ChatMember, ChatMemberUpdated,
        InlineKeyboardButton, InlineKeyboardMarkup,
        ChatPermissions,
    )
    from telegram.ext import (
        Application,
        MessageHandler,
        ContextTypes,
        filters,
        ChatMemberHandler,
        CallbackQueryHandler,
    )
except ImportError:
    print("❌ pip install python-telegram-bot")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("❌ pip install yt-dlp")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
except ImportError:
    print("❌ pip install pillow")
    sys.exit(1)

try:
    from rlottie_python import LottieAnimation
    HAS_RLOTTIE = True
except Exception:
    HAS_RLOTTIE = False
    LottieAnimation = None

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    HAS_MONGO = True
except ImportError:
    HAS_MONGO = False
    AsyncIOMotorClient = None

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    web = None


# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════

TOKENS = [
    os.getenv("BOT_TOKEN", ""),
]

DOWNLOAD_DIR = "downloads"
FONT_DIR = "fonts"
COMMAND_PREFIX = "."
OWNER_ID = int(os.getenv("OWNER_ID", "8783901855"))

# ✅ FORCE JOIN — ENABLED
FORCE_JOIN_ENABLED = os.getenv("FORCE_JOIN_ENABLED", "True").lower() == "true"
FORCE_JOIN_LINK = os.getenv("FORCE_JOIN_LINK", "https://t.me/+e56LxHnciK5lOWI1")
FORCE_JOIN_CHAT_ID = int(os.getenv("FORCE_JOIN_CHAT_ID", "-1004343483155"))

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "please_set_a_long_random_secret")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
PORT = int(os.getenv("PORT", "10000"))

MONGO_URI = os.getenv("MONGO_URI", "")

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

apps = []
bots = []

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════

VERIFIED_USERS = set()
BLOCKED_USERS = set()
KNOWN_CHATS = set()
RR_USERS = {}
LOCKED_CHATS = set()

_mongo_client = None
_mongo_db = None
_use_mongo = False


async def init_mongo():
    global _mongo_client, _mongo_db, _use_mongo
    global VERIFIED_USERS, BLOCKED_USERS, KNOWN_CHATS, RR_USERS, LOCKED_CHATS

    if not HAS_MONGO or not MONGO_URI:
        print("⚠️ MongoDB URI nahi mila — in-memory storage use hoga")
        _use_mongo = False
        return
    try:
        _mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _mongo_db = _mongo_client["arya_bot"]
        await _mongo_client.admin.command("ping")
        _use_mongo = True
        print("✅ MongoDB Atlas connected")

        v = await _mongo_db.verified.find_one({"_id": "verified"})
        if v:
            VERIFIED_USERS = set(v.get("users", []))

        b = await _mongo_db.blocked.find_one({"_id": "blocked"})
        if b:
            BLOCKED_USERS = set(b.get("users", []))

        c = await _mongo_db.chats.find_one({"_id": "chats"})
        if c:
            KNOWN_CHATS = set(c.get("chats", []))

        r = await _mongo_db.rr.find_one({"_id": "rr"})
        if r:
            RR_USERS = {str(k): v for k, v in r.get("users", {}).items()}

        l = await _mongo_db.locked.find_one({"_id": "locked"})
        if l:
            LOCKED_CHATS = set(l.get("chats", []))

        print(f"📋 Loaded: {len(VERIFIED_USERS)} verified, "
              f"{len(BLOCKED_USERS)} blocked, {len(RR_USERS)} RR, "
              f"{len(LOCKED_CHATS)} locked, "
              f"{len(KNOWN_CHATS)} chats")
    except Exception as e:
        print(f"⚠️ MongoDB connect fail: {e}")
        _use_mongo = False


async def _save_collection(collection_name, doc):
    if not _use_mongo:
        return
    try:
        await _mongo_db[collection_name].replace_one(
            {"_id": doc["_id"]}, doc, upsert=True
        )
    except Exception as e:
        logger.error(f"MongoDB save {collection_name}: {e}")


async def save_verified():
    await _save_collection("verified", {"_id": "verified", "users": list(VERIFIED_USERS)})


async def save_blocked():
    await _save_collection("blocked", {"_id": "blocked", "users": list(BLOCKED_USERS)})


async def save_chats():
    await _save_collection("chats", {"_id": "chats", "chats": list(KNOWN_CHATS)})


async def save_rr():
    await _save_collection("rr", {"_id": "rr", "users": dict(RR_USERS)})


async def save_locked():
    await _save_collection("locked", {"_id": "locked", "chats": list(LOCKED_CHATS)})


# ═══════════════════════════════════════════════════════
# FONTS
# ═══════════════════════════════════════════════════════

FONTS_TO_DOWNLOAD = {
    "Anton": ["https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"],
    "BebasNeue": ["https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"],
    "Bungee": ["https://github.com/google/fonts/raw/main/ofl/bungee/Bungee-Regular.ttf"],
    "BlackOpsOne": ["https://github.com/google/fonts/raw/main/ofl/blackopsone/BlackOpsOne-Regular.ttf"],
    "Bangers": ["https://github.com/google/fonts/raw/main/ofl/bangers/Bangers-Regular.ttf"],
    "RussoOne": ["https://github.com/google/fonts/raw/main/ofl/russoone/RussoOne-Regular.ttf"],
    "Staatliches": ["https://github.com/google/fonts/raw/main/ofl/staatliches/Staatliches-Regular.ttf"],
    "Orbitron": ["https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf"],
    "SairaStencil": ["https://github.com/google/fonts/raw/main/ofl/sairastencilone/SairaStencilOne-Regular.ttf"],
    "Teko": ["https://github.com/google/fonts/raw/main/ofl/teko/Teko%5Bwght%5D.ttf"],
}

_font_paths = []
_fonts_loaded = False


def _download_font(name, urls):
    path = os.path.join(FONT_DIR, f"{name}.ttf")
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        try:
            ImageFont.truetype(path, 40)
            return path
        except Exception:
            try:
                os.remove(path)
            except Exception:
                pass
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) < 10000:
                continue
            with open(path, "wb") as f:
                f.write(data)
            ImageFont.truetype(path, 40)
            logger.info(f"✓ Font {name}")
            return path
        except Exception as e:
            logger.warning(f"Font {name} fail: {e}")
    return None


def load_all_fonts():
    global _font_paths, _fonts_loaded
    if _fonts_loaded:
        return _font_paths
    os.makedirs(FONT_DIR, exist_ok=True)
    logger.info("Downloading fonts...")
    paths = []
    for name, urls in FONTS_TO_DOWNLOAD.items():
        p = _download_font(name, urls)
        if p:
            paths.append(p)
    for sf in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "arialbd.ttf",
    ]:
        try:
            ImageFont.truetype(sf, 40)
            paths.append(sf)
        except Exception:
            pass
    if not paths:
        paths = [None]
    _font_paths = paths
    _fonts_loaded = True
    logger.info(f"Fonts ready: {len(paths)}")
    return _font_paths


def _get_font(size):
    if not _font_paths:
        return ImageFont.load_default()
    fp = random.choice(_font_paths)
    if fp is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(fp, size)
    except Exception:
        return ImageFont.load_default()


def _find_font_path():
    for p in _font_paths:
        if p and os.path.exists(p):
            return p
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]:
        if os.path.exists(p):
            return p
    return None


# ═══════════════════════════════════════════════════════
# YT-DLP
# ═══════════════════════════════════════════════════════

def get_base_ydl_opts(extra: dict = None) -> dict:
    opts = {
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage", "configs"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "socket_timeout": 60, "retries": 5, "fragment_retries": 5,
        "extractor_retries": 3, "default_search": "ytsearch1",
        "nocheckcertificate": True,
    }
    if extra:
        opts.update(extra)
    return opts


# ═══════════════════════════════════════════════════════
# DEDUP
# ═══════════════════════════════════════════════════════

_processed = {}
_dedup_lock = asyncio.Lock()


def dedup(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return await func(update, context)
        key = (update.message.chat_id, update.message.message_id)
        now = time.time()
        async with _dedup_lock:
            if len(_processed) > 3000:
                cutoff = now - 120
                for k in list(_processed.keys()):
                    if _processed[k] < cutoff:
                        del _processed[k]
            if key in _processed:
                return
            _processed[key] = now
        return await func(update, context)
    return wrapper


# ═══════════════════════════════════════════════════════
# SAFE HELPERS
# ═══════════════════════════════════════════════════════

async def safe_reply(message, text, **kwargs):
    try:
        return await message.reply_text(text, **kwargs)
    except Exception as e:
        logger.error(f"safe_reply: {e}")
        return None


async def safe_edit(message, text, **kwargs):
    try:
        return await message.edit_text(text, **kwargs)
    except Exception as e:
        logger.error(f"safe_edit: {e}")
        return None


async def safe_delete(message):
    try:
        await message.delete()
    except Exception:
        pass


def _get_target_name(update: Update):
    try:
        if (update.message.reply_to_message
                and update.message.reply_to_message.from_user):
            u = update.message.reply_to_message.from_user
            if u.username:
                return f"@{u.username}"
            return u.first_name
    except Exception:
        pass
    return None


def is_owner(user_id):
    return OWNER_ID and user_id == OWNER_ID


async def is_group_admin(chat_id, user_id, context):
    if is_owner(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        logger.error(f"is_group_admin error: {e}")
        return False


# ═══════════════════════════════════════════════════════
# FORCE JOIN (ENABLED)
# ═══════════════════════════════════════════════════════

async def is_user_joined(update, context):
    if not FORCE_JOIN_ENABLED or not FORCE_JOIN_CHAT_ID:
        return True
    user_id = update.effective_user.id
    if is_owner(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(FORCE_JOIN_CHAT_ID, user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
        return False
    except Exception as e:
        logger.error(f"Join check error (user {user_id}): {e}")
        return False


async def send_join_message(update, context):
    keyboard = [
        [InlineKeyboardButton("🔗 Join Group", url=FORCE_JOIN_LINK)],
        [InlineKeyboardButton("✅ I'm Joined", callback_data="check_join")],
    ]
    await safe_reply(
        update.message,
        "⚠️ **GROUP JOIN KARO** ⚠️\n\n"
        "Bot use karne ke liye pehle group join karna zaroori hai.\n\n"
        "1️⃣ Neeche **Join Group** button dabao\n"
        "2️⃣ Group join karo\n"
        "3️⃣ Wapas aake **I'm Joined** button dabao\n\n"
        "✅ Join karne ke baad hi bot kaam karega.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def check_join_callback(update, context):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    user_id = query.from_user.id
    if not FORCE_JOIN_ENABLED or not FORCE_JOIN_CHAT_ID:
        try:
            await query.edit_message_text("✅ Force-join disabled.")
        except Exception:
            pass
        return
    try:
        member = await context.bot.get_chat_member(FORCE_JOIN_CHAT_ID, user_id)
        if member.status in ("member", "administrator", "creator"):
            VERIFIED_USERS.add(user_id)
            await save_verified()
            await query.edit_message_text(
                "✅ **Verified!** Ab tum bot use kar sakte ho.\n"
                f"`{COMMAND_PREFIX}help` bhejo commands ke liye.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                "❌ Tumne abhi group join nahi kiya.\n\n"
                "Pehle **Join Group** button dabao, group join karo, "
                "phir **I'm Joined** dabao.",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Check join callback: {e}")
        try:
            await query.edit_message_text(
                "⚠️ Error aaya. Bot ko force-join group me add karo, "
                "phir dobara try karo."
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
# IMAGE SEARCH
# ═══════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _bing_image_search(query):
    url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}&form=HDRSC2&first=1"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    urls = re.findall(r'"murl":"(https?://[^"]+?)"', html)
    urls += re.findall(r"&quot;murl&quot;:&quot;(https?://[^&]+?)&quot;", html)
    good = []
    for u in set(urls):
        if any(x in u.lower() for x in [".jpg", ".jpeg", ".png", ".webp"]):
            good.append(u)
    return good


def _pinterest_html(query):
    url = f"https://in.pinterest.com/search/pins/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    urls = re.findall(r'https://i\.pinimg\.com/[^\s"\\]+\.(?:jpg|jpeg|png|webp)', html)
    urls = [u for u in urls if "/originals/" in u or "/736x/" in u or "/564x/" in u]
    return list(set(urls))


def _age_to_word(age):
    if age <= 0:
        return ""
    if age <= 2:
        return "baby"
    if age <= 4:
        return "toddler"
    if age <= 12:
        return "kid"
    if age <= 18:
        return "teenage"
    if age <= 25:
        return "young"
    if age <= 45:
        return "adult"
    if age <= 60:
        return "middle aged"
    return "old"


def _build_logo_queries(gender, age):
    g = "boy" if gender == "boy" else "girl"
    age_w = _age_to_word(age)
    if age_w:
        return [
            f"{age_w} {g} portrait photography",
            f"{age} year old {g} dp",
            f"{age_w} {g} stylish photo",
            f"{g} {age} years attitude dp",
        ]
    return [
        f"stylish {g} portrait",
        f"{g} attitude dp hd",
        f"handsome {g}" if gender == "boy" else f"beautiful {g}",
    ]


def _fetch_best_image(queries, min_size=5000, min_wh=250):
    random.shuffle(queries)
    all_images = []
    for q in queries[:4]:
        try:
            imgs = _bing_image_search(q)
            if imgs:
                all_images.extend(imgs)
                if len(all_images) >= 25:
                    break
        except Exception as e:
            logger.warning(f"Bing fail '{q}': {e}")
    if len(all_images) < 8:
        for q in queries[:3]:
            try:
                imgs = _pinterest_html(q)
                if imgs:
                    all_images.extend(imgs)
                    if len(all_images) >= 20:
                        break
            except Exception as e:
                logger.warning(f"Pinterest fail '{q}': {e}")
    if not all_images:
        raise Exception("Koi image nahi mili. Dobara try karo.")
    all_images = list(set(all_images))
    random.shuffle(all_images)
    for url in all_images[:15]:
        try:
            req = urllib.request.Request(
                url, headers={**HEADERS, "Referer": "https://www.bing.com/"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) < min_size:
                continue
            try:
                im = Image.open(io.BytesIO(data))
                w, h = im.size
                if w < min_wh or h < min_wh:
                    continue
                im.verify()
            except Exception:
                continue
            return url, data
        except Exception as e:
            logger.warning(f"DL fail: {e}")
            continue
    raise Exception("Image download fail. Dobara try karo.")


def fetch_random_image(gender="boy", age=0):
    return _fetch_best_image(_build_logo_queries(gender, age))


def fetch_famous_image(search_term):
    queries = [
        f"{search_term} famous",
        f"famous {search_term}",
        f"{search_term} high resolution wallpaper",
        f"{search_term} hd portrait",
        f"{search_term} iconic photo",
        f"{search_term} 4k",
    ]
    return _fetch_best_image(queries, min_size=8000, min_wh=300)


# ═══════════════════════════════════════════════════════
# TEXT STYLES
# ═══════════════════════════════════════════════════════

def _center_position(draw, text, font, W, H, sw=0):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=sw)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (W - tw) // 2 - bbox[0]
    y = (H - th) // 2 - bbox[1]
    return x, y, tw, th


def style_1_red_white_glow(draw, text, font, x, y):
    for r in range(22, 0, -2):
        draw.text((x + r, y), text, font=font, fill=(220, 20, 20, 50))
        draw.text((x - r, y), text, font=font, fill=(220, 20, 20, 50))
        draw.text((x, y + r), text, font=font, fill=(220, 20, 20, 50))
        draw.text((x, y - r), text, font=font, fill=(220, 20, 20, 50))
    draw.text((x + 6, y + 6), text, font=font, fill=(0, 0, 0, 240))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=8, stroke_fill=(200, 10, 10))


def style_2_split_red_white(draw, text, font, x, y):
    if len(text) < 2:
        draw.text((x, y), text, font=font, fill=(255, 255, 255),
                  stroke_width=8, stroke_fill=(0, 0, 0))
        return
    draw.text((x + 6, y + 6), text, font=font, fill=(0, 0, 0, 240))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=9, stroke_fill=(0, 0, 0))
    first = text[0]
    draw.text((x, y), first, font=font, fill=(220, 20, 20, 255),
              stroke_width=9, stroke_fill=(0, 0, 0))


def style_3_bloody_red(draw, text, font, x, y, tw, th):
    for _ in range(80):
        dx = random.randint(-60, tw + 60)
        dy = random.randint(-60, th + 60)
        r = random.randint(2, 12)
        draw.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r],
                     fill=(170, 5, 5, 200))
    draw.text((x + 7, y + 7), text, font=font, fill=(0, 0, 0, 245))
    draw.text((x, y), text, font=font, fill=(225, 15, 15, 255),
              stroke_width=8, stroke_fill=(0, 0, 0))


def style_4_white_red_shadow(draw, text, font, x, y):
    for off in range(20, 0, -2):
        draw.text((x + off, y + off), text, font=font, fill=(180, 10, 10, 80))
    draw.text((x + 10, y + 10), text, font=font, fill=(215, 15, 15, 250))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=8, stroke_fill=(0, 0, 0))


def style_5_metallic_red(draw, text, font, x, y):
    for r in range(20, 0, -2):
        for dx in range(-r, r + 1, 3):
            for dy in range(-r, r + 1, 3):
                if abs(dx) + abs(dy) >= r - 3:
                    draw.text((x + dx, y + dy), text, font=font,
                              fill=(190, 20, 20, 55))
    draw.text((x + 6, y + 6), text, font=font, fill=(15, 15, 25, 235))
    draw.text((x, y), text, font=font, fill=(240, 240, 250, 255),
              stroke_width=6, stroke_fill=(20, 20, 30))


def style_6_neon_glow(draw, text, font, x, y):
    for r in range(18, 0, -2):
        draw.text((x + r, y), text, font=font, fill=(255, 0, 60, 60))
        draw.text((x - r, y), text, font=font, fill=(255, 0, 60, 60))
        draw.text((x, y + r), text, font=font, fill=(255, 0, 60, 60))
        draw.text((x, y - r), text, font=font, fill=(255, 0, 60, 60))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=14, stroke_fill=(210, 5, 35))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=3, stroke_fill=(255, 255, 255))


def style_7_fire_burst(draw, text, font, x, y):
    for r in range(25, 0, -2):
        draw.text((x + r, y), text, font=font, fill=(255, 90, 0, 55))
        draw.text((x - r, y), text, font=font, fill=(255, 90, 0, 55))
        draw.text((x, y + r), text, font=font, fill=(255, 90, 0, 55))
        draw.text((x, y - r), text, font=font, fill=(255, 90, 0, 55))
    draw.text((x + 6, y + 6), text, font=font, fill=(140, 20, 0, 240))
    draw.text((x, y), text, font=font, fill=(255, 230, 100, 255),
              stroke_width=8, stroke_fill=(160, 25, 0))


def style_8_cyber_teal(draw, text, font, x, y):
    for r in range(20, 0, -2):
        draw.text((x + r, y), text, font=font, fill=(0, 220, 220, 60))
        draw.text((x - r, y), text, font=font, fill=(0, 220, 220, 60))
        draw.text((x, y + r), text, font=font, fill=(0, 220, 220, 60))
        draw.text((x, y - r), text, font=font, fill=(0, 220, 220, 60))
    draw.text((x + 5, y + 5), text, font=font, fill=(0, 0, 0, 240))
    draw.text((x, y), text, font=font, fill=(220, 250, 255, 255),
              stroke_width=6, stroke_fill=(0, 80, 100))


def style_9_gold_dark(draw, text, font, x, y):
    for r in range(22, 0, -2):
        draw.text((x + r, y), text, font=font, fill=(230, 180, 40, 55))
        draw.text((x - r, y), text, font=font, fill=(230, 180, 40, 55))
        draw.text((x, y + r), text, font=font, fill=(230, 180, 40, 55))
        draw.text((x, y - r), text, font=font, fill=(230, 180, 40, 55))
    draw.text((x + 6, y + 6), text, font=font, fill=(0, 0, 0, 240))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=7, stroke_fill=(180, 130, 20))


def style_10_double_stroke(draw, text, font, x, y):
    draw.text((x + 7, y + 7), text, font=font, fill=(0, 0, 0, 240))
    draw.text((x, y), text, font=font, fill=(220, 10, 10, 255),
              stroke_width=12, stroke_fill=(220, 10, 10))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=7, stroke_fill=(255, 255, 255))
    draw.text((x, y), text, font=font, fill=(200, 10, 10, 255),
              stroke_width=3, stroke_fill=(200, 10, 10))


STYLES = [
    ("red_white_glow", style_1_red_white_glow),
    ("split_red_white", style_2_split_red_white),
    ("bloody_red", style_3_bloody_red),
    ("white_red_shadow", style_4_white_red_shadow),
    ("metallic_red", style_5_metallic_red),
    ("neon_glow", style_6_neon_glow),
    ("fire_burst", style_7_fire_burst),
    ("cyber_teal", style_8_cyber_teal),
    ("gold_dark", style_9_gold_dark),
    ("double_stroke", style_10_double_stroke),
]


# ═══════════════════════════════════════════════════════
# CREATE LOGO
# ═══════════════════════════════════════════════════════

def create_logo(img_bytes, name, output_path, darken=0.65):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    W, H = img.size
    target = 1080
    if W < H:
        new_w, new_h = target, int(H * (target / W))
    else:
        new_h, new_w = target, int(W * (target / H))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    if new_w > new_h:
        left = (new_w - target) // 2
        img = img.crop((left, 0, left + target, new_h))
    else:
        top = (new_h - target) // 2
        img = img.crop((0, top, new_w, top + target))

    tw, th = target, target
    img = ImageEnhance.Brightness(img).enhance(darken)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(0.85)

    vig = Image.new("L", (tw, th), 0)
    vd = ImageDraw.Draw(vig)
    max_r = int((tw ** 2 + th ** 2) ** 0.5 / 2)
    cx, cy = tw // 2, th // 2
    for i in range(40):
        a = int(140 * (i / 40))
        vd.ellipse(
            [cx - max_r + i * 4, cy - max_r + i * 4,
             cx + max_r - i * 4, cy + max_r - i * 4],
            fill=255 - a,
        )
    vig = vig.filter(ImageFilter.GaussianBlur(80))
    black = Image.new("RGB", (tw, th), (0, 0, 0))
    img = Image.composite(img, black, vig)

    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    text = name.upper().strip()
    base_size = int(tw * 0.26)
    font = _get_font(base_size)
    size = base_size
    tmp = Image.new("RGB", (10, 10))
    td = ImageDraw.Draw(tmp)
    while size > 50:
        bbox = td.textbbox((0, 0), text, font=font, stroke_width=10)
        w = bbox[2] - bbox[0]
        if w < tw - 100:
            break
        size -= 8
        font = _get_font(size)

    x, y, tw_, th_ = _center_position(draw, text, font, tw, th, sw=10)

    style_name, style_fn = random.choice(STYLES)
    logger.info(f"Style: {style_name}, size: {size}")

    try:
        if style_name == "bloody_red":
            style_fn(draw, text, font, x, y, tw_, th_)
        else:
            style_fn(draw, text, font, x, y)
    except Exception as e:
        logger.warning(f"Style fail: {e}")
        draw.text((x, y), text, font=font, fill=(255, 255, 255),
                  stroke_width=8, stroke_fill=(200, 10, 10))

    try:
        wm_font = _get_font(30)
        wm_text = "⚡ ARYA ⚡"
        wb = draw.textbbox((0, 0), wm_text, font=wm_font)
        wm_w = wb[2] - wb[0]
        draw.text(
            (tw - wm_w - 25, th - 55),
            wm_text, font=wm_font,
            fill=(255, 255, 255, 220),
            stroke_width=2, stroke_fill=(0, 0, 0),
        )
    except Exception:
        pass

    img = img.convert("RGB")
    img.save(output_path, "JPEG", quality=95)
    return output_path


# ═══════════════════════════════════════════════════════
# STATIC STICKER
# ═══════════════════════════════════════════════════════

def _sticker_pe_naam_likho(sticker_bytes, naam):
    img = Image.open(io.BytesIO(sticker_bytes)).convert("RGBA")
    W, H = img.size
    TARGET = 512
    if W >= H:
        nw, nh = TARGET, max(1, int(H * TARGET / W))
    else:
        nh, nw = TARGET, max(1, int(W * TARGET / H))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (TARGET, TARGET), (0, 0, 0, 0))
    canvas.paste(img, ((TARGET - nw) // 2, (TARGET - nh) // 2), img)
    draw = ImageDraw.Draw(canvas, "RGBA")
    text = naam.upper().strip()
    size = int(TARGET * 0.16)
    font = _get_font(size)
    tmp = Image.new("RGBA", (10, 10))
    td = ImageDraw.Draw(tmp)
    while size > 18:
        bb = td.textbbox((0, 0), text, font=font, stroke_width=6)
        if (bb[2] - bb[0]) < TARGET - 30:
            break
        size -= 4
        font = _get_font(size)
    bb = draw.textbbox((0, 0), text, font=font, stroke_width=6)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (TARGET - tw) // 2 - bb[0]
    y = TARGET - th - 25 - bb[1]
    draw.text((x + 3, y + 3), text, font=font,
              fill=(0, 0, 0, 180),
              stroke_width=6, stroke_fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font,
              fill=(255, 255, 255, 255),
              stroke_width=6, stroke_fill=(200, 10, 10, 255))
    out = io.BytesIO()
    canvas.save(out, "WEBP", quality=95, method=6)
    out.seek(0)
    return out


# ═══════════════════════════════════════════════════════
# ANIMATED STICKER
# ═══════════════════════════════════════════════════════

def _has_ffmpeg():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


HAS_FFMPEG = _has_ffmpeg()


def _process_video_sticker_webm(webm_bytes, naam):
    if not HAS_FFMPEG:
        raise Exception("ffmpeg install nahi hai.")
    font_path = _find_font_path()
    if not font_path:
        raise Exception("Font nahi mila")
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "in.webm")
        out_path = os.path.join(tmpdir, "out.webm")
        text_file = os.path.join(tmpdir, "text.txt")
        with open(in_path, "wb") as f:
            f.write(webm_bytes)
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(naam.upper())
        fp = font_path.replace("'", "'\\''")
        vf = (
            f"drawtext=fontfile='{fp}':textfile='{text_file}':"
            f"fontcolor=white:fontsize=44:"
            f"borderw=4:bordercolor=red:"
            f"x=(w-text_w)/2:y=h-text_h-20"
        )
        cmd = [
            "ffmpeg", "-y", "-i", in_path, "-vf", vf,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-b:v", "250k", "-crf", "38", "-an", "-t", "3",
            out_path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        if r.returncode != 0:
            raise Exception(f"ffmpeg fail: {r.stderr.decode(errors='ignore')[-200:]}")
        with open(out_path, "rb") as f:
            data = f.read()
        if len(data) > 500 * 1024:
            raise Exception(f"Output bada ({len(data)//1024}KB)")
        return io.BytesIO(data)


def _process_tgs_sticker(tgs_bytes, naam):
    if not HAS_RLOTTIE:
        raise Exception("pip install rlottie-python")
    if not HAS_FFMPEG:
        raise Exception("ffmpeg install nahi hai")
    json_data = gzip.decompress(tgs_bytes).decode("utf-8")
    anim = LottieAnimation.from_data(json_data)
    total = anim.lottie_animation_get_totalframe()
    fps = anim.lottie_animation_get_framerate()
    if fps <= 0:
        fps = 30
    fps = int(round(fps))
    if total > 180:
        total = 180
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(total):
            pil = anim.render_pillow_frame(frame_num=i).convert("RGBA")
            w, h = pil.size
            if w != 512 or h != 512:
                target = 512
                if w >= h:
                    nw, nh = target, max(1, int(h * target / w))
                else:
                    nh, nw = target, max(1, int(w * target / h))
                pil = pil.resize((nw, nh), Image.LANCZOS)
                canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
                canvas.paste(pil, ((target - nw) // 2, (target - nh) // 2), pil)
                pil = canvas
            draw = ImageDraw.Draw(pil, "RGBA")
            text = naam.upper().strip()
            size = int(512 * 0.16)
            font = _get_font(size)
            tmp = Image.new("RGBA", (10, 10))
            td = ImageDraw.Draw(tmp)
            while size > 14:
                bb = td.textbbox((0, 0), text, font=font, stroke_width=6)
                if (bb[2] - bb[0]) < 512 - 30:
                    break
                size -= 4
                font = _get_font(size)
            bb = draw.textbbox((0, 0), text, font=font, stroke_width=6)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            x = (512 - tw) // 2 - bb[0]
            y = 512 - th - 25 - bb[1]
            draw.text((x + 3, y + 3), text, font=font,
                      fill=(0, 0, 0, 180),
                      stroke_width=6, stroke_fill=(0, 0, 0, 180))
            draw.text((x, y), text, font=font,
                      fill=(255, 255, 255, 255),
                      stroke_width=6, stroke_fill=(200, 10, 10, 255))
            pil.save(os.path.join(tmpdir, f"f_{i:05d}.png"), "PNG")
        out_path = os.path.join(tmpdir, "out.webm")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "f_%05d.png"),
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-b:v", "250k", "-crf", "38", "-an", "-t", "3",
            out_path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            raise Exception(f"ffmpeg fail: {r.stderr.decode(errors='ignore')[-200:]}")
        with open(out_path, "rb") as f:
            data = f.read()
        if len(data) > 500 * 1024:
            raise Exception(f"Output bada ({len(data)//1024}KB)")
        return io.BytesIO(data)


# ═══════════════════════════════════════════════════════
# FUN CONTENT
# ═══════════════════════════════════════════════════════

ROASTS = [
    "Tera face dekh ke Google bhi bolta hai '404 Not Found' 😂",
    "Tu itna slow hai ki WiFi bhi tujhse faster hai 🐌",
    "Tere jaisa banda dekh ke mirror bhi sharma jata hai 🪞",
    "Tu wo hai jise dekh ke Alexa bhi 'Sorry, I don't know' bolti hai 🤖",
    "Teri personality Windows Vista jaisi hai — purani aur useless 💀",
    "Tu itna useless hai ki Google bhi tujhe search nahi karta 🔍",
    "Tere dimaag me ek bulb hai, par bijli nahi 💡",
    "Tu wo wifi hai jo connect hota hai par kaam nahi karta 📶",
    "Tera confidence dekh ke Google bhi 'Are you sure?' puchta hai ❓",
    "Tu itna patla hai ki shadow bhi bolti hai 'bhai khale kuch' 🍔",
]

SHAYARI = [
    "Dil ki baat labon pe na laao,\nJo tumhe chahe use jaanne do,\nMohabbat me koi jaldi nahi hoti,\nThoda waqt do, khud aa jayenge ❤️",
    "Zindagi ek kitaab hai,\nHar panne pe naya sabaq,\nPadhte raho, seekhte raho,\nKabhi rukna mat 📖",
    "Chand ko dekh ke tare jalte hain,\nTumhe dekh ke hum pagal hote hain 🌙",
    "Ishq me jo maza hai,\nWo kisi aur cheez me nahi,\nDil de do kisi ko,\nPar pehle soch lo 💭",
    "Raat ki khamoshi me,\nTeri yaad aati hai,\nDil kehta hai jaake mil,\nPar himmat nahi aati 💔",
]

FLIRT_SHAYARI = [
    "Teri smile dekh ke lagta hai,\nChand bhi sharma gaya hoga 🌙\nTu paas aaye to lage,\nSara jahan mil gaya hoga 💕",
    "Dil ne kaha dhadakna zaroori hai,\nTumse milna bhi zaroori hai,\nAgar tum na ho to kya hoga,\nTumhara hona hi to zaroori hai ❤️",
    "Tere aankhon mein doob jaana chahta hoon,\nTeri baahon mein kho jaana chahta hoon,\nZindagi bhar tere saath rehna hai,\nTujhe apna bana lena chahta hoon 💘",
    "Chand se puchha tum kahan rehti ho,\nChand ne kaha maine tumhe dekha hai,\nKisi ki aankhon mein basa hua hai,\nWahi to meri jaan ban gaya hai 🌹",
    "Teri ek jhalak se din ban jata hai,\nTera ek message se dil khil jata hai,\nKya karoon ye dil pagal hai,\nHar waqt teri hi fikar karta hai 🥰",
    "Tum ho to zindagi hasin lagti hai,\nTum ho to har pal khushi lagti hai,\nTumse milke laga jaise,\nPoori duniya mil gayi hai 💫",
    "Meri subah ki dua tum ho,\nMeri raat ki tamanna tum ho,\nMere dil ki dhadkan tum ho,\nMeri zindagi ka sapna tum ho ❤️",
    "Tujhe dekhta hoon to sukoon milta hai,\nTeri baatein sunke dil khilta hai,\nKaise bataun ye kya ho gaya hai,\nTere ishq mein sab kuch bhool gaya hai 😘",
    "Teri muskaan ka jaadu hai,\nMera dil bas tera hua hai,\nZamana chahe kuch bhi kahe,\nMujhe to sirf tujhse pyaar hua hai 💕",
    "Tere bina adhoora sa lagta hai,\nMera ye dil majboor sa lagta hai,\nTu saath ho to sab kuch hai,\nWarna ye jahan bhi door sa lagta hai 🥺",
]

JOKES = [
    "Teacher: Batao 2+2 kitna hota hai?\nStudent: Sir 4\nTeacher: Shabash! Ab 4+4?\nStudent: Sir 44 😂",
    "Wife: Mujhe surprise do!\nHusband: Tum aaj bhi sundar lag rahi ho 😂",
    "Banda: Doctor sahab, mujhe bhoolne ki bimari hai\nDoctor: Kab se?\nBanda: Kya kab se? 🤔",
    "Ek aadmi ne kaha: Main gym jaa raha hoon\n5 saal baad bhi... 'Kal se pakka' 💪",
    "Boss: Tum late kyun aaye?\nEmployee: Sir, traffic tha\nBoss: Har roz?\nEmployee: Haan sir, har roz traffic hota hai 🚗",
]

QUOTES = [
    "✨ 'Sapne wo nahi jo sote hue dekhte ho, sapne wo hain jo tumhe sone nahi dete' — Dr. APJ Abdul Kalam",
    "💪 'Kamyabi ka raaz hai — shuru karna aur laga rehna'",
    "🔥 'Grind karo, results khud bolenge'",
    "🌟 'Tum wo ho jo tum sochte ho' — Buddha",
    "📚 'Padho, jaago, aur tab tak na ruko jab tak lakshya na mile'",
]

TRUTHS = [
    "Tumne kabhi kisi ko secretly block kiya hai? 🤐",
    "Tumhari sabse embarrassing moment kya thi? 😳",
    "Tumne last kisi ko kab jhooth bola? 🤥",
    "Tumhara crush kaun hai? 💘",
    "Tumne kabhi kisi ki photo delete ki hai? 📱",
]

DARES = [
    "Apni photo bhej 10 sec me 📸",
    "5 log ko msg kar 'I love you' 💌",
    "Ek emoji use karke apni feeling bata 😊",
    "Apna phone wallpaper bhej 📱",
    "Voice note bhej kisi funny joke ka 🎤",
]

RR_DEFAULT_REPLIES = [
    "kya hua bhai? 😏",
    "bol na, sun raha hoon 👂",
    "phir se bol? 🤔",
    "hmm... 🤨",
    "kuch kaam tha? 😅",
    "batao batao 💬",
    "ji bolo? 🙃",
    "haan haan, bolo 🎤",
    "ooye, sun 👀",
    "kya scene hai? 🍿",
]


# ═══════════════════════════════════════════════════════
# WELCOME
# ═══════════════════════════════════════════════════════

async def on_bot_added(update, context):
    try:
        cmu = update.my_chat_member
        if not cmu:
            return
        chat = cmu.chat
        new_status = cmu.new_chat_member.status
        old_status = cmu.old_chat_member.status
        if chat.type not in ("group", "supergroup"):
            return

        KNOWN_CHATS.add(chat.id)
        await save_chats()

        if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
            logger.info(f"✅ Bot added: {chat.title} ({chat.id})")
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"⚡ **ARYA BOT ACTIVE** ⚡\n\n"
                        f"🎯 **{chat.title}**\n"
                        f"🔹 Prefix: `{COMMAND_PREFIX}`\n\n"
                        f"🎉 Ab tum group me bot use kar sakte ho!\n\n"
                        f"⚙️ **Recommended:** Bot ko **ADMIN** banao aur "
                        f"BotFather me **privacy OFF** karo.\n\n"
                        f"📋 Try karo: `.help` `.test` `.logo`"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Welcome fail: {e}")

        elif old_status == "member" and new_status == "administrator":
            logger.info(f"👑 Bot promoted: {chat.title}")
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="👑 **ADMIN MIL GAYA!**\n\nAb saare commands kaam karenge. Try: `.help`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"on_bot_added: {e}")


# ═══════════════════════════════════════════════════════
# BASIC COMMANDS
# ═══════════════════════════════════════════════════════

@dedup
async def test_cmd(update, context):
    await safe_reply(
        update.message,
        "✅ **BOT WORKING!**\n\n"
        f"Chat: `{update.effective_chat.id}`\n"
        f"Type: `{update.effective_chat.type}`\n"
        f"User: {update.effective_user.first_name}",
        parse_mode="Markdown",
    )


@dedup
async def start_cmd(update, context):
    await safe_reply(
        update.message,
        "⚡ **ARYA BOT ACTIVE** ⚡\n\n"
        f"`{COMMAND_PREFIX}help` - Saare commands dekho\n"
        "**ARYA TO BAAP H SABKA**",
        parse_mode="Markdown",
    )


@dedup
async def help_cmd(update, context):
    p = COMMAND_PREFIX
    user_id = update.effective_user.id
    is_owner_user = is_owner(user_id)

    help_text = f"""
╔══════════════════════════════╗
     ⚡ 𝐀𝐑𝐘𝐀 々 𓄋 ⚡
╚══════════════════════════════╝

🎬 {p}yt <search>              - Video download
🎵 {p}song <name>              - Audio download
🎨 {p}logo <name> boy <age>    - Boy DP
🎨 {p}logo <name> girl <age>   - Girl DP
🐾 {p}fem <search> | <name>    - Famous img
🎨 {p}custmstk <name>          - Sticker pe naam
👤 {p}info (reply)             - User Info
🔍 {p}aryainfo                 - Detailed Info
🏓 {p}ping                     - Ping
📊 {p}check                    - Admin status
🧪 {p}test                     - Test bot

━━━━━━━━━━━━━━━━━━━━━━━━━━
      😂 FUN COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 {p}roast @user              - Roast
🌹 {p}shayari                  - Shayari (reply=target)
😂 {p}joke                     - Joke (reply=target)
💡 {p}quote                    - Quote (reply=target)
💕 {p}qt                       - Flirt Shayari
💭 {p}truth                    - Truth
🎯 {p}dare                     - Dare
💘 {p}ship <n1> <n2>           - Love %
🪙 {p}coin                     - Coin flip
🎲 {p}dice                     - Dice roll
🎱 {p}8ball <question>         - 8 Ball
🎮 {p}rps <rock/paper/scissor> - RPS
🐱 {p}cat                      - Random cat
🐶 {p}dog                      - Random dog
💀 {p}wasted (reply photo)     - Wasted effect

━━━━━━━━━━━━━━━━━━━━━━━━━━
      🛡️ GROUP ADMIN COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔇 {p}mute (reply)             - User ko mute
🔊 {p}unmute (reply)           - Unmute
👑 {p}prompt (reply)           - Admin banao
🔒 {p}lock                     - Group lock
🔓 {p}unlock                   - Group unlock
"""

    if is_owner_user:
        help_text += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
      👑 OWNER ONLY
━━━━━━━━━━━━━━━━━━━━━━━━━━
🚫 {p}block (reply)            - Block user
✅ {p}unblock (reply)          - Unblock
📋 {p}blocklist                - Blocked list
🔔 {p}rr (reply)               - Auto-reply ON
🛑 {p}srr (reply)              - Auto-reply OFF
🧹 {p}srr all                  - Clear all RR
📊 {p}gc                       - Groups list
"""

    help_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n      𝐀𝐑𝐘𝐀⚡\n"
    await safe_reply(update.message, help_text)


@dedup
async def ping_cmd(update, context):
    start = time.time()
    msg = await safe_reply(update.message, "🏓 Pinging...")
    if not msg:
        return
    ms = int((time.time() - start) * 1000)
    await safe_edit(msg, f"🏓 Pong! {ms}ms")


@dedup
async def check_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "ℹ️ Group me use karo.")
    status_msg = await safe_reply(update.message, "🔍 Checking...")
    if not status_msg:
        return
    try:
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat.id, me.id)
        status = member.status
        if status == ChatMember.ADMINISTRATOR:
            text = (
                f"✅ **BOT IS ADMIN**\n\n"
                f"📛 Group: **{chat.title}**\n"
                f"🆔 ID: `{chat.id}`\n"
                f"👑 Status: ADMIN\n\n"
                f"✅ Saare commands kaam karenge!"
            )
        elif status == ChatMember.MEMBER:
            text = (
                f"⚠️ **BOT IS NOT ADMIN**\n\n"
                f"📛 Group: **{chat.title}**\n"
                f"🆔 ID: `{chat.id}`\n"
                f"👉 Bot ko **admin** banao taaki "
                f".mute .lock .prompt kaam kare."
            )
        else:
            text = f"⚠️ Bot status: {status}"
        await safe_edit(status_msg, text, parse_mode="Markdown")
    except Exception as e:
        await safe_edit(status_msg, f"❌ Error: {str(e)[:180]}")


@dedup
async def gc_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Owner only command!")
    if not KNOWN_CHATS:
        return await safe_reply(update.message, "📋 No groups yet")
    lines = [f"📋 **ARYA GROUPS ({len(KNOWN_CHATS)})**\n"]
    for cid in list(KNOWN_CHATS)[:50]:
        try:
            chat = await context.bot.get_chat(cid)
            lines.append(f"• **{chat.title}**\n  `{cid}`")
        except Exception:
            lines.append(f"• `{cid}`")
    await safe_reply(update.message, "\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════
# YT / SONG
# ═══════════════════════════════════════════════════════

@dedup
async def yt_cmd(update, context):
    if not context.args:
        return await safe_reply(update.message, f"❌ `{COMMAND_PREFIX}yt <name>`")
    query = " ".join(context.args)
    status = await safe_reply(update.message, f"🎬 Searching: `{query}`...")
    if not status:
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_name = None
    try:
        def _dl():
            with yt_dlp.YoutubeDL(get_base_ydl_opts({
                "format": "best[ext=mp4][height<=720]/best[ext=mp4]/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            })) as ydl:
                return ydl.extract_info(f"ytsearch1:{query}", download=True)
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _dl)
        if not info or not info.get("entries"):
            return await safe_edit(status, "❌ Not found!")
        v = info["entries"][0]
        title = v.get("title", "Video")
        vid = v.get("id", "video")
        dur = v.get("duration", 0)
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(str(vid)):
                file_name = os.path.join(DOWNLOAD_DIR, f)
                break
        if not file_name or not os.path.exists(file_name):
            return await safe_edit(status, "❌ Download fail")
        size_mb = os.path.getsize(file_name) / (1024 * 1024)
        if size_mb > 50:
            return await safe_edit(status, f"❌ Too large ({size_mb:.1f}MB)")
        with open(file_name, "rb") as vid_f:
            await update.message.reply_video(
                video=vid_f,
                caption=f"🎬 **{title}**\n👤 {update.effective_user.first_name}",
                parse_mode="Markdown", supports_streaming=True,
                duration=int(dur) if dur else 0,
            )
        await safe_delete(status)
    except Exception as e:
        logger.error(f"YT: {e}")
        await safe_edit(status, f"⚠️ {str(e)[:180]}")
    finally:
        if file_name and os.path.exists(file_name):
            try:
                os.remove(file_name)
            except Exception:
                pass


@dedup
async def song_cmd(update, context):
    if not context.args:
        return await safe_reply(update.message, f"❌ `{COMMAND_PREFIX}song <name>`")
    query = " ".join(context.args)
    status = await safe_reply(update.message, f"🔎 Searching: `{query}`...")
    if not status:
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_name = None
    try:
        def _dl():
            with yt_dlp.YoutubeDL(get_base_ydl_opts({
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            })) as ydl:
                return ydl.extract_info(f"ytsearch1:{query}", download=True)
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _dl)
        if not info or not info.get("entries"):
            return await safe_edit(status, "❌ Not found!")
        v = info["entries"][0]
        title = v.get("title", "Audio")
        vid = v.get("id", "audio")
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(str(vid)):
                file_name = os.path.join(DOWNLOAD_DIR, f)
                break
        if not file_name or not os.path.exists(file_name):
            return await safe_edit(status, "❌ Fail")
        with open(file_name, "rb") as audio:
            await update.message.reply_audio(
                audio=audio, title=title,
                caption=f"🎵 **{title}**\n👤 {update.effective_user.first_name}",
                parse_mode="Markdown",
            )
        await safe_delete(status)
    except Exception as e:
        logger.error(f"Song: {e}")
        await safe_edit(status, f"⚠️ {str(e)[:180]}")
    finally:
        if file_name and os.path.exists(file_name):
            try:
                os.remove(file_name)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# LOGO
# ═══════════════════════════════════════════════════════

@dedup
async def logo_cmd(update, context):
    if not context.args:
        return await safe_reply(
            update.message,
            f"❌ `{COMMAND_PREFIX}logo <name> boy <age>`\n"
            f"`{COMMAND_PREFIX}logo <name> girl <age>`",
        )
    args = list(context.args)
    gender = "boy"
    age = 0
    if args and args[-1].isdigit():
        try:
            a = int(args[-1])
            if 1 <= a <= 120:
                age = a
                args = args[:-1]
        except Exception:
            pass
    if args and args[-1].lower() in ("boy", "girl", "b", "g", "male", "female", "m", "f"):
        last = args[-1].lower()
        gender = "boy" if last in ("boy", "b", "male", "m") else "girl"
        args = args[:-1]
    name = " ".join(args).strip()
    if not name:
        return await safe_reply(update.message, "❌ Name missing!")
    age_text = f" {age}" if age else ""
    status = await safe_reply(
        update.message,
        f"🎨 **ARYA LOGO**\n📥 {gender}{age_text} fetch...\n✍️ `{name}` likh raha...",
    )
    if not status:
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(DOWNLOAD_DIR, f"logo_{int(time.time())}.jpg")
    try:
        loop = asyncio.get_event_loop()
        await safe_edit(status, f"🔍 {gender.title()}{age_text} search...")
        url, data = await loop.run_in_executor(None, fetch_random_image, gender, age)
        logger.info(f"Img: {url[:80]} ({len(data)}b)")
        await safe_edit(status, f"✍️ `{name}` likh raha...")
        await loop.run_in_executor(None, create_logo, data, name, out_path, 0.65)
        await safe_edit(status, "📤 Uploading...")
        with open(out_path, "rb") as photo:
            caption = f"⚡ **ARYA LOGO** ⚡\n\n🔮 **Name:** `{name}`\n🎭 **Gender:** {gender.title()}\n"
            if age:
                caption += f"🎂 **Age:** {age}\n"
            caption += f"👤 **By:** {update.effective_user.first_name}"
            await update.message.reply_photo(
                photo=photo, caption=caption, parse_mode="Markdown",
            )
        await safe_delete(status)
    except Exception as e:
        logger.error(f"Logo: {e}")
        await safe_edit(status, f"⚠️ **Error** `{str(e)[:180]}`")
    finally:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# FEM
# ═══════════════════════════════════════════════════════

@dedup
async def fem_cmd(update, context):
    if not context.args:
        return await safe_reply(
            update.message,
            f"❌ `{COMMAND_PREFIX}fem <search>`\n"
            f"`{COMMAND_PREFIX}fem <search> | <name>`",
        )
    full = " ".join(context.args)
    if "|" in full:
        parts = full.split("|", 1)
        search_term = parts[0].strip()
        write_name = parts[1].strip()
    else:
        search_term = full.strip()
        write_name = search_term
    if not search_term:
        return await safe_reply(update.message, "❌ Search term missing!")
    if not write_name:
        write_name = search_term
    status = await safe_reply(
        update.message,
        f"🐾 **ARYA FAMOUS**\n🔍 Search: `{search_term}`\n✍️ Write: `{write_name}`",
    )
    if not status:
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(DOWNLOAD_DIR, f"fem_{int(time.time())}.jpg")
    try:
        loop = asyncio.get_event_loop()
        await safe_edit(status, f"🔍 '{search_term}' search...")
        url, data = await loop.run_in_executor(None, fetch_famous_image, search_term)
        logger.info(f"Fem img: {url[:80]} ({len(data)}b)")
        await safe_edit(status, f"✍️ `{write_name.upper()}` likh raha...")
        await loop.run_in_executor(None, create_logo, data, write_name, out_path, 0.60)
        await safe_edit(status, "📤 Uploading...")
        with open(out_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=(
                    f"🐾 **ARYA FAMOUS** 🐾\n\n"
                    f"🔍 **Search:** `{search_term.title()}`\n"
                    f"✍️ **Written:** `{write_name.title()}`\n"
                    f"👤 **By:** {update.effective_user.first_name}"
                ),
                parse_mode="Markdown",
            )
        await safe_delete(status)
    except Exception as e:
        logger.error(f"Fem: {e}")
        await safe_edit(status, f"⚠️ **Error** `{str(e)[:180]}`")
    finally:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# CUSTMSTK
# ═══════════════════════════════════════════════════════

@dedup
async def custmstk_cmd(update, context):
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.sticker:
        return await safe_reply(
            msg,
            f"❌ **Kaise use kare:**\n\n"
            f"1️⃣ Koi sticker bhejo\n"
            f"2️⃣ Us **sticker pe reply** karo\n"
            f"3️⃣ `{COMMAND_PREFIX}custmstk <naam>` likho\n\n"
            f"Example: `{COMMAND_PREFIX}custmstk ARYA`",
            parse_mode="Markdown",
        )
    if not context.args:
        return await safe_reply(
            msg,
            f"❌ Naam missing! `{COMMAND_PREFIX}custmstk <naam>`",
        )
    naam = " ".join(context.args).strip()[:40]
    sticker = msg.reply_to_message.sticker
    is_animated = sticker.is_animated
    is_video = sticker.is_video

    if is_animated or is_video:
        kind = "video (.webm)" if is_video else "Lottie (.tgs)"
        status = await safe_reply(
            msg,
            f"🎨 **Animated sticker** ({kind})\n`{naam}` likh raha...\n⏳ 10-40 sec",
            parse_mode="Markdown",
        )
        if not status:
            return
        try:
            f = await context.bot.get_file(sticker.file_id)
            data = await f.download_as_bytearray()
            loop = asyncio.get_event_loop()
            if is_video:
                out = await loop.run_in_executor(
                    None, _process_video_sticker_webm, bytes(data), naam
                )
            else:
                out = await loop.run_in_executor(
                    None, _process_tgs_sticker, bytes(data), naam
                )
            await safe_edit(status, "📤 Sending...")
            await msg.reply_sticker(sticker=out)
            await safe_delete(status)
        except Exception as e:
            logger.error(f"custmstk anim: {e}")
            await safe_edit(status, f"❌ **Error** `{str(e)[:250]}`", parse_mode="Markdown")
        return

    status = await safe_reply(msg, f"🎨 `{naam}` likh raha hoon sticker pe...")
    if not status:
        return
    try:
        f = await context.bot.get_file(sticker.file_id)
        data = await f.download_as_bytearray()
        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(
            None, _sticker_pe_naam_likho, bytes(data), naam
        )
        await safe_edit(status, "📤 Sending...")
        await msg.reply_sticker(sticker=out)
        await safe_delete(status)
    except Exception as e:
        logger.error(f"custmstk error: {e}")
        await safe_edit(status, f"❌ Error: `{str(e)[:150]}`", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════
# FUN COMMANDS
# ═══════════════════════════════════════════════════════

@dedup
async def roast_cmd(update, context):
    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user.first_name
    elif context.args:
        target = " ".join(context.args)
    else:
        target = update.effective_user.first_name
    await safe_reply(
        update.message, f"🔥 **{target}**\n\n{random.choice(ROASTS)}",
        parse_mode="Markdown",
    )


@dedup
async def shayari_cmd(update, context):
    target = _get_target_name(update)
    shayari = random.choice(SHAYARI)
    if target:
        header = f"🌹 **Shayari for {target}** 🌹"
        footer = f"\n\n— **{update.effective_user.first_name}** ki taraf se 💌"
    else:
        header = "🌹 **Shayari** 🌹"
        footer = f"\n\n— **{update.effective_user.first_name}**"
    await safe_reply(update.message, f"{header}\n\n{shayari}{footer}", parse_mode="Markdown")


@dedup
async def joke_cmd(update, context):
    target = _get_target_name(update)
    joke = random.choice(JOKES)
    if target:
        header = f"😂 **Joke for {target}** 😂"
        footer = f"\n\n— **{update.effective_user.first_name}** ki taraf se"
    else:
        header = "😂 **Joke** 😂"
        footer = f"\n\n— **{update.effective_user.first_name}**"
    await safe_reply(update.message, f"{header}\n\n{joke}{footer}", parse_mode="Markdown")


@dedup
async def quote_cmd(update, context):
    target = _get_target_name(update)
    q = random.choice(QUOTES)
    if target:
        header = f"💡 **Quote for {target}** 💡"
        footer = f"\n\n— **{update.effective_user.first_name}** ki taraf se"
    else:
        header = "💡 **Quote** 💡"
        footer = f"\n\n— **{update.effective_user.first_name}**"
    await safe_reply(update.message, f"{header}\n\n{q}{footer}", parse_mode="Markdown")


@dedup
async def qt_cmd(update, context):
    target = _get_target_name(update)
    shayari = random.choice(FLIRT_SHAYARI)
    if target:
        header = f"💕 **Flirt Shayari for {target}** 💕"
        footer = f"\n\n— **{update.effective_user.first_name}** ki taraf se 😘"
    else:
        header = "💕 **Flirt Shayari** 💕"
        footer = f"\n\n— **{update.effective_user.first_name}**"
    await safe_reply(update.message, f"{header}\n\n{shayari}{footer}", parse_mode="Markdown")


@dedup
async def truth_cmd(update, context):
    await safe_reply(update.message, f"💭 **TRUTH**\n\n{random.choice(TRUTHS)}", parse_mode="Markdown")


@dedup
async def dare_cmd(update, context):
    await safe_reply(update.message, f"🎯 **DARE**\n\n{random.choice(DARES)}", parse_mode="Markdown")


@dedup
async def ship_cmd(update, context):
    names = []
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        names.append(update.effective_user.first_name)
        names.append(update.message.reply_to_message.from_user.first_name)
    elif len(context.args) >= 2:
        names = context.args[:2]
    else:
        return await safe_reply(
            update.message,
            f"❌ `{COMMAND_PREFIX}ship <n1> <n2>` ya reply karo",
        )
    seed = sum(ord(c) for c in "".join(names).lower())
    percent = (seed * 7) % 101
    bar = "❤️" * (percent // 10) + "🖤" * (10 - percent // 10)
    if percent >= 90:
        msg = "🔥 PERFECT MATCH! Shaadi pakki 💍"
    elif percent >= 70:
        msg = "😍 Bahut acha jodi hai!"
    elif percent >= 50:
        msg = "🙂 Theek hai, try karo"
    elif percent >= 30:
        msg = "😐 Kuch zyada hope mat rakho"
    else:
        msg = "💔 Bhai bhool jao, match nahi hai"
    await safe_reply(
        update.message,
        f"💘 **LOVE CALCULATOR** 💘\n\n"
        f"👤 {names[0]}\n👤 {names[1]}\n\n"
        f"💗 **Love:** `{percent}%`\n{bar}\n\n{msg}",
        parse_mode="Markdown",
    )


@dedup
async def coin_cmd(update, context):
    result = random.choice(["🪙 HEADS", "🪙 TAILS"])
    await safe_reply(update.message, f"**Coin Flip:** {result}", parse_mode="Markdown")


@dedup
async def dice_cmd(update, context):
    try:
        n = int(context.args[0]) if context.args else 6
        n = max(2, min(n, 1000))
    except Exception:
        n = 6
    await safe_reply(
        update.message,
        f"🎲 You rolled: **{random.randint(1, n)}** (1-{n})",
        parse_mode="Markdown",
    )


@dedup
async def eightball_cmd(update, context):
    if not context.args:
        return await safe_reply(update.message, f"❌ `{COMMAND_PREFIX}8ball <q>`")
    answers = [
        "✅ Bilkul haan!", "❌ Nahi bhai, bhool ja", "🤔 Shayad",
        "💯 Pakka hoga", "🚫 Kabhi nahi", "🎯 Try kar, ho jayega",
        "😏 Puchhne ki zaroorat nahi", "🌧️ Abhi nahi, baad me",
        "🔥 Haan but mehnat kar", "🤷‍♂️ Kaun jaane?",
    ]
    await safe_reply(
        update.message,
        f"🎱 **Q:** {' '.join(context.args)}\n\n**A:** {random.choice(answers)}",
        parse_mode="Markdown",
    )


@dedup
async def rps_cmd(update, context):
    if not context.args or context.args[0].lower() not in ("rock", "paper", "scissor", "scissors"):
        return await safe_reply(update.message, f"❌ `{COMMAND_PREFIX}rps rock/paper/scissor`")
    user = context.args[0].lower().replace("scissors", "scissor")
    bot = random.choice(["rock", "paper", "scissor"])
    emoji = {"rock": "🪨", "paper": "📄", "scissor": "✂️"}
    if user == bot:
        res = "🤝 TIE!"
    elif (user == "rock" and bot == "scissor") or \
         (user == "paper" and bot == "rock") or \
         (user == "scissor" and bot == "paper"):
        res = "🎉 TUM JEETE!"
    else:
        res = "😎 BOT JEETA!"
    await safe_reply(
        update.message,
        f"🎮 **RPS**\n\n👤 {emoji[user]} {user.title()}\n🤖 {emoji[bot]} {bot.title()}\n\n**{res}**",
        parse_mode="Markdown",
    )


@dedup
async def cat_cmd(update, context):
    try:
        req = urllib.request.Request(
            "https://api.thecatapi.com/v1/images/search", headers=HEADERS
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        await update.message.reply_photo(data[0]["url"], caption="🐱 Meow!")
    except Exception as e:
        await safe_reply(update.message, f"❌ Cat fail: {str(e)[:100]}")


@dedup
async def dog_cmd(update, context):
    try:
        req = urllib.request.Request(
            "https://dog.ceo/api/breeds/image/random", headers=HEADERS
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        await update.message.reply_photo(data["message"], caption="🐶 Woof!")
    except Exception as e:
        await safe_reply(update.message, f"❌ Dog fail: {str(e)[:100]}")


def apply_wasted_effect(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    W, H = img.size
    img = ImageEnhance.Color(img).enhance(0.3)
    img = ImageEnhance.Brightness(img).enhance(0.7)
    draw = ImageDraw.Draw(img, "RGBA")
    font = _get_font(int(W * 0.18))
    text = "WASTED"
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=6)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2 - bbox[0]
    y = (H - th) // 2 - bbox[1]
    draw.text((x + 5, y + 5), text, font=font, fill=(0, 0, 0, 220))
    draw.text((x, y), text, font=font, fill=(255, 30, 30, 255),
              stroke_width=6, stroke_fill=(0, 0, 0))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=92)
    out.seek(0)
    return out


@dedup
async def wasted_cmd(update, context):
    file_id = None
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        file_id = update.message.reply_to_message.photo[-1].file_id
    else:
        try:
            photos = await context.bot.get_user_profile_photos(
                update.effective_user.id, limit=1
            )
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
        except Exception:
            pass
    if not file_id:
        return await safe_reply(
            update.message,
            "❌ Photo pe reply karo ya profile pic set karo!",
        )
    status = await safe_reply(update.message, "💀 Wasting...")
    try:
        f = await context.bot.get_file(file_id)
        data = await f.download_as_bytearray()
        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, apply_wasted_effect, bytes(data))
        await update.message.reply_photo(out, caption="💀 **WASTED**", parse_mode="Markdown")
        await safe_delete(status)
    except Exception as e:
        await safe_edit(status, f"❌ {str(e)[:180]}")


# ═══════════════════════════════════════════════════════
# OWNER ONLY — BLOCK / UNBLOCK / BLOCKLIST
# ═══════════════════════════════════════════════════════

@dedup
async def block_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Ye command sirf **Owner** use kar sakta hai!")
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Reply karke `{COMMAND_PREFIX}block` bhejo.",
            parse_mode="Markdown",
        )
    target = update.message.reply_to_message.from_user
    if target.id == OWNER_ID:
        return await safe_reply(update.message, "😂 Khud ko block nahi kar sakte!")
    BLOCKED_USERS.add(target.id)
    await save_blocked()
    await safe_reply(
        update.message,
        f"🚫 **BLOCKED:** {target.first_name} (`{target.id}`)",
        parse_mode="Markdown",
    )


@dedup
async def unblock_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Ye command sirf **Owner** use kar sakta hai!")
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Reply karke `{COMMAND_PREFIX}unblock` bhejo.",
            parse_mode="Markdown",
        )
    target = update.message.reply_to_message.from_user
    if target.id in BLOCKED_USERS:
        BLOCKED_USERS.discard(target.id)
        await save_blocked()
        await safe_reply(
            update.message,
            f"✅ **UNBLOCKED:** {target.first_name} (`{target.id}`)",
            parse_mode="Markdown",
        )
    else:
        await safe_reply(
            update.message,
            f"ℹ️ **{target.first_name}** blocked list me nahi.",
            parse_mode="Markdown",
        )


@dedup
async def blocklist_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Ye command sirf **Owner** use kar sakta hai!")
    if not BLOCKED_USERS:
        return await safe_reply(update.message, "📋 Blocked list khaali hai.")
    lines = [f"🚫 **BLOCKED USERS ({len(BLOCKED_USERS)})**\n"]
    for uid in list(BLOCKED_USERS)[:50]:
        try:
            u = await context.bot.get_chat(uid)
            lines.append(f"• {u.first_name} — `{uid}`")
        except Exception:
            lines.append(f"• `{uid}`")
    await safe_reply(update.message, "\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════
# OWNER ONLY — RR / SRR
# ═══════════════════════════════════════════════════════

@dedup
async def rr_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Ye command sirf **Owner** use kar sakta hai!")

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Kisi ke message pe **reply** karke `{COMMAND_PREFIX}rr` bhejo.\n\n"
            f"Optional: `{COMMAND_PREFIX}rr <custom message>`",
            parse_mode="Markdown",
        )

    target = update.message.reply_to_message.from_user

    if target.id == OWNER_ID:
        return await safe_reply(update.message, "😂 Khud ko RR nahi kar sakte!")
    if target.is_bot:
        return await safe_reply(update.message, "❌ Bot ko RR nahi kar sakte!")

    custom = " ".join(context.args).strip() if context.args else ""

    RR_USERS[str(target.id)] = {
        "name": target.first_name or "User",
        "username": target.username or "",
        "custom": custom,
    }
    await save_rr()

    mention = f"@{target.username}" if target.username else target.first_name
    extra = f"\n💬 **Custom:** `{custom}`" if custom else "\n💬 **Reply:** Random fun message"

    await safe_reply(
        update.message,
        f"🔔 **RR STARTED** 🔔\n\n"
        f"👤 Target: {mention} (`{target.id}`)\n"
        f"{extra}\n\n"
        f"✅ Ab ye user jab bhi message bhejega, bot reply karega.\n\n"
        f"🛑 Rokne ke liye: uske kisi message pe reply karke `{COMMAND_PREFIX}srr`",
        parse_mode="Markdown",
    )


@dedup
async def srr_cmd(update, context):
    if not is_owner(update.effective_user.id):
        return await safe_reply(update.message, "❌ Ye command sirf **Owner** use kar sakta hai!")

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
        uid = str(target.id)
        if uid in RR_USERS:
            del RR_USERS[uid]
            await save_rr()
            mention = f"@{target.username}" if target.username else target.first_name
            return await safe_reply(
                update.message,
                f"🛑 **RR STOPPED**\n\n👤 {mention} (`{target.id}`) ka auto-reply band.",
                parse_mode="Markdown",
            )
        else:
            return await safe_reply(
                update.message,
                f"ℹ️ Ye user RR list me nahi hai.",
            )

    if context.args and context.args[0].lower() in ("all", "clear"):
        count = len(RR_USERS)
        RR_USERS.clear()
        await save_rr()
        return await safe_reply(
            update.message,
            f"🛑 **RR CLEARED** — {count} user(s) removed.",
        )

    if not RR_USERS:
        return await safe_reply(update.message, "📋 RR list khaali hai.")

    lines = [f"🔔 **RR LIST ({len(RR_USERS)})**\n"]
    for uid, info in RR_USERS.items():
        name = info.get("name", "User")
        un = info.get("username", "")
        mention = f"@{un}" if un else name
        custom = info.get("custom", "")
        extra = f" — `{custom}`" if custom else ""
        lines.append(f"• {mention} (`{uid}`){extra}")
    lines.append(f"\n🛑 Stop (reply): `{COMMAND_PREFIX}srr`")
    lines.append(f"🧹 Clear all: `{COMMAND_PREFIX}srr all`")
    await safe_reply(update.message, "\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════
# GROUP ADMIN — MUTE / UNMUTE / PROMPT / LOCK / UNLOCK
# ═══════════════════════════════════════════════════════

@dedup
async def mute_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "❌ Group me use karo.")

    if not await is_group_admin(chat.id, update.effective_user.id, context):
        return await safe_reply(
            update.message,
            "❌ Ye command sirf **Group Admin** ya **Owner** use kar sakta hai!",
            parse_mode="Markdown",
        )

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Kisi ke message pe **reply** karke `{COMMAND_PREFIX}mute` bhejo.",
            parse_mode="Markdown",
        )

    target = update.message.reply_to_message.from_user

    if target.id == OWNER_ID:
        return await safe_reply(update.message, "😂 Owner ko mute nahi kar sakte!")
    if target.id == context.bot.id:
        return await safe_reply(update.message, "❌ Khud ko mute nahi kar sakta!")

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            ),
        )
        mention = f"@{target.username}" if target.username else target.first_name
        await safe_reply(
            update.message,
            f"🔇 **MUTED:** {mention} (`{target.id}`)\n\n"
            f"Ab ye group me message nahi bhej sakta.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await safe_reply(
            update.message,
            f"❌ Mute fail: `{str(e)[:150]}`\n\n"
            f"Bot ko **admin** banao + **Restrict Members** permission do.",
            parse_mode="Markdown",
        )


@dedup
async def unmute_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "❌ Group me use karo.")

    if not await is_group_admin(chat.id, update.effective_user.id, context):
        return await safe_reply(
            update.message,
            "❌ Ye command sirf **Group Admin** ya **Owner** use kar sakta hai!",
            parse_mode="Markdown",
        )

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Kisi ke message pe **reply** karke `{COMMAND_PREFIX}unmute` bhejo.",
            parse_mode="Markdown",
        )

    target = update.message.reply_to_message.from_user

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        mention = f"@{target.username}" if target.username else target.first_name
        await safe_reply(
            update.message,
            f"🔊 **UNMUTED:** {mention} (`{target.id}`)\n\n"
            f"Ab ye normal message bhej sakta hai.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await safe_reply(
            update.message,
            f"❌ Unmute fail: `{str(e)[:150]}`",
            parse_mode="Markdown",
        )


@dedup
async def prompt_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "❌ Group me use karo.")

    if not await is_group_admin(chat.id, update.effective_user.id, context):
        return await safe_reply(
            update.message,
            "❌ Ye command sirf **Group Admin** ya **Owner** use kar sakta hai!",
            parse_mode="Markdown",
        )

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        return await safe_reply(
            update.message,
            f"❌ Kisi ke message pe **reply** karke `{COMMAND_PREFIX}prompt` bhejo.",
            parse_mode="Markdown",
        )

    target = update.message.reply_to_message.from_user

    if target.is_bot:
        return await safe_reply(update.message, "❌ Bot ko admin nahi bana sakte!")
    if target.id == context.bot.id:
        return await safe_reply(update.message, "😂 Main to already admin hoon!")

    try:
        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            can_change_info=False,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False,
            can_manage_video_chats=True,
            can_manage_chat=True,
            is_anonymous=False,
        )
        mention = f"@{target.username}" if target.username else target.first_name
        await safe_reply(
            update.message,
            f"👑 **PROMOTED:** {mention} (`{target.id}`)\n\n"
            f"Ab ye group ka **admin** hai.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await safe_reply(
            update.message,
            f"❌ Promote fail: `{str(e)[:150]}`\n\n"
            f"Bot ko **Add New Admins** permission do.",
            parse_mode="Markdown",
        )


@dedup
async def lock_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "❌ Group me use karo.")

    if not await is_group_admin(chat.id, update.effective_user.id, context):
        return await safe_reply(
            update.message,
            "❌ Ye command sirf **Group Admin** ya **Owner** use kar sakta hai!",
            parse_mode="Markdown",
        )

    if chat.id in LOCKED_CHATS:
        return await safe_reply(update.message, "🔒 Group pehle se locked hai!")

    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            ),
        )
        LOCKED_CHATS.add(chat.id)
        await save_locked()

        await safe_reply(
            update.message,
            f"🔒 **GROUP LOCKED** 🔒\n\n"
            f"📛 Group: **{chat.title}**\n\n"
            f"✅ Ab sirf **Owner** aur **Admins** message bhej sakte hain.\n"
            f"🔓 Unlock: `{COMMAND_PREFIX}unlock`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await safe_reply(
            update.message,
            f"❌ Lock fail: `{str(e)[:150]}`\n\n"
            f"Bot ko **Restrict Members** permission do.",
            parse_mode="Markdown",
        )


@dedup
async def unlock_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await safe_reply(update.message, "❌ Group me use karo.")

    if not await is_group_admin(chat.id, update.effective_user.id, context):
        return await safe_reply(
            update.message,
            "❌ Ye command sirf **Group Admin** ya **Owner** use kar sakta hai!",
            parse_mode="Markdown",
        )

    if chat.id not in LOCKED_CHATS:
        return await safe_reply(update.message, "🔓 Group pehle se unlocked hai!")

    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        LOCKED_CHATS.discard(chat.id)
        await save_locked()

        await safe_reply(
            update.message,
            f"🔓 **GROUP UNLOCKED** 🔓\n\n"
            f"📛 Group: **{chat.title}**\n\n"
            f"✅ Ab sabhi members message bhej sakte hain.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await safe_reply(
            update.message,
            f"❌ Unlock fail: `{str(e)[:150]}`",
            parse_mode="Markdown",
        )


# ═══════════════════════════════════════════════════════
# INFO COMMANDS
# ═══════════════════════════════════════════════════════

@dedup
async def info_cmd(update, context):
    msg = update.message
    user = (msg.reply_to_message.from_user
            if msg.reply_to_message and msg.reply_to_message.from_user
            else update.effective_user)
    await safe_reply(
        msg,
        f"👤 **USER INFO**\n\n"
        f"**Name:** {user.first_name or 'N/A'}\n"
        f"**Username:** @{user.username or 'N/A'}\n"
        f"**User ID:** `{user.id}`\n"
        f"**Is Bot:** {user.is_bot}",
        parse_mode="Markdown",
    )


@dedup
async def aryainfo_cmd(update, context):
    t_user = None
    t_uname = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        t_user = update.message.reply_to_message.from_user
    elif context.args:
        t_uname = context.args[0].replace("@", "").strip()
    else:
        return await safe_reply(
            update.message,
            f"❌ `{COMMAND_PREFIX}aryainfo` (reply) ya @user",
        )
    status = await safe_reply(update.message, "🔍 Fetching...")
    if not status:
        return
    try:
        if t_uname and not t_user:
            try:
                t_user = await context.bot.get_chat(f"@{t_uname}")
            except Exception as e:
                logger.error(f"get_chat: {e}")
        if not t_user:
            return await safe_edit(status, "❌ Not found!")
        uid = t_user.id
        fn = getattr(t_user, "first_name", "N/A") or "N/A"
        ln = getattr(t_user, "last_name", "") or ""
        un = getattr(t_user, "username", None) or "N/A"
        isbot = getattr(t_user, "is_bot", False)
        try:
            ph = await context.bot.get_user_profile_photos(uid, limit=1)
            has_ph = ph.total_count > 0
        except Exception:
            ph, has_ph = None, False
        bio = "No bio"
        try:
            cm = await context.bot.get_chat_member(update.message.chat_id, uid)
            bio = getattr(cm.user, "bio", None) or "No bio"
        except Exception:
            pass
        txt = f"""
╔══════════════════════════════╗
║   🔥 **ARYA INFO CARD** 🔥   ║
╚══════════════════════════════╝

👤 **USER DETAILS**
┣━ ID: `{uid}`
┣━ Name: {fn} {ln}
┣━ Username: @{un}
┗━ Bot: {'✅' if isbot else '❌'}

📝 **BIO**
┗━ {(bio or 'N/A')[:100]}

📱 [t.me/{un}](https://t.me/{un})

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ **ARYA TO BAAP H SABKA** ⚡
"""
        if has_ph and ph and ph.photos:
            try:
                photo = ph.photos[0][-1]
                await update.message.reply_photo(
                    photo=photo.file_id, caption=txt, parse_mode="Markdown"
                )
                await safe_delete(status)
                return
            except Exception as e:
                logger.error(f"Photo fail: {e}")
        await safe_edit(status, txt, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Aryainfo: {e}")
        await safe_edit(status, f"❌ {str(e)[:180]}")


# ═══════════════════════════════════════════════════════
# COMMAND MAP
# ═══════════════════════════════════════════════════════

COMMAND_MAP = {
    # Public
    "start": start_cmd, "help": help_cmd, "ping": ping_cmd, "test": test_cmd,
    "check": check_cmd,
    "yt": yt_cmd, "song": song_cmd,
    "logo": logo_cmd, "fem": fem_cmd,
    "custmstk": custmstk_cmd, "cs": custmstk_cmd,
    "info": info_cmd, "aryainfo": aryainfo_cmd,
    "roast": roast_cmd, "shayari": shayari_cmd, "joke": joke_cmd,
    "quote": quote_cmd, "qt": qt_cmd,
    "truth": truth_cmd, "dare": dare_cmd,
    "ship": ship_cmd, "love": ship_cmd,
    "coin": coin_cmd, "flip": coin_cmd,
    "dice": dice_cmd, "roll": dice_cmd,
    "8ball": eightball_cmd, "rps": rps_cmd,
    "cat": cat_cmd, "dog": dog_cmd, "wasted": wasted_cmd,
    # Group admin
    "mute": mute_cmd, "unmute": unmute_cmd, "prompt": prompt_cmd,
    "lock": lock_cmd, "unlock": unlock_cmd,
    # Owner only
    "block": block_cmd, "unblock": unblock_cmd, "blocklist": blocklist_cmd,
    "rr": rr_cmd, "srr": srr_cmd, "gc": gc_cmd,
}


# ═══════════════════════════════════════════════════════
# MASTER HANDLER
# ═══════════════════════════════════════════════════════

async def master_handler(update, context):
    try:
        if not update.message:
            return

        sender_id = update.effective_user.id

        # ────── RR AUTO-REPLY CHECK ──────
        if sender_id != OWNER_ID and str(sender_id) in RR_USERS:
            try:
                info = RR_USERS[str(sender_id)]
                un = info.get("username", "")
                name = info.get("name", "User")
                mention = f"@{un}" if un else name
                custom = info.get("custom", "")

                if custom:
                    reply_text = f"{mention} — {custom}"
                else:
                    reply_text = f"{mention} — {random.choice(RR_DEFAULT_REPLIES)}"

                await update.message.reply_text(reply_text)
            except Exception as e:
                logger.error(f"RR reply error: {e}")
            return
        # ────── END RR CHECK ──────

        # ────── LOCK CHECK ──────
        if update.effective_chat and update.effective_chat.id in LOCKED_CHATS:
            if sender_id != OWNER_ID:
                try:
                    member = await context.bot.get_chat_member(
                        update.effective_chat.id, sender_id
                    )
                    if member.status not in ("administrator", "creator"):
                        try:
                            await update.message.delete()
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
        # ────── END LOCK CHECK ──────

        if not update.message.text:
            return

        raw = update.message.text
        if DEBUG:
            logger.info(f"📩 MSG from {sender_id}: {raw[:100]}")

        # Track groups
        if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            if update.effective_chat.id not in KNOWN_CHATS:
                KNOWN_CHATS.add(update.effective_chat.id)
                await save_chats()
                logger.info(f"📋 New group tracked: {update.effective_chat.id}")

        text = raw.strip()
        if not text.startswith(COMMAND_PREFIX):
            return
        body = text[len(COMMAND_PREFIX):]
        if not body:
            return
        parts = body.split(maxsplit=1)
        cmd = parts[0].lower().strip()
        args_str = parts[1] if len(parts) > 1 else ""
        if "@" in cmd:
            cmd = cmd.split("@")[0]
        context.args = args_str.split() if args_str else []

        # Block check
        if sender_id in BLOCKED_USERS:
            if DEBUG:
                logger.info(f"🚫 Blocked user {sender_id} tried .{cmd}")
            return

        # ✅ FORCE-JOIN CHECK (ON)
        # Owner exempt, verified users skip
        if FORCE_JOIN_ENABLED and FORCE_JOIN_CHAT_ID:
            if sender_id != OWNER_ID and sender_id not in VERIFIED_USERS:
                joined = await is_user_joined(update, context)
                if not joined:
                    await send_join_message(update, context)
                    return

        # Command dispatch
        handler = COMMAND_MAP.get(cmd)
        if handler:
            logger.info(f"▶️ Executing .{cmd} from {sender_id}")
            await handler(update, context)
        else:
            if DEBUG:
                logger.info(f"❓ Unknown command: .{cmd}")
    except Exception as e:
        logger.error(f"master_handler error: {e}\n{traceback.format_exc()}")


# ═══════════════════════════════════════════════════════
# WEBHOOK SERVER
# ═══════════════════════════════════════════════════════

async def webhook_handler(request):
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, apps[0].bot)
        await apps[0].process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)


async def health_handler(request):
    return web.Response(text="ARYA BOT ALIVE ✅")


async def self_ping():
    if not RENDER_EXTERNAL_URL:
        print("⚠️ RENDER_EXTERNAL_URL set nahi — self-ping disabled")
        return
    url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/health"
    print(f"🔄 Self-ping started: {url}")
    while True:
        try:
            await asyncio.sleep(14 * 60)
            req = urllib.request.Request(url, headers={"User-Agent": "ARYA-Ping/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                logger.info(f"🔄 Self-ping OK ({r.status})")
        except Exception as e:
            logger.warning(f"Self-ping fail: {e}")


async def run_webhook_server():
    if not HAS_AIOHTTP:
        print("❌ aiohttp missing — webhook mode fail")
        return
    app_web = web.Application()
    app_web.router.add_post(WEBHOOK_PATH, webhook_handler)
    app_web.router.add_get("/health", health_handler)
    app_web.router.add_get("/", health_handler)

    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"✅ Web server running on port {PORT}")
    print(f"   Webhook path: {WEBHOOK_PATH}")


# ═══════════════════════════════════════════════════════
# BUILD
# ═══════════════════════════════════════════════════════

def build_app(token):
    app = Application.builder().token(token).build()
    app.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(MessageHandler(filters.TEXT, master_handler))
    return app


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

async def run_all_bots():
    global apps, bots
    failed = []

    print(f"\n🚀 Starting {len(TOKENS)} bot(s)...\n")

    await init_mongo()

    print(f"📋 Known groups: {len(KNOWN_CHATS)}")
    print(f"✅ Verified: {len(VERIFIED_USERS)}")
    print(f"🚫 Blocked: {len(BLOCKED_USERS)}")
    print(f"🔔 RR users: {len(RR_USERS)}")
    print(f"🔒 Locked groups: {len(LOCKED_CHATS)}")
    print(f"🎬 ffmpeg: {'✅' if HAS_FFMPEG else '❌'}")
    print(f"🎞️  rlottie: {'✅' if HAS_RLOTTIE else '❌'}")
    print(f"💾 MongoDB: {'✅' if _use_mongo else '⚠️ memory only'}")
    print(f"🔐 Force-join: {'✅ ON' if FORCE_JOIN_ENABLED else '❌ OFF'}")

    try:
        fp = load_all_fonts()
        print(f"✅ Fonts loaded: {len(fp)}")
    except Exception as e:
        print(f"⚠️ Font init: {e}")

    for idx, token in enumerate(TOKENS, 1):
        token = token.strip()
        if not token:
            print(f"⚠️ Bot{idx}: Token empty hai!")
            failed.append(f"Bot{idx}")
            continue
        ok = False
        for attempt in range(3):
            try:
                app = build_app(token)
                await app.initialize()
                me = await app.bot.get_me()

                if RENDER_EXTERNAL_URL:
                    webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}{WEBHOOK_PATH}"
                    await app.bot.set_webhook(
                        url=webhook_url,
                        drop_pending_updates=True,
                        allowed_updates=[
                            "message", "edited_message",
                            "my_chat_member", "chat_member", "callback_query",
                        ],
                    )
                    print(f"✅ Webhook set: {webhook_url}")
                else:
                    await app.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=[
                            "message", "edited_message",
                            "my_chat_member", "chat_member", "callback_query",
                        ],
                    )
                    print(f"✅ Polling started (local mode)")

                await app.start()
                apps.append(app)
                bots.append(app.bot)
                print(f"✅ Bot {idx}/{len(TOKENS)}: @{me.username}")
                ok = True
                break
            except Exception as e:
                logger.warning(f"⚠️ Bot{idx} try{attempt+1}: {e}")
                await asyncio.sleep(2)
        if not ok:
            failed.append(f"Bot{idx}")

    print("\n" + "=" * 55)
    print("🎉 ARYA BOT READY")
    print(f"✅ Active: {len(bots)}/{len(TOKENS)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"🔹 Prefix: '{COMMAND_PREFIX}'")
    print(f"👑 Owner: {OWNER_ID}")
    print(f"🔐 Force-Join: {'✅ ON' if FORCE_JOIN_ENABLED else '❌ OFF'}")
    print(f"🌐 Mode: {'WEBHOOK' if RENDER_EXTERNAL_URL else 'POLLING'}")
    print("=" * 55)
    print("\n🔐 Sab use kar sakte hain — par pehle GC join karna padega!")
    print("👑 Owner commands: .block .unblock .blocklist .rr .srr .gc")
    print("🛡️  Group-admin commands: .mute .unmute .prompt .lock .unlock")
    print("\n🟢 Running... Ctrl+C to stop\n")

    if not bots:
        return

    if RENDER_EXTERNAL_URL:
        await run_webhook_server()
        asyncio.create_task(self_ping())

    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(run_all_bots())
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
    except Exception as e:
        print(f"❌ Fatal: {e}")
        traceback.print_exc()