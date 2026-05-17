import io
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from firebase.client import (
    get_user_by_telegram_id, get_shifts_by_user,
    add_photo_to_shift, upload_photo_to_storage,
    get_pending_state, set_pending_state, clear_pending_state
)
from bot.keyboards import photo_shift_select_kb

logger = logging.getLogger(__name__)
router = Router()

class PhotoStates(StatesGroup):
    waiting_shift_select = State()

@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    
    # Get largest photo
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Store file_id temporarily
    set_pending_state(message.from_user.id, {
        **( get_pending_state(message.from_user.id) or {} ),
        "pending_photo_file_id": file_id
    })
    
    shifts = get_shifts_by_user(user["id"], limit=5)
    open_shifts = [s for s in shifts if s.get("status") == "open"]
    
    if not open_shifts:
        await message.answer("У вас нет открытых смен. Создайте смену командой /smena")
        return
    
    await message.answer(
        "📷 Фото получено! К какой смене привязать?",
        reply_markup=photo_shift_select_kb(open_shifts)
    )
    await state.set_state(PhotoStates.waiting_shift_select)

@router.callback_query(F.data.startswith("photo_to_shift:"))
async def cb_photo_to_shift(cb: CallbackQuery, state: FSMContext):
    shift_id = cb.data.split(":")[1]
    pending = get_pending_state(cb.from_user.id)
    
    if not pending or "pending_photo_file_id" not in pending:
        await cb.answer("Фото не найдено, отправьте снова")
        return
    
    file_id = pending["pending_photo_file_id"]
    
    # Download photo from Telegram
    wait_msg = await cb.message.answer("⏳ Загружаю фото...")
    try:
        file = await cb.bot.get_file(file_id)
        file_bytes_io = await cb.bot.download_file(file.file_path)
        file_bytes = file_bytes_io.read()
        
        filename = f"{shift_id}_{file_id[:8]}.jpg"
        photo_url = await upload_photo_to_storage(file_bytes, filename)
        
        result = add_photo_to_shift(shift_id, photo_url)
        await wait_msg.delete()
        
        if result is False:
            await cb.message.answer("❌ Максимум 10 фото на смену")
        else:
            await cb.message.edit_text(f"✅ Фото добавлено к смене")
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        await wait_msg.delete()
        await cb.message.answer("❌ Ошибка загрузки фото. Попробуйте снова.")
    
    # Clear photo from pending
    pending.pop("pending_photo_file_id", None)
    if pending:
        set_pending_state(cb.from_user.id, pending)
    else:
        clear_pending_state(cb.from_user.id)
    
    await state.clear()

@router.callback_query(F.data == "cancel_photo")
async def cb_cancel_photo(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Добавление фото отменено")

@router.callback_query(F.data.startswith("add_photo:"))
async def cb_add_photo_prompt(cb: CallbackQuery, state: FSMContext):
    shift_id = cb.data.split(":")[1]
    set_pending_state(cb.from_user.id, {
        **(get_pending_state(cb.from_user.id) or {}),
        "photo_shift_id": shift_id
    })
    await cb.message.answer("📷 Отправьте фото в чат — я автоматически привяжу его к этой смене")
    await cb.answer()
