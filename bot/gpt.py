import os
import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

CONSTRUCTION_SYSTEM_PROMPT = """Ты парсер строительных смен. Из текста или голосовой расшифровки извлекай данные о конструкциях.

Верни ТОЛЬКО валидный JSON, без markdown, без пояснений:
{
  "object_name": "название объекта если есть",
  "block": "блок/секция если есть",
  "floor": "этаж если есть",
  "shift_type": "day" или "night",
  "constructions": [
    {
      "type": "Колонна|Стена|Плита|Балка|Фундамент|Лестница|Ригель|Перемычка",
      "marks": ["К-1", "К-2"],
      "nature_status": "given|not_given|will_be_night",
      "rebar_status": "accepted|partial|not_accepted",
      "concrete_plan_m3": 45.0,
      "concrete_method": "насос|кран|вручную",
      "concrete_ready": true,
      "comment": ""
    }
  ]
}

Правила:
- Если тип не указан явно, угадай по контексту (К-х = Колонна, Ст-х = Стена, Пл-х = Плита)
- Несколько маркировок одного типа → одна запись с массивом marks
- "арматура сдана" → rebar_status: "accepted"
- "натура дана" → nature_status: "given"
- "бетон 45 кубов насосом" → concrete_plan_m3: 45, concrete_method: "насос"
- shift_type по умолчанию "day"
- Если что-то неясно, оставь пустую строку или null"""

async def parse_constructions(text: str) -> dict | None:
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CONSTRUCTION_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"GPT JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"GPT error: {e}")
        return None

async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    try:
        from io import BytesIO
        audio_file = BytesIO(audio_bytes)
        audio_file.name = filename
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ru",
        )
        return transcript.text
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return None

def format_constructions_preview(parsed: dict) -> str:
    if not parsed:
        return "Не удалось распознать конструкции."
    
    lines = []
    if parsed.get("object_name"):
        lines.append(f"🏗 <b>Объект:</b> {parsed['object_name']}")
    if parsed.get("block"):
        lines.append(f"🏢 <b>Блок:</b> {parsed['block']}")
    if parsed.get("floor"):
        lines.append(f"🏠 <b>Этаж:</b> {parsed['floor']}")
    
    shift_label = "☀️ Дневная" if parsed.get("shift_type") == "day" else "🌙 Ночная"
    lines.append(f"⏱ <b>Смена:</b> {shift_label}")
    lines.append("")
    
    constructions = parsed.get("constructions", [])
    total_m3 = 0
    for c in constructions:
        marks = ", ".join(c.get("marks", []))
        ctype = c.get("type", "—")
        m3 = c.get("concrete_plan_m3") or 0
        total_m3 += m3
        
        nature_icons = {"given": "✅", "not_given": "❌", "will_be_night": "🌙"}
        rebar_icons = {"accepted": "✅", "partial": "⚠️", "not_accepted": "❌"}
        
        nature = nature_icons.get(c.get("nature_status", ""), "❓")
        rebar = rebar_icons.get(c.get("rebar_status", ""), "❓")
        
        lines.append(f"<b>{ctype}</b> ({marks})")
        lines.append(f"  Натура: {nature} | Арматура: {rebar} | Бетон: {m3} м³")
        if c.get("concrete_method"):
            lines.append(f"  Подача: {c['concrete_method']}")
    
    if total_m3:
        lines.append(f"\n📊 <b>Итого бетона:</b> {total_m3} м³")
    
    return "\n".join(lines)
