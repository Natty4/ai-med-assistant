# app/bot/handlers.py

import os
import asyncio
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.methods import SendMessageDraft
from aiogram.client.default import DefaultBotProperties

from src.utils.redis_client import redis_client
from src.synthesis.response_generator import ResponseGenerator

load_dotenv()

logger = logging.getLogger(__name__)

bot = Bot(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

medical_assistant = None


async def animate_loading(chat_id: int, draft_id: int, stop_event: asyncio.Event):
    stages = ["🔍 Analyzing", "🧠 Matching conditions", "📚 Preparing response"]
    stage_index = 0
    dot_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        while not stop_event.is_set():
            elapsed = asyncio.get_event_loop().time() - start_time
            stage_index = min(int(elapsed // 6), len(stages) - 1)
            dots = " •" * (dot_count % 4)
            text = f"{stages[stage_index]}{dots}"

            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await bot(SendMessageDraft(
                chat_id=chat_id,
                draft_id=draft_id,
                text=f"<i>{text}</i>",
                parse_mode=ParseMode.HTML
            ))
            dot_count += 1
            await asyncio.sleep(0.5)
    except Exception:
        pass


def build_initial_text(structured: dict) -> str:
    lines = [structured['summary'], "", structured['urgency_friendly'], ""]
    sections = structured["sections"]
    section_order = [
        ("overview", "Condition"), ("symptoms", "Symptoms"), ("causes", "Causes"),
        ("self_care", "Self-Care (Do's & Don'ts)"), ("treatment", "Treatment"),
        ("prevention", "Prevention"), ("lifestyle_tips", "Lifestyle Tips"),
        ("when_to_seek_help", "When to Seek Help"),
    ]
    for key, title in section_order:
        content = sections.get(key, []) if key != "overview" else [sections.get("overview", "")]
        if content:
            text_content = "\n".join(f"• {item}" for item in content if str(item).strip()) if isinstance(content, list) else str(content)
            if text_content.strip():
                lines.append(f"<blockquote expandable><b>{title}</b>\n\n{text_content}</blockquote>")
                lines.append("")
    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🩺 <b>Medical Assistant</b>\n\n"
        "Describe your symptoms clearly. I give information based on official sources.\n\n"
        "⚠️ Not for emergencies – call 991 if needed."
    )


@dp.message(F.text)
async def handle_medical_query(message: types.Message):
    user_id = message.from_user.id
    draft_id = message.message_id
    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_loading(message.chat.id, draft_id, stop_event))

    try:
        structured = await asyncio.to_thread(
            medical_assistant.generate_structured,
            message.text,
            user_id=user_id                     # ← Passing user_id
        )

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

        # Save session to Redis
        session_data = {
            "structured": structured,
            "chat_id": message.chat.id,
            "message_id": sent.message_id,
            "full_text": text,
            "user_id": user_id
        }
        await redis_client.save_session(structured["query_id"], session_data)

    except Exception as e:
        stop_event.set()
        logger.error(f"Error: {e}", exc_info=True)
        await bot(SendMessageDraft(chat_id=message.chat.id, draft_id=draft_id,
                                   text="⚠️ Something went wrong. Please try again."))


@dp.callback_query(F.data.startswith("show:images"))
async def handle_images_callback(callback: types.CallbackQuery):
    _, _, query_id = callback.data.split(":", 2)
    session = await redis_client.get_session(query_id)

    if not session:
        await callback.answer("Session expired.")
        return

    structured = session["structured"]
    chat_id = session["chat_id"]
    msg_id = session["message_id"]
    full_text = session["full_text"]

    images = structured["sections"].get("images", [])
    await callback.answer("📸 Sending images...")

    if images:
        for img in images[:3]:
            raw_caption = img.get("caption", "").strip()

            # Split by "•"
            parts = [p.strip() for p in raw_caption.split("•") if p.strip()]
            if len(parts) >= 2:
                caption = f"<b>{parts[0]}</b>\n\n<i>• {parts[1]}</i>"
            elif len(parts) == 1:
                caption = parts[0]
            else:
                caption = ""

            caption = caption[:300]

            await bot.send_photo(
                chat_id=chat_id,
                photo=img["url"],
                caption=caption,
                parse_mode=ParseMode.HTML
            )

        new_text = full_text + "\n\n✅ <b>Images sent below!</b>"
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=new_text,
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
    else:
        await callback.answer("No images available.")