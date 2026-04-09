# app/bot/handlers.py

import asyncio
import random
import logging
from aiogram import Router, types
from aiogram.methods import SendMessageDraft
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Command
from app.core.services import medical_service

logger = logging.getLogger(__name__)

router = Router()


async def animate_loading(bot, chat_id: int, draft_id: int, stop_event: asyncio.Event):
    stages = ["🔍 Analyzing", "🧠 Matching conditions", "📚 Preparing response"]
    dot_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        while not stop_event.is_set():
            elapsed = asyncio.get_event_loop().time() - start_time
            stage_index = min(int(elapsed // 4), len(stages) - 1)

            dots = " •" * (dot_count % 4)
            text = f"<i>{stages[stage_index]}{dots}</i>"

            await bot.send_chat_action(chat_id, ChatAction.TYPING)

            await bot(SendMessageDraft(
                chat_id=chat_id,
                draft_id=draft_id,
                text=text,
                parse_mode=ParseMode.HTML
            ))

            dot_count += 1
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.warning(f"Animation stopped: {e}")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🩺 <b>Medical Assistant</b>\n\n"
                         "Hello! I am your Medical Assistant." 
                         "How can I help you today?", 
                         parse_mode=ParseMode.HTML
        )

    

@router.message()
async def handle_user_query(message: types.Message):
    if not medical_service._is_valid_query(message.text):
        await message.answer(
            "<b>Hello!</b>\n\nPlease describe your symptoms briefly.",
            parse_mode=ParseMode.HTML
        )
        return

    bot = message.bot
    chat_id = message.chat.id
    
    draft_id = message.message_id 
    stop_event = asyncio.Event()

    anim_task = asyncio.create_task(
        animate_loading(bot, chat_id, draft_id, stop_event)
    )

    try:
        # Get the actual response from your service
        response_text = await medical_service.get_grounded_response(message.text)
        # Stop the animation
        stop_event.set()
        await anim_task
        await message.answer(response_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Handler error: {e}")
        stop_event.set()
        await anim_task
        await message.answer(
            "<b>Wait a moment...</b>" 
            "Something went wrong. Please try again later.",
            parse_mode=ParseMode.HTML
            )