import json
import logging
import uuid
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from firebase.client import (
    get_user_by_telegram_id, create_shift, get_shift, update_shift,
    get_shifts_by_user, set_pending_state, get_pending_state, clear_pending_state
)
from bot.keyboards import confirm_constructions_kb, shift_actions_kb, confirm_close_kb, cancel_kb
from bot.gpt import parse_constructions, format_constructions_preview

logger = logging.getLogger(__name__)
router = Router()

class ShiftStates(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()
    waiting_close_note = State()

# ─── /smena COMMAND ──────────────────────────────────────────────────────────

@router.message(Command("smena"))
async def cmd_smena(message: Message, state: FSMContext):
    await state.set_state(ShiftStates.waiting_text)
    await message.answer(
        "✍️ <b>Создание смены</b>\n\n"
        "Опишите что произошло на смене:\n"
        "<i>Например: «Колонны К-1 К-2, арматура сдана, бетон 45 кубов насосом, натура дана»</i>\n\n"
        "Или отправьте голосовое сообщение 🎤",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )

@router.message(ShiftStates.waiting_text, F.text)
async def process_shift_text(message: Message, state: FSMContext):
    await _process_shift_input(message, state, message.text)

async def _process_shift_input(message: Message, state: FSMContext, text: str):
    wait_msg = await message.answer("🤖 Распознаю конструкции...")
    parsed = await parse_constructions(text)
    await wait_msg.delete()
    
    if not parsed or not parsed.get("constructions"):
        await message.answer(
            "❌ Не удалось распознать конструкции. Попробуйте ещё раз.\n"
            "Пример: <i>Колонна К-1 К-2, арматура сдана, бетон 30 кубов</i>",
            parse_mode="HTML"
        )
        return
    
    draft_id = str(uuid.uuid4())[:8]
    set_pending_state(message.from_user.id, {"draft_id": draft_id, "data": parsed})
    
    preview = format_constructions_preview(parsed)
    await message.answer(
        f"📋 <b>Проверьте данные смены:</b>\n\n{preview}\n\n"
        f"Всё верно?",
        parse_mode="HTML",
        reply_markup=confirm_constructions_kb(draft_id)
    )
    await state.set_state(ShiftStates.waiting_confirm)

# ─── CALLBACKS ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("confirm_shift:"))
async def cb_confirm_shift(cb: CallbackQuery, state: FSMContext):
    user = get_user_by_telegram_id(cb.from_user.id)
    if not user:
        await cb.answer("Ошибка: пользователь не найден")
        return
    
    pending = get_pending_state(cb.from_user.id)
    if not pending:
        await cb.answer("Данные устарели, начните заново")
        return
    
    parsed = pending["data"]
    shift_data = {
        "engineer_id": user["id"],
        "engineer_name": user.get("name", ""),
        "object_name": parsed.get("object_name", "Без названия"),
        "block": parsed.get("block", ""),
        "floor": parsed.get("floor", ""),
        "shift_type": parsed.get("shift_type", "day"),
        "constructions": parsed.get("constructions", []),
        "photos": [],
        "warnings": _check_warnings(parsed.get("constructions", [])),
    }
    
    shift_id = create_shift(shift_data)
    clear_pending_state(cb.from_user.id)
    await state.clear()
    
    warnings = shift_data["warnings"]
    warn_text = ""
    if warnings:
        warn_text = "\n\n⚠️ <b>Предупреждения:</b>\n" + "\n".join(f"• {w}" for w in warnings)
    
    await cb.message.edit_text(
        f"✅ <b>Смена создана!</b>\n"
        f"ID: <code>{shift_id}</code>\n"
        f"Объект: {shift_data['object_name']}"
        f"{warn_text}",
        parse_mode="HTML",
        reply_markup=shift_actions_kb(shift_id)
    )
    
    # Notify supervisors if warnings
    if warnings:
        await _notify_supervisors(cb.bot, shift_data, shift_id, warnings)

@router.callback_query(F.data.startswith("edit_shift:"))
async def cb_edit_shift(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ShiftStates.waiting_text)
    await cb.message.edit_text(
        "✏️ Введите исправленное описание смены:",
        reply_markup=cancel_kb()
    )

@router.callback_query(F.data == "cancel_shift")
async def cb_cancel_shift(cb: CallbackQuery, state: FSMContext):
    clear_pending_state(cb.from_user.id)
    await state.clear()
    await cb.message.edit_text("❌ Создание смены отменено")

@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Отменено")

@router.callback_query(F.data == "new_shift")
async def cb_new_shift(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ShiftStates.waiting_text)
    await cb.message.edit_text(
        "✍️ <b>Создание смены</b>\n\n"
        "Опишите что произошло:\n"
        "<i>Колонны К-1 К-2, арматура сдана, бетон 45 кубов насосом</i>\n\n"
        "Или отправьте голосовое 🎤",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )

@router.callback_query(F.data.startswith("confirm_close:"))
async def cb_confirm_close(cb: CallbackQuery):
    shift_id = cb.data.split(":")[1]
    await cb.message.edit_text(
        "✅ <b>Подтверждение смены</b>\n\nВыберите статус выполнения:",
        parse_mode="HTML",
        reply_markup=confirm_close_kb(shift_id)
    )

@router.callback_query(F.data.startswith("close_shift:"))
async def cb_close_shift(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    status_map = {"done": "closed", "partial": "partial", "failed": "failed"}
    result = status_map.get(parts[1], "closed")
    shift_id = parts[2]
    
    update_shift(shift_id, {
        "status": result,
        "closed_at": datetime.utcnow().isoformat(),
        "closed_by": cb.from_user.id,
    })
    
    shift = get_shift(shift_id)
    status_label = {"closed": "✅ Выполнено", "partial": "⚠️ Частично", "failed": "❌ Не выполнено"}.get(result, result)
    
    await cb.message.edit_text(
        f"Смена подтверждена: {status_label}\n"
        f"Объект: {shift.get('object_name', '—')}",
        parse_mode="HTML"
    )
    
    # Notify opposite shift
    await _notify_opposite_shift(cb.bot, shift, result)

@router.callback_query(F.data.startswith("report:"))
async def cb_report(cb: CallbackQuery):
    shift_id = cb.data.split(":")[1]
    shift = get_shift(shift_id)
    if not shift:
        await cb.answer("Смена не найдена")
        return
    
    html = generate_report_html(shift)
    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(html.encode("utf-8"), filename=f"report_{shift_id[:8]}.html")
    await cb.message.answer_document(file, caption=f"📄 Отчёт смены")
    await cb.answer()

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _check_warnings(constructions: list) -> list:
    warnings = []
    for c in constructions:
        marks = ", ".join(c.get("marks", []))
        ctype = c.get("type", "")
        
        if c.get("concrete_plan_m3") and c.get("nature_status") == "not_given":
            warnings.append(f"{ctype} ({marks}): натура не дана, но заливка запланирована")
        if c.get("concrete_plan_m3") and c.get("rebar_status") == "not_accepted":
            warnings.append(f"{ctype} ({marks}): арматура не сдана, но заливка запланирована")
    return warnings

async def _notify_supervisors(bot, shift_data: dict, shift_id: str, warnings: list):
    from firebase.client import get_all_users
    supervisors = [u for u in get_all_users() if u.get("role") in ("supervisor", "admin")]
    
    warn_text = "\n".join(f"⚠️ {w}" for w in warnings)
    text = (
        f"🔔 <b>Предупреждения на объекте</b>\n"
        f"Объект: {shift_data.get('object_name')}\n"
        f"Инженер: {shift_data.get('engineer_name')}\n\n"
        f"{warn_text}"
    )
    for sup in supervisors:
        tg_id = sup.get("telegram_id")
        if tg_id:
            try:
                await bot.send_message(tg_id, text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Notify supervisor error: {e}")

async def _notify_opposite_shift(bot, shift: dict, result: str):
    from firebase.client import get_all_users
    shift_type = shift.get("shift_type", "day")
    opposite = "night" if shift_type == "day" else "day"
    
    users = get_all_users()
    opposite_engineers = [u for u in users if u.get("shift_type") == opposite]
    
    status_label = {"closed": "✅ Выполнено", "partial": "⚠️ Частично", "failed": "❌ Не выполнено"}.get(result, result)
    shift_label = "☀️ Дневная" if shift_type == "day" else "🌙 Ночная"
    
    text = (
        f"🔔 <b>{shift_label} смена передана</b>\n"
        f"Объект: {shift.get('object_name', '—')}\n"
        f"Статус: {status_label}\n"
        f"Инженер: {shift.get('engineer_name', '—')}"
    )
    
    for eng in opposite_engineers:
        tg_id = eng.get("telegram_id")
        if tg_id:
            try:
                await bot.send_message(tg_id, text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Notify error: {e}")

def generate_report_html(shift: dict) -> str:
    constructions = shift.get("constructions", [])
    photos = shift.get("photos", [])
    warnings = shift.get("warnings", [])
    
    total_m3 = sum(c.get("concrete_plan_m3", 0) or 0 for c in constructions)
    
    nature_labels = {"given": "✅ Дана", "not_given": "❌ Не дана", "will_be_night": "🌙 Ночью"}
    rebar_labels = {"accepted": "✅ Сдана", "partial": "⚠️ Частично", "not_accepted": "❌ Не сдана"}
    
    rows = ""
    for c in constructions:
        marks = ", ".join(c.get("marks", []))
        rows += f"""
        <tr>
            <td>{c.get('type','—')}</td>
            <td>{marks}</td>
            <td>{nature_labels.get(c.get('nature_status',''), '—')}</td>
            <td>{rebar_labels.get(c.get('rebar_status',''), '—')}</td>
            <td>{c.get('concrete_plan_m3','—')} м³</td>
            <td>{c.get('concrete_method','—')}</td>
            <td>{c.get('comment','')}</td>
        </tr>"""
    
    photos_html = ""
    if photos:
        photos_html = "<h3>Фотоматериалы</h3><div style='display:flex;flex-wrap:wrap;gap:10px'>"
        for p in photos:
            photos_html += f"<img src='{p['url']}' style='width:200px;height:150px;object-fit:cover;border-radius:8px'>"
        photos_html += "</div>"
    
    warnings_html = ""
    if warnings:
        warnings_html = "<div class='warnings'><h3>⚠️ Предупреждения</h3><ul>"
        for w in warnings:
            warnings_html += f"<li>{w}</li>"
        warnings_html += "</ul></div>"
    
    shift_label = "☀️ Дневная" if shift.get("shift_type") == "day" else "🌙 Ночная"
    
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Отчёт смены — {shift.get('object_name','')}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; color: #1a1a1a; }}
  .header {{ background: #1a3a5c; color: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; }}
  .header h1 {{ font-size: 22px; margin-bottom: 8px; }}
  .header .meta {{ font-size: 13px; opacity: 0.85; line-height: 1.8; }}
  .stats {{ display: flex; gap: 12px; margin-bottom: 20px; }}
  .stat {{ background: #f0f4f8; border-radius: 10px; padding: 14px; flex: 1; text-align: center; }}
  .stat .num {{ font-size: 28px; font-weight: 700; color: #1a3a5c; }}
  .stat .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px; }}
  th {{ background: #1a3a5c; color: white; padding: 10px 8px; text-align: left; }}
  td {{ padding: 9px 8px; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #f8fafc; }}
  .warnings {{ background: #fff8e1; border: 1px solid #ffc107; border-radius: 8px; padding: 14px; margin-bottom: 20px; }}
  .warnings h3 {{ margin-bottom: 8px; color: #e65100; }}
  .warnings li {{ margin-left: 16px; line-height: 1.8; font-size: 14px; }}
  .signatures {{ display: flex; gap: 40px; margin-top: 30px; padding-top: 20px; border-top: 2px solid #eee; }}
  .sig {{ flex: 1; }}
  .sig .label {{ font-size: 12px; color: #888; margin-bottom: 6px; }}
  .sig .line {{ border-bottom: 1px solid #333; height: 30px; margin-bottom: 4px; }}
  .sig .name {{ font-size: 13px; font-weight: 600; }}
  @media print {{ body {{ padding: 10px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>📋 Акт передачи смены</h1>
  <div class="meta">
    🏗 Объект: <b>{shift.get('object_name','—')}</b><br>
    🏢 Блок: {shift.get('block','—')} | Этаж: {shift.get('floor','—')}<br>
    ⏱ {shift_label} | {shift.get('created_at','')[:16].replace('T',' ')}<br>
    👷 Инженер: {shift.get('engineer_name','—')}<br>
    🆔 ID: {shift.get('id','—')}
  </div>
</div>

<div class="stats">
  <div class="stat"><div class="num">{len(constructions)}</div><div class="label">Конструкций</div></div>
  <div class="stat"><div class="num">{total_m3}</div><div class="label">м³ бетона</div></div>
  <div class="stat"><div class="num">{len(photos)}</div><div class="label">Фото</div></div>
</div>

{warnings_html}

<table>
  <thead>
    <tr>
      <th>Тип</th><th>Маркировка</th><th>Натура</th><th>Арматура</th><th>Бетон</th><th>Подача</th><th>Примечание</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

{photos_html}

<div class="signatures">
  <div class="sig">
    <div class="label">Сдал:</div>
    <div class="line"></div>
    <div class="name">{shift.get('engineer_name','_________________')}</div>
  </div>
  <div class="sig">
    <div class="label">Принял:</div>
    <div class="line"></div>
    <div class="name">_________________</div>
  </div>
</div>
</body>
</html>"""
