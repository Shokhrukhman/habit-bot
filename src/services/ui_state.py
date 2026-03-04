from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import UiState, User

HOME = "HOME"
HABITS_MENU = "HABITS_MENU"
STATS_MENU = "STATS_MENU"
SETTINGS_MENU = "SETTINGS_MENU"
TIMEZONE_SELECT = "TIMEZONE_SELECT"
NOTIFICATION_SETTINGS = "NOTIFICATION_SETTINGS"
SNOOZE_CUSTOM_INPUT = "SNOOZE_CUSTOM_INPUT"
HABITS_LIST = "HABITS_LIST"
HABIT_VIEW = "HABIT_VIEW"
HABIT_ADD = "HABIT_ADD"
HABIT_ADD_TIME = "HABIT_ADD_TIME"
TODAY = "TODAY"
MONTH = "MONTH"
CALENDAR_PICKER = "CALENDAR_PICKER"
DAY_DETAILS = "DAY_DETAILS"
DEFAULT_TZ = "Asia/Tashkent"
DEFAULT_SNOOZE = 10

SCREEN_NAMES = {
    HOME,
    HABITS_MENU,
    STATS_MENU,
    SETTINGS_MENU,
    TIMEZONE_SELECT,
    NOTIFICATION_SETTINGS,
    SNOOZE_CUSTOM_INPUT,
    HABITS_LIST,
    HABIT_VIEW,
    HABIT_ADD,
    HABIT_ADD_TIME,
    TODAY,
    MONTH,
    CALENDAR_PICKER,
    DAY_DETAILS,
}


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    stmt: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
    return await session.scalar(stmt)


async def _resolve_user(session: AsyncSession, tg_id: int) -> User:
    stmt: Select[tuple[User]] = select(User).where(User.telegram_id == tg_id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        telegram_id=tg_id,
        timezone=DEFAULT_TZ,
        snooze_minutes=DEFAULT_SNOOZE,
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_ui_state(session: AsyncSession, tg_id: int) -> UiState:
    user = await _resolve_user(session, tg_id)
    stmt: Select[tuple[UiState]] = select(UiState).where(UiState.user_id == user.id)
    ui_state = await session.scalar(stmt)
    if ui_state:
        return ui_state
    ui_state = UiState(user_id=user.id, current_screen=HOME, stack=[], payload={})
    session.add(ui_state)
    await session.commit()
    await session.refresh(ui_state)
    return ui_state


async def save_ui_state(
    session: AsyncSession,
    ui_state: UiState,
    *,
    current_screen: str | None = None,
    payload: dict | None = None,
    stack: list[dict] | None = None,
    screen_message_id: int | None | object = ...,
) -> UiState:
    if current_screen is not None:
        ui_state.current_screen = current_screen
    if payload is not None:
        ui_state.payload = payload
    if stack is not None:
        ui_state.stack = stack
    if screen_message_id is not ...:
        ui_state.screen_message_id = screen_message_id
    ui_state.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(ui_state)
    return ui_state
