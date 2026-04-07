# app/bot/main.py

import os
import sys
import uuid
import asyncio
import logging
from typing import Dict
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.methods import SendMessage, SendMessageDraft
from aiogram.client.default import DefaultBotProperties

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.synthesis.response_generator import ResponseGenerator

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

ResponseGenerator.initialize()
medical_assistant = ResponseGenerator()

session_store: Dict[str, dict] = {}



async def animate_loading(chat_id: int, draft_id: int, stop_event: asyncio.Event):
    """Hybrid animation: dots + stage switching based on time"""
    
    stages = [
        "🔍 Analyzing",
        "🧠 Matching conditions",
        "📚 Preparing response"
    ]
    
    stage_index = 0
    start_time = asyncio.get_event_loop().time()
    dot_count = 0

    try:
        while not stop_event.is_set():
            elapsed = asyncio.get_event_loop().time() - start_time

            # Change stage every 6 seconds
            stage_index = min(int(elapsed // 6), len(stages) - 1)

            # Animate dots (0 → 3 → repeat)
            dots = " •" * (dot_count % 4)
            text = f"{stages[stage_index]}{dots}"

            try:
                
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
                await bot(SendMessageDraft(
                    chat_id=chat_id,
                    draft_id=draft_id,
                    text=f"<i>{text}</i>",
                    parse_mode=ParseMode.HTML
                ))
            except Exception as e:
                logger.debug(f"Draft update failed: {e}")

            dot_count += 1
            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        pass
    
        
def build_initial_text(structured: dict) -> str:
    """Build rich message with all sections as expandable blockquotes"""
    lines = [
        structured['summary'],
        "",
        structured['urgency_friendly'],
        ""
    ]

    sections = structured["sections"]
    section_order = [
        ("overview", "Condition"),
        ("symptoms", "Symptoms"),
        ("causes", "Causes"),
        ("self_care", "Self-Care (Do's & Don'ts)"),
        ("treatment", "Treatment"),
        ("prevention", "Prevention"),
        ("lifestyle_tips", "Lifestyle Tips"),
        ("when_to_seek_help", "When to Seek Help"),
    ]

    for key, title in section_order:
        if key == "overview":
            content = sections.get("overview") or " ".join(sections.get("symptoms", [])[:6])
        else:
            items = sections.get(key, [])
            if not items:
                continue
            content = "\n".join(f"• {item}" for item in items if str(item).strip())

        if content and content.strip():
            lines.append(f"<blockquote expandable><b>{title}</b>\n\n{content}</blockquote>")
            lines.append("")

    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🩺 <b>Medical Assistant</b>\n\n"
        "Describe your symptoms clearly. I give information based on official NHS sources.\n\n"
        "⚠️ Not for emergencies – call 991 if needed."
    )


@dp.message(F.text)
async def handle_medical_query(message: types.Message):
    draft_id = message.message_id
    stop_event = asyncio.Event()

    # Start animation
    anim_task = asyncio.create_task(
        animate_loading(message.chat.id, draft_id, stop_event)
    )

    try:
        structured = await asyncio.to_thread(
            medical_assistant.generate_structured,
            message.text
        )

        # Stop animation
        stop_event.set()
        await anim_task

        text = build_initial_text(structured)

        keyboard = []
        if structured["sections"].get("images"):
            keyboard.append([types.InlineKeyboardButton(
                text="📸 View Images",
                callback_data=f"show:images:{structured['query_id']}"
            )])

        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

        sent = await message.answer(text, reply_markup=reply_markup)

        session_store[structured["query_id"]] = {
            "structured": structured,
            "chat_id": message.chat.id,
            "message_id": sent.message_id,
            "full_text": text
        }

    except Exception as e:
        stop_event.set()
        logger.error(f"Error: {e}", exc_info=True)

        await bot(SendMessageDraft(
            chat_id=message.chat.id,
            draft_id=draft_id,
            text="⚠️ Something went wrong. Please try again."
        ))

@dp.callback_query(F.data.startswith("show:images"))
async def handle_images_callback(callback: types.CallbackQuery):
    _, _, query_id = callback.data.split(":", 2)

    if query_id not in session_store:
        await callback.answer("Session expired.")
        return

    data = session_store[query_id]
    structured = data["structured"]
    chat_id = data["chat_id"]
    msg_id = data["message_id"]
    full_text = data["full_text"]   # Restore original rich text

    images = structured["sections"].get("images", [])
    await callback.answer("📸 Sending images...")

    if images:
        for img in images[:3]:
            raw_caption = img.get("caption", "").strip()

            # Split by "•"
            parts = [p.strip() for p in raw_caption.split("•") if p.strip()]

            # Format caption
            if len(parts) >= 2:
                caption = f"<b>{parts[0]}</b>\n\n<i>• {parts[1]}</i>"
            elif len(parts) == 1:
                caption = parts[0]
            else:
                caption = ""

            # Limit caption length (Telegram limit ~1024, you're using 200)
            caption = caption[:200]

            await bot.send_photo(
                chat_id=chat_id,
                photo=img["url"],
                caption=caption,
                parse_mode=ParseMode.HTML
            )

        # Edit message to remove button + add confirmation (keep blockquotes)
        new_text = full_text + "\n\n✅ <b>Images sent below!</b>"
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=new_text,
            parse_mode=ParseMode.HTML,
            reply_markup=None  # Remove the button
        )
    else:
        await callback.answer("No images available.")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Telegram Bot started – Expandable blockquotes + Smart Images button")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())