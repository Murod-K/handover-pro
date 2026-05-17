from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

MINI_APP_URL = "https://handover-pro-bot.onrender.com/app"

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Открыть приложение", web_app={"url": MINI_APP_URL})
    )
    builder.row(
        InlineKeyboardButton(text="➕ Новая смена", callback_data="new_shift"),
        InlineKeyboardButton(text="📋 История", callback_data="history"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статус", callback_data="status"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
    )
    return builder.as_markup()

def confirm_constructions_kb(shift_draft_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Верно, создать смену", callback_data=f"confirm_shift:{shift_draft_id}"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_shift:{shift_draft_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_shift")
    )
    return builder.as_markup()

def shift_actions_kb(shift_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📄 Отчёт", callback_data=f"report:{shift_id}"),
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_close:{shift_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📷 Добавить фото", callback_data=f"add_photo:{shift_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="history"),
    )
    return builder.as_markup()

def confirm_close_kb(shift_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Выполнено", callback_data=f"close_shift:done:{shift_id}"),
        InlineKeyboardButton(text="⚠️ Частично", callback_data=f"close_shift:partial:{shift_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"close_shift:failed:{shift_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data=f"shift_detail:{shift_id}"),
    )
    return builder.as_markup()

def photo_shift_select_kb(shifts: list):
    builder = InlineKeyboardBuilder()
    for shift in shifts[:5]:
        shift_id = shift["id"]
        label = shift.get("object_name", "Объект")[:20]
        date = shift.get("created_at", "")[:10]
        builder.row(
            InlineKeyboardButton(
                text=f"📋 {label} ({date})",
                callback_data=f"photo_to_shift:{shift_id}"
            )
        )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_photo"))
    return builder.as_markup()

def history_shifts_kb(shifts: list):
    builder = InlineKeyboardBuilder()
    for shift in shifts:
        sid = shift["id"]
        obj = shift.get("object_name", "—")[:15]
        status_icon = {"open": "🟡", "closed": "✅", "partial": "⚠️"}.get(shift.get("status"), "⚪")
        date = shift.get("created_at", "")[:10]
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {obj} {date}",
                callback_data=f"shift_detail:{sid}"
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 Главная", callback_data="main_menu"))
    return builder.as_markup()

def cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()
