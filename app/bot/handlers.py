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


async def animate_loading(message: types.Message, draft_id: int, stop_event: asyncio.Event):
    stages = ["🔍 Analyzing", "🧠 Matching conditions", "📚 Preparing response"]
    dot_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        while not stop_event.is_set():
            elapsed = asyncio.get_event_loop().time() - start_time
            # Progress through stages every 4 seconds
            stage_index = min(int(elapsed // 4), len(stages) - 1)
            
            dots = " •" * (dot_count % 4)
            text = f"<i>{stages[stage_index]}{dots}</i>"
            await message.send_chat_action(message.chat.id, ChatAction.TYPING)
            await message(SendMessageDraft(
                chat_id=message.chat.id,
                draft_id=draft_id,
                text=text,
                parse_mode=ParseMode.HTML
            ))

            dot_count += 1
            await asyncio.sleep(0.5)
            
    except Exception:
        pass


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Hello! I am your ICD-11 Grounded Medical Assistant. How can I help you today?", parse_mode=ParseMode.HTML)

    
@router.message()
async def handle_user_query(message: types.Message):
    if not medical_service._is_valid_query(message.text):
        await message.answer("<b>Hello!</b> Please describe your symptoms.", parse_mode=ParseMode.HTML)
        return

    draft_id = message.message_id
    stop_event = asyncio.Event()
    
    # Start the native draft animation
    anim_task = asyncio.create_task(
        animate_loading(message, draft_id, stop_event)
    )

    try:
        # Get response (handles its own internal API errors)
        response_text = await medical_service.get_grounded_response(message.text)
        
        stop_event.set()
        await anim_task

        # Success: Send final response
        await message.answer(response_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Handler error: {e}")
        stop_event.set()
        await anim_task
        await message.answer("<b>Wait a moment...</b>\nSomething went wrong. Please try rephrasing your concern.")