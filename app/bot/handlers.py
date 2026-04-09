# app/bot/handlers.py

import asyncio
import logging
from aiogram import Router, types
from aiogram.methods import SendMessageDraft
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Command
from app.core.services import medical_service, redis_client

logger = logging.getLogger(__name__)
router = Router()

async def animate_loading(bot, chat_id: int, draft_id: int, stop_event: asyncio.Event):
    stages = ["🔍 Analyzing", "🧠 Matching conditions", "📚 Preparing response"]
    dot_count = 0
    while not stop_event.is_set():
        text = f"<i>{stages[min(dot_count // 8, 2)]}{' •' * (dot_count % 4)}</i>"
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await bot(SendMessageDraft(chat_id=chat_id, draft_id=draft_id, text=text, parse_mode=ParseMode.HTML))
            dot_count += 1
            await asyncio.sleep(0.5)
        except Exception: break

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🩺 <b>Medical Assistant</b>\nHow can I help you today?", parse_mode=ParseMode.HTML)

@router.message()
async def handle_user_query(message: types.Message):
    if not medical_service._is_valid_query(message.text):
        await message.answer("<b>Hello!</b>\nPlease describe your symptoms briefly.", parse_mode=ParseMode.HTML)
        return

    # Session Storage: Track last query and increment total user requests
    user_id = message.from_user.id
    session_key = f"session:{user_id}"
    await redis_client.hset(session_key, mapping={"last_query": message.text, "username": message.from_user.username or "unknown"})
    await redis_client.hincrby(session_key, "total_requests", 1)

    bot, chat_id, draft_id = message.bot, message.chat.id, message.message_id 
    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_loading(bot, chat_id, draft_id, stop_event))

    try:
        response_text = await medical_service.get_grounded_response(message.text)
        stop_event.set()
        await anim_task
        await message.answer(response_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Handler error: {e}")
        stop_event.set()
        await anim_task
        await message.answer("⚠️ Error processing request.", parse_mode=ParseMode.HTML)