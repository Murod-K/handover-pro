import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

async def scheduler_task(bot):
    """Background task: check for overdue shifts every 30 minutes"""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 min
            await check_overdue_shifts(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")

async def check_overdue_shifts(bot):
    from firebase.client import get_open_shifts, get_user_by_telegram_id
    open_shifts = get_open_shifts()
    now = datetime.utcnow()
    
    for shift in open_shifts:
        created_at_str = shift.get("created_at", "")
        if not created_at_str:
            continue
        try:
            created_at = datetime.fromisoformat(created_at_str)
            age_hours = (now - created_at).total_seconds() / 3600
            
            if age_hours >= 13:
                engineer_id = shift.get("engineer_id")
                if not engineer_id:
                    continue
                from firebase.client import get_all_users
                users = {u["id"]: u for u in get_all_users()}
                engineer = users.get(engineer_id)
                if engineer:
                    tg_id = engineer.get("telegram_id")
                    if tg_id:
                        try:
                            await bot.send_message(
                                tg_id,
                                f"⏰ <b>Напоминание</b>\n\n"
                                f"Смена на объекте <b>{shift.get('object_name','—')}</b> "
                                f"открыта уже {int(age_hours)} часов.\n"
                                f"Не забудьте закрыть смену!",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Overdue notify error: {e}")
        except Exception as e:
            logger.error(f"Date parse error: {e}")
