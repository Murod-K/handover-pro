import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from firebase.client import get_user_by_telegram_id, create_user
from bot.keyboards import main_menu_kb, history_shifts_kb, shift_actions_kb

logger = logging.getLogger(__name__)
router = Router()

def get_or_create_user(message: Message) -> dict:
    tg_id = message.from_user.id
    user = get_user_by_telegram_id(tg_id)
    if not user:
        user_data = {
            "telegram_id": tg_id,
            "name": message.from_user.full_name,
            "username": message.from_user.username or "",
            "role": "engineer",
            "shift_type": "day",
        }
        uid = create_user(user_data)
        user = {**user_data, "id": uid}
    return user

@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_or_create_user(message)
    name = user.get("name", "коллега")
    role_label = {"admin": "Администратор", "supervisor": "Прораб", "engineer": "Инженер"}.get(user.get("role"), "Инженер")
    
    text = (
        f"👷 <b>Handover Pro</b>\n\n"
        f"Привет, {name}! ({role_label})\n\n"
        f"Система передачи смены на строительной площадке.\n\n"
        f"<b>Команды:</b>\n"
        f"➕ /smena — создать смену\n"
        f"📋 /history — последние смены\n"
        f"📊 /status — открытые смены\n"
        f"📄 /report [ID] — отчёт смены\n\n"
        f"Или просто напиши что произошло на смене — я распознаю ✍️"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())

@router.message(Command("status"))
async def cmd_status(message: Message):
    from firebase.client import get_open_shifts, get_user_by_telegram_id
    user = get_user_by_telegram_id(message.from_user.id)
    open_shifts = get_open_shifts()
    
    if not open_shifts:
        await message.answer("✅ Нет открытых смен")
        return
    
    lines = [f"🟡 <b>Открытые смены ({len(open_shifts)}):</b>\n"]
    for s in open_shifts[:10]:
        obj = s.get("object_name", "—")
        eng = s.get("engineer_name", "—")
        date = s.get("created_at", "")[:16].replace("T", " ")
        lines.append(f"• {obj} — {eng} ({date})")
    
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("history"))
async def cmd_history(message: Message):
    from firebase.client import get_user_by_telegram_id, get_shifts_by_user
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала запустите бота: /start")
        return
    
    shifts = get_shifts_by_user(user["id"], limit=5)
    if not shifts:
        await message.answer("У вас ещё нет смен. Создайте первую: /smena")
        return
    
    await message.answer(
        "📋 <b>Последние смены:</b>",
        parse_mode="HTML",
        reply_markup=history_shifts_kb(shifts)
    )

@router.message(Command("report"))
async def cmd_report(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Укажите ID смены: /report [ID]")
        return
    shift_id = args[1]
    from firebase.client import get_shift
    from bot.handlers.shifts import generate_report_html
    shift = get_shift(shift_id)
    if not shift:
        await message.answer("Смена не найдена")
        return
    
    html = generate_report_html(shift)
    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(html.encode("utf-8"), filename=f"report_{shift_id}.html")
    await message.answer_document(file, caption=f"📄 Отчёт смены {shift_id[:8]}")

# ─── CALLBACKS ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    await cb.message.edit_text(
        "👷 <b>Handover Pro</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "history")
async def cb_history(cb: CallbackQuery):
    from firebase.client import get_user_by_telegram_id, get_shifts_by_user
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Сначала /start")
        return
    shifts = get_shifts_by_user(user["id"], limit=5)
    if not shifts:
        await cb.answer("Смен нет")
        return
    await cb.message.edit_text(
        "📋 <b>Последние смены:</b>",
        parse_mode="HTML",
        reply_markup=history_shifts_kb(shifts)
    )

@router.callback_query(F.data.startswith("shift_detail:"))
async def cb_shift_detail(cb: CallbackQuery):
    shift_id = cb.data.split(":")[1]
    from firebase.client import get_shift
    shift = get_shift(shift_id)
    if not shift:
        await cb.answer("Смена не найдена")
        return
    
    status_map = {"open": "🟡 Открыта", "closed": "✅ Закрыта", "partial": "⚠️ Частично"}
    status = status_map.get(shift.get("status"), "⚪")
    constructions = shift.get("constructions", [])
    total_m3 = sum(c.get("concrete_plan_m3", 0) or 0 for c in constructions)
    
    text = (
        f"📋 <b>{shift.get('object_name', '—')}</b>\n"
        f"Блок: {shift.get('block', '—')} | Этаж: {shift.get('floor', '—')}\n"
        f"Статус: {status}\n"
        f"Конструкций: {len(constructions)} | Бетон: {total_m3} м³\n"
        f"Инженер: {shift.get('engineer_name', '—')}\n"
        f"Дата: {shift.get('created_at', '')[:16].replace('T', ' ')}"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=shift_actions_kb(shift_id))

@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    text = (
        "❓ <b>Как пользоваться:</b>\n\n"
        "1. Напишите или надиктуйте что произошло:\n"
        "<i>«Колонны К-1 К-2 К-3, арматура сдана, бетон 45 кубов насосом»</i>\n\n"
        "2. Я распознаю конструкции и спрошу подтверждение\n\n"
        "3. После подтверждения смена создаётся в базе\n\n"
        "4. Ночная смена получит уведомление о передаче\n\n"
        "📱 Полный функционал — в Mini App"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu_kb())
