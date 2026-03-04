from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.ui import strings as ui_str


def reminder_action_keyboard(habit_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Done", callback_data=f"today:done:{habit_id}")
    kb.button(text="⏭ Skip", callback_data=f"today:skip:{habit_id}")
    kb.button(text="📝 Snooze 10m", callback_data=f"today:snooze:{habit_id}")
    kb.button(text=ui_str.HOME_BUTTON, callback_data="nav:home")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def daily_summary_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=ui_str.CLEAR_BUTTON, callback_data="summary:clear")
    kb.adjust(1)
    return kb.as_markup()
