"""HTML-safe Berry Store Telegram menu presentation.

Normal Unicode emojis are the safe default. Optional Telegram custom-emoji IDs
are owner-supplied configuration; this module never fetches, guesses or embeds
an unverified icon pack. Callback buttons / payment controls are unchanged.
"""
from __future__ import annotations

from html import escape
import os
import re

_CUSTOM_EMOJI_ID = re.compile(r"[0-9]{12,24}\Z")
_APP_ICONS = (
    ("netflix", "🎬", "NETFLIX"),
    ("spotify", "🎧", "SPOTIFY"),
    ("youtube", "▶️", "YOUTUBE"),
    ("disney", "🏰", "DISNEY"),
    ("hbo", "🎞️", "HBO"),
    ("iqiyi", "📺", "IQIYI"),
    ("viu", "📺", "VIU"),
    ("wetv", "📺", "WETV"),
    ("tonton", "📺", "TONTON"),
    ("loklok", "🍿", "LOKLOK"),
    ("moviebox", "🍿", "MOVIEBOX"),
    ("canva", "🎨", "CANVA"),
    ("capcut", "✂️", "CAPCUT"),
    ("adobe", "🅰️", "ADOBE"),
    ("lightroom", "📸", "LIGHTROOM"),
    ("photoshop", "🖼️", "PHOTOSHOP"),
    ("picsart", "🖌️", "PICSART"),
    ("rem ini", "🪄", "REMINI"),
    ("remini", "🪄", "REMINI"),
    ("microsoft", "🪟", "MICROSOFT"),
    ("office", "🪟", "MICROSOFT"),
    ("windows", "🪟", "MICROSOFT"),
    ("autodesk", "📐", "AUTODESK"),
    ("chatgpt", "🤖", "CHATGPT"),
    ("gemini", "✨", "GEMINI"),
    ("grok", "🪐", "GROK"),
    ("vpn", "🛡️", "VPN"),
    ("api key", "🔑", "API"),
    ("turnitin", "📄", "TURNITIN"),
    ("pdf", "📕", "PDF"),
    ("notion", "📓", "NOTION"),
    ("prime video", "📺", "PRIME"),
)


def icon(key: str, fallback: str) -> str:
    """Telegram <tg-emoji> is opt-in: never assume Premium or valid IDs."""
    if os.getenv("BERRY_ANIMATED_EMOJI_ENABLED", "").strip().lower() == "true":
        raw = os.getenv("BERRY_EMOJI_" + key.upper() + "_ID", "").strip()
        if _CUSTOM_EMOJI_ID.fullmatch(raw):
            return f'<tg-emoji emoji-id="{raw}">{escape(fallback)}</tg-emoji>'
    return escape(fallback)


def product_icon(product_name: str) -> str:
    normal = str(product_name or "").casefold()
    for phrase, fallback, key in _APP_ICONS:
        if phrase in normal:
            return icon(key, fallback)
    return icon("PRODUCT", "📦")


def welcome_message(*, welcome: str, first_name: str, username: str,
                    telegram_id: int, total_users: int, total_sold: int,
                    updated: str) -> str:
    return (
        f"{icon('FIRE', '🔥')} <b>BERRY STORE</b> {icon('FIRE', '🔥')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{escape(str(welcome))}\n\n"
        f"{icon('WAVE', '👋')} Hi, <b>{escape(str(first_name))}</b>!\n"
        "Your Trusted Digital Hub ✨\n\n"
        "👤 <b>YOUR ACCOUNT</b>\n"
        f"└ Username: @{escape(str(username or 'tiada'))}\n"
        f"└ ID: <code>{int(telegram_id)}</code>\n\n"
        f"{icon('CHART', '📊')} <b>STORE STATS</b>\n"
        f"└ Total Users: <b>{int(total_users):,}</b>\n"
        f"└ Total Sold: <b>{int(total_sold):,}</b> units\n\n"
        f"{icon('SPARKLE', '✨')} Pilih menu di bawah untuk mula!\n"
        f"<i>Updated: {escape(str(updated))}</i>"
    )


def shop_header(title: str) -> str:
    return (
        f"{icon('FIRE', '🔥')} <b>{escape(str(title))}</b> "
        f"{icon('FIRE', '🔥')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )


def shop_line(index: int, name: str, stock: int) -> str:
    return (
        f"{product_icon(name)} <b>{int(index)}.</b> "
        f"{escape(str(name))} "
        f"(<code>{int(stock)}</code> qty.)\n"
    )


def shop_footer(text: str) -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{escape(str(text))}"
    )


def ai_studio_message(*, balance: str, wallet_status: str) -> str:
    return (
        f"{icon('SPARKLE', '✨')} <b>BERRY AI STUDIO</b> "
        f"{icon('SPARKLE', '✨')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{icon('WAVE', '👋')} Welcome to Berry AI Studio!\n"
        "🎬 Create • 🎨 Imagine • 🪄 Transform\n\n"
        f"{icon('WALLET', '💰')} <b>Your Balance:</b> {escape(str(balance))}\n"
        f"{escape(str(wallet_status))}"
        "Pilih studio yang kau nak explore 👇\n\n"
        "🔒 <i>Admin preview — tiada paid generation atau caj.</i>"
    )
