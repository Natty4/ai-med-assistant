# app/bot/handlers.py

import json
import asyncio
import logging
from aiogram import Router, types
from aiogram.methods import SendMessageDraft
from aiogram.types import BufferedInputFile
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Filter, Command
from app.core.config import settings
from app.core.services import medical_service, redis_client

logger = logging.getLogger(__name__)
router = Router()

class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in settings.admin_list
    
    
async def animate_loading(bot, chat_id: int, stop_event: asyncio.Event):
    """
    Keeps the 'typing...' indicator active in the Telegram UI.
    Telegram auto-expires this after ~5 seconds, so we loop every 4 seconds.
    """
    try:
        while not stop_event.is_set():
            # Trigger the 'typing' action
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            for _ in range(40):
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Animation error: {e}")

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
    
@router.message(Command("ping_redis"), IsAdmin())
async def cmd_ping_redis(message: types.Message):
    start = asyncio.get_event_loop().time()
    try:
        await redis_client.ping()
        latency = (asyncio.get_event_loop().time() - start) * 1000
        await message.answer(f"🏓 <b>Redis Pong!</b>\nLatency: {latency:.2f}ms", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.answer(f"❌ <b>Redis Connection Failed</b>\nError: {str(e)}", parse_mode=ParseMode.HTML)

@router.message(Command("set"))
async def cmd_set_profile(message: types.Message):
    """
    Usage: /set age: 30, conditions: Asthma, Diabetes, meds: Albuterol
    """
    args = message.text.replace("/set", "").strip()
    if not args:
        await message.answer(
            "<b>How to set your profile:</b>\n"
            "Use the format: <code>/set key: value</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/set age: 29, conditions: Asthma, meds: Ventolin</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # Simple parsing logic
    new_data = {
        "demographics": {},
        "chronic_conditions": [],
        "medications": []
    }
    
    parts = args.split(",")
    for part in parts:
        if ":" in part:
            key, val = part.split(":", 1)
            key, val = key.strip().lower(), val.strip()
            
            if key in ["age", "weight", "gender"]:
                new_data["demographics"][key] = val
            elif key in ["conditions", "condition", "disease"]:
                new_data["chronic_conditions"].append(val)
            elif key in ["meds", "medications", "medicine"]:
                new_data["medications"].append(val)

    # Save to Redis via existing service method
    await medical_service.update_user_profile(message.from_user.id, new_data)
    
    await message.answer("✅ <b>Profile updated!</b>\nI will consider this information in our future conversations.", parse_mode=ParseMode.HTML)

@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    profile = await medical_service.get_user_profile(message.from_user.id)
    
    if not any(profile.values()):
        await message.answer("📝 Your profile is currently empty.")
        return

    # Format output for clarity
    res = ["<b>📋 Current Medical Context:</b>\n"]
    
    if profile.get("demographics"):
        res.append(f"👤 <b>Bio:</b> {', '.join([f'{k}: {v}' for k, v in profile['demographics'].items()])}")
    
    if profile.get("chronic_conditions"):
        res.append(f"🏥 <b>Conditions:</b> {', '.join(profile['chronic_conditions'])}")
        
    if profile.get("medications"):
        res.append(f"💊 <b>Medications:</b> {', '.join(profile['medications'])}")

    res.append("\n<i>This info anonymized and shared with the AI to personalize your health insights.</i>")
    
    await message.answer("\n".join(res), parse_mode=ParseMode.HTML)
  
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🩺 <b>Medical Assistant</b>\nHow can I help you today?", parse_mode=ParseMode.HTML)
        

@router.message()
async def handle_user_query(message: types.Message):
    is_valid = await medical_service.is_meaningful_input(message.text, user_id)
    
    if not is_valid:
        await message.answer("<b>I'm listening.</b>\nPlease describe your symptoms or answer the previous question.", parse_mode=ParseMode.HTML)
        return
    
    user_id = message.from_user.id
    session_key = f"session:{user_id}"
    clean_term = medical_service._clean_query(message.text)
    
    await asyncio.gather(
        redis_client.hincrby("stats:condition_searches", clean_term, 1),
        redis_client.hset(session_key, mapping={
            "last_query": message.text, 
            "username": message.from_user.username or "unknown"
        }),
        redis_client.hincrby(session_key, "total_requests", 1)
    )

    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_loading(message.bot, message.chat.id, stop_event))
    try:
        response_text = await medical_service.get_grounded_response(message.text, user_id)
        stop_event.set()
        await anim_task
        await message.answer(response_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Handler error: {e}")
        stop_event.set()
        await anim_task
        await message.answer("⚠️ <b>Error:</b> I couldn't process that request. Please try again.", parse_mode=ParseMode.HTML)
        
        