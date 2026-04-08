# app/bot/handlers.py

from aiogram import Router, types
from aiogram.filters import Command
from app.core.services import medical_service

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Hello! I am your ICD-11 Grounded Medical Assistant. How can I help you today?")

@router.message()
async def handle_user_query(message: types.Message):
    # Visual feedback: 'typing...'
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    response_text = await medical_service.get_grounded_response(message.text)
    await message.answer(response_text)