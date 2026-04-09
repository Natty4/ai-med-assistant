# app/bot/handlers.py

import json
import asyncio
import logging
from aiogram import Router, types
from aiogram.methods import SendMessageDraft
from aiogram.types import BufferedInputFile
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Filter, Command
from core.config import settings
from app.core.services import medical_service, redis_client

logger = logging.getLogger(__name__)
router = Router()

class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in settings.admin_list
    
    
async def animate_loading(bot, chat_id: int, draft_id: int, stop_event: asyncio.Event):
    stages = ["🔍 Analyzing", "🧠 Matching conditions", "📚 Preparing response"]
    dot_count = 0
    while not stop_event.is_set():
        text = f"<i>{stages[min(dot_count // 8, 2)]}{' •' * (dot_count % 4)}</i>"
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await bot(SendMessageDraft(chat_id=chat_id, draft_id=draft_id, text=text, parse_mode=ParseMode.HTML))
            dot_count += 1
            await asyncio.sleep(1.5)
        except Exception: break

@router.message(Command("stats"), IsAdmin())
async def cmd_stats(message: types.Message):
    """Gives a summary of Redis data usage."""
    # Get total keys
    all_keys = await redis_client.keys("*")
    cache_keys = [k for k in all_keys if k.startswith("icd_cache:")]
    session_keys = [k for k in all_keys if k.startswith("session:")]
    
    # Get top searched condition (from stats:condition_searches hash)
    top_searches = await redis_client.hgetall("stats:condition_searches")
    sorted_stats = sorted(top_searches.items(), key=lambda x: int(x[1]), reverse=True)[:5]
    
    stats_text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"🔑 Total Keys: {len(all_keys)}\n"
        f"🧠 Cached ICD Entities: {len(cache_keys)}\n"
        f"👥 Active User Sessions: {len(session_keys)}\n\n"
        "🔥 <b>Top Searches:</b>\n"
    )
    
    for term, count in sorted_stats:
        stats_text += f"• {term}: {count}\n"
        
    await message.answer(stats_text, parse_mode=ParseMode.HTML)

@router.message(Command("dump"), IsAdmin())
async def cmd_dump(message: types.Message):
    """Dumps all Redis data into a JSON file and sends it."""
    data_dump = {}
    
    # Iteratively fetch all keys (Safe for production)
    async for key in redis_client.scan_iter("*"):
        key_type = await redis_client.type(key)
        if key_type == "string":
            val = await redis_client.get(key)
            try: data_dump[key] = json.loads(val)
            except: data_dump[key] = val
        elif key_type == "hash":
            data_dump[key] = await redis_client.hgetall(key)
            
    # Convert to JSON and send as file
    json_str = json.dumps(data_dump, indent=2, ensure_ascii=False)
    file_content = BufferedInputFile(json_str.encode("utf-8"), filename="redis_dump.json")
    
    await message.answer_document(
        file_content, 
        caption="🔐 <b>Full Database Dump</b>\nGenerated successfully.",
        parse_mode=ParseMode.HTML
    )
    
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