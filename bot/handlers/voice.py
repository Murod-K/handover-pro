import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from firebase.client import get_user_by_telegram_id
from bot.gpt import transcribe_voice, parse_constructions, format_constructions_preview
from bot.keyboards import confirm_constructions_kb
from firebase.client import set_pending_state
import uuid

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    
    wait_msg = await message.answer("🎤 Распознаю голосовое...")
    
    try:
        file = await message.bot.get_file(message.voice.file_id)
        file_bytes_io = await message.bot.download_file(file.file_path)
        file_bytes = file_bytes_io.read()
        
        text = await transcribe_voice(file_bytes, "voice.ogg")
        if not text:
            await wait_msg.delete()
            await message.answer("❌ Не удалось распознать голос. Попробуйте снова.")
            return
        
        await wait_msg.edit_text(f"🎤 Распознано: <i>{text}</i>\n\n🤖 Парсю конструкции...", parse_mode="HTML")
        
        parsed = await parse_constructions(text)
        await wait_msg.delete()
        
        if not parsed or not parsed.get("constructions"):
            await message.answer(
                "❌ Не удалось распознать конструкции. Попробуйте ещё раз."
            )
            return
        
        draft_id = str(uuid.uuid4())[:8]
        set_pending_state(message.from_user.id, {"draft_id": draft_id, "data": parsed})
        
        preview = format_constructions_preview(parsed)
        await message.answer(
            f"📋 <b>Проверьте данные смены:</b>\n\n{preview}\n\nВсё верно?",
            parse_mode="HTML",
            reply_markup=confirm_constructions_kb(draft_id)
        )
    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await wait_msg.delete()
        await message.answer("❌ Ошибка обработки голосового сообщения")

# Fallback: plain text that's not a command → treat as shift description
@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, state: FSMContext):
    from aiogram.fsm.state import State
    current_state = await state.get_state()
    if current_state:
        return  # Let the FSM handle it
    
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        return
    
    # Only process if it looks like a shift description (has construction-related words)
    keywords = ["колонн", "стен", "плит", "арматур", "бетон", "натур", "балк", "ригел", "фундамент", "перемычк"]
    text_lower = message.text.lower()
    if not any(kw in text_lower for kw in keywords):
        return
    
    wait_msg = await message.answer("🤖 Распознаю конструкции...")
    parsed = await parse_constructions(message.text)
    await wait_msg.delete()
    
    if not parsed or not parsed.get("constructions"):
        return
    
    draft_id = str(uuid.uuid4())[:8]
    set_pending_state(message.from_user.id, {"draft_id": draft_id, "data": parsed})
    
    preview = format_constructions_preview(parsed)
    await message.answer(
        f"📋 <b>Обнаружено описание смены:</b>\n\n{preview}\n\nСоздать смену?",
        parse_mode="HTML",
        reply_markup=confirm_constructions_kb(draft_id)
    )
