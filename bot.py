import asyncio
import random
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
import aiosqlite

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8717213060:AAHm_up8kch9cqpIR__llEqG-kGe2THeII0"  # Вставь сюда свой токен!
INACTIVE_HOURS = 3  # Часов неактивности для отправки музыки

# Пути к папкам с музыкой (создай их в папке с ботом)
MUSIC_SWEAR = "music/swear"      # Папка с треками на мат
MUSIC_MORNING = "music/morning"  # Папка с треками на доброе утро
MUSIC_HELLO = "music/hello"      # Папка с треками на привет
MUSIC_WAKE = "music/wake"        # Папка с треками для оживления чата

# ========== СПИСКИ КЛЮЧЕВЫХ СЛОВ ==========
SWEAR_WORDS = ["бля", "хуй", "пизда", "еба", "залупа", "мудак", "говно", "сука", "пидор", "нахер", "нахуй", "похуй"]
MORNING_WORDS = ["доброе утро", "с добрым утром", "morning"]
HELLO_WORDS = ["привет", "здарова", "hello", "ку", "прив"]

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_path = "bot_session.db"

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
async def init_db():
    """Создание таблицы в БД"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS last_activity (
                chat_id INTEGER PRIMARY KEY,
                last_message_time TEXT
            )
        ''')
        await db.commit()

async def update_activity(chat_id: int):
    """Обновление времени последнего сообщения в чате"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "REPLACE INTO last_activity (chat_id, last_message_time) VALUES (?, ?)",
            (chat_id, datetime.now().isoformat())
        )
        await db.commit()

async def get_last_activity(chat_id: int):
    """Получение времени последнего сообщения"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT last_message_time FROM last_activity WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return datetime.fromisoformat(row[0])
            return None

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С МУЗЫКОЙ ==========
def get_random_music(folder_path: str):
    """Возвращает случайный аудиофайл из папки"""
    if not os.path.exists(folder_path):
        print(f"Папка не найдена: {folder_path}")
        return None
    
    music_files = [f for f in os.listdir(folder_path) 
                   if f.endswith(('.mp3', '.wav', '.ogg', '.m4a'))]
    
    if not music_files:
        print(f"В папке {folder_path} нет музыки!")
        return None
    
    random_file = random.choice(music_files)
    return FSInputFile(os.path.join(folder_path, random_file))

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========
def contains_swear(text: str) -> bool:
    """Проверка наличия мата в тексте"""
    text_lower = text.lower()
    for word in SWEAR_WORDS:
        if word in text_lower:
            return True
    return False

def contains_morning(text: str) -> bool:
    """Проверка на доброе утро"""
    text_lower = text.lower()
    for phrase in MORNING_WORDS:
        if phrase in text_lower:
            return True
    return False

def contains_hello(text: str) -> bool:
    """Проверка на приветствие"""
    text_lower = text.lower()
    for word in HELLO_WORDS:
        if word in text_lower:
            return True
    return False

# ========== ПРОВЕРКА НЕАКТИВНОСТИ (ЗАДАЧА В ФОНЕ) ==========
async def check_inactive_chats():
    """Фоновая задача: проверяет чаты на неактивность"""
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту
        
        try:
            async with aiosqlite.connect(db_path) as db:
                # Получаем все чаты
                async with db.execute("SELECT chat_id, last_message_time FROM last_activity") as cursor:
                    rows = await cursor.fetchall()
                    
                    for chat_id, last_time_str in rows:
                        last_time = datetime.fromisoformat(last_time_str)
                        now = datetime.now()
                        
                        # Если прошло больше INACTIVE_HOURS часов
                        if now - last_time > timedelta(hours=INACTIVE_HOURS):
                            # Отправляем музыку для оживления
                            music_file = get_random_music(MUSIC_WAKE)
                            if music_file:
                                try:
                                    await bot.send_audio(
                                        chat_id=chat_id,
                                        audio=music_file,
                                        caption="🔊 Эй, чат! 3 часа тишины... Включаем музыку!"
                                    )
                                    # Обновляем время, чтобы не спамить
                                    await update_activity(chat_id)
                                except Exception as e:
                                    print(f"Ошибка отправки в чат {chat_id}: {e}")
        except Exception as e:
            print(f"Ошибка в check_inactive_chats: {e}")

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("🎵 Привет! Я музыкальный бот!\n"
                        "Я реагирую на:\n"
                        "• Мат → отправлю трек 🚫\n"
                        "• Доброе утро → отправлю трек ☀️\n"
                        "• Привет → отправлю трек 👋\n"
                        "• Если 3 часа тишины → разбужу чат музыкой 🔈")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer("📖 Как настроить музыку:\n"
                        "1. Создай папки:\n"
                        f"   - {MUSIC_SWEAR}\n"
                        f"   - {MUSIC_MORNING}\n"
                        f"   - {MUSIC_HELLO}\n"
                        f"   - {MUSIC_WAKE}\n"
                        "2. Положи туда .mp3 файлы\n"
                        "3. Бот будет их рандомно отправлять!\n\n"
                        f"Сейчас неактивность: {INACTIVE_HOURS} часа")

# ========== ОБРАБОТКА СООБЩЕНИЙ В ЧАТЕ ==========
@dp.message()
async def handle_message(message: types.Message):
    # Игнорируем сообщения от ботов и команды
    if message.from_user.is_bot:
        return
    
    chat_id = message.chat.id
    text = message.text.lower() if message.text else ""
    
    # Обновляем время активности чата
    await update_activity(chat_id)
    
    # Проверяем мат (приоритет 1)
    if contains_swear(text):
        music = get_random_music(MUSIC_SWEAR)
        if music:
            await message.answer("🤬 Ай-яй-яй, не ругайся! Лучше послушай:")
            await bot.send_audio(chat_id=chat_id, audio=music)
        else:
            await message.answer("🤬 Не ругайся, пожалуйста! (музыки пока нет в папке)")
        return
    
    # Проверяем доброе утро
    if contains_morning(text):
        music = get_random_music(MUSIC_MORNING)
        if music:
            await bot.send_audio(chat_id=chat_id, audio=music, caption="☀️ Доброе утро! Твой плейлист:")
        else:
            await message.answer("☀️ Доброе утро! (скоро добавлю музыку)")
        return
    
    # Проверяем приветствие
    if contains_hello(text):
        music = get_random_music(MUSIC_HELLO)
        if music:
            await bot.send_audio(chat_id=chat_id, audio=music, caption="👋 Привет-привет! Держи трек:")
        else:
            await message.answer("👋 Привет! (скоро добавлю музыку в папку)")
        return

# ========== ЗАПУСК БОТА ==========
async def main():
    print("Бот запускается...")
    
    # Создаём папки для музыки, если их нет
    for folder in [MUSIC_SWEAR, MUSIC_MORNING, MUSIC_HELLO, MUSIC_WAKE]:
        os.makedirs(folder, exist_ok=True)
        print(f"Папка готова: {folder}")
    
    # Инициализируем БД
    await init_db()
    print("База данных готова")
    
    # Запускаем фоновую задачу проверки неактивности
    asyncio.create_task(check_inactive_chats())
    
    # Запускаем бота
    print("Бот запущен! Жду сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
