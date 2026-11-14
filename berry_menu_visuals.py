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

# Exact names allowed for the bot owner's /setemoji mapping. Persisted IDs
# come from genuine Telegram custom_emoji MessageEntity objects only.
AVAILABLE_ICON_KEYS = frozenset({
    *(key for _, _, key in _APP_ICONS),
    "FIRE", "WAVE", "CHART", "SPARKLE", "WALLET", "PRODUCT"
})


def icon(key: str, fallback: str, custom_ids: dict | None = None) -> str:
    """Telegram custom emoji opt-in; the owner must provide real emoji IDs."""
    if os.getenv("BERRY_ANIMATED_EMOJI_ENABLED", "").strip().lower() == "true":
        raw = str((custom_ids or {}).get(key.upper()) or
                  os.getenv("BERRY_EMOJI_" + key.upper() + "_ID", "")).strip()
        if _CUSTOM_EMOJI_ID.fullmatch(raw):
            return f'<tg-emoji emoji-id="{raw}">{escape(fallback)}</tg-emoji>'
    return escape(fallback)


def product_icon(product_name: str, custom_ids: dict | None = None) -> str:
    normal = str(product_name or "").casefold()
    for phrase, fallback, key in _APP_ICONS:
        if phrase in normal:
            return icon(key, fallback, custom_ids)
    return icon("PRODUCT", "📦", custom_ids)


def welcome_message(*, welcome: str, first_name: str, username: str,
                    telegram_id: int, total_users: int, total_sold: int,
                    updated: str, custom_ids: dict | None = None) -> str:
    return (
        f"{icon('FIRE', '🔥', custom_ids)} <b>BERRY STORE</b> {icon('FIRE', '🔥', custom_ids)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{escape(str(welcome))}\n\n"
        f"{icon('WAVE', '👋', custom_ids)} Hi, <b>{escape(str(first_name))}</b>!\n"
        "Your Trusted Digital Hub ✨\n\n"
        "👤 <b>YOUR ACCOUNT</b>\n"
        f"└ Username: @{escape(str(username or 'tiada'))}\n"
        f"└ ID: <code>{int(telegram_id)}</code>\n\n"
        f"{icon('CHART', '📊', custom_ids)} <b>STORE STATS</b>\n"
        f"└ Total Users: <b>{int(total_users):,}</b>\n"
        f"└ Total Sold: <b>{int(total_sold):,}</b> units\n\n"
        f"{icon('SPARKLE', '✨', custom_ids)} Pilih menu di bawah untuk mula!\n"
        f"<i>Updated: {escape(str(updated))}</i>"
    )


def shop_header(title: str, custom_ids: dict | None = None) -> str:
    return (
        f"{icon('FIRE', '🔥', custom_ids)} <b>{escape(str(title))}</b> "
        f"{icon('FIRE', '🔥', custom_ids)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )


def shop_line(index: int, name: str, stock: int, custom_ids: dict | None = None) -> str:
    return (
        f"{product_icon(name, custom_ids)} <b>{int(index)}.</b> "
        f"{escape(str(name))} "
        f"(<code>{int(stock)}</code> qty.)\n"
    )


def shop_footer(text: str) -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{escape(str(text))}"
    )


def ai_studio_message(*, balance: str, wallet_status: str,
                      custom_ids: dict | None = None) -> str:
    return (
        f"{icon('SPARKLE', '✨', custom_ids)} <b>BERRY AI STUDIO</b> "
        f"{icon('SPARKLE', '✨', custom_ids)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{icon('WAVE', '👋', custom_ids)} Welcome to Berry AI Studio!\n"
        "🎬 Create • 🎨 Imagine • 🪄 Transform\n\n"
        f"{icon('WALLET', '💰', custom_ids)} <b>Your Balance:</b> {escape(str(balance))}\n"
        f"{escape(str(wallet_status))}"
        "Pilih studio yang kau nak explore 👇\n\n"
        "🔒 <i>Admin preview — tiada paid generation atau caj.</i>"
    )
