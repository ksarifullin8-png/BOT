import asyncio
import logging
import os
import random
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam, InputReportReasonViolence,
    InputReportReasonPornography, InputReportReasonOther,
    InputReportReasonChildAbuse, InputReportReasonIllegalDrugs,
    InputReportReasonPersonalDetails
)
from config import *
from database import Database
from crypto_api import CryptoBotAPI

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PremiumReportBot:
    def __init__(self):
        self.bot_client = None
        self.session_clients = []  # Загруженные сессии из папки session
        self.db = Database()
        self.crypto = CryptoBotAPI(CRYPTOBOT_TOKEN)
        self.user_states = {}
        
        # Маппинг причин на типы Telethon
        self.reason_mapping = {
            "spam": InputReportReasonSpam(),
            "personal": InputReportReasonPersonalDetails(),
            "violence": InputReportReasonViolence(),
            "drugs": InputReportReasonIllegalDrugs(),
            "child": InputReportReasonChildAbuse(),
            "porn": InputReportReasonPornography(),
            "other": InputReportReasonOther()
        }
    
    async def load_sessions(self):
        """Загрузка всех .session файлов из папки session (БЕЗ API ID/HASH)"""
        if not os.path.exists(SESSIONS_FOLDER):
            os.makedirs(SESSIONS_FOLDER)
            logger.warning(f"📁 Создана папка {SESSIONS_FOLDER}, положите в нее .session файлы")
            return []
        
        # Ищем все .session файлы
        session_files = [f for f in os.listdir(SESSIONS_FOLDER) if f.endswith('.session')]
        loaded = []
        
        logger.info(f"🔍 Найдено .session файлов: {len(session_files)}")
        
        for session_file in session_files:
            try:
                # Путь к файлу сессии (без расширения .session)
                session_path = os.path.join(SESSIONS_FOLDER, session_file.replace('.session', ''))
                
                # Создаем клиента БЕЗ передачи api_id и api_hash
                # Telethon сам прочитает их из существующего .session файла
                client = TelegramClient(session_path, None, None)
                
                # Подключаемся
                await client.connect()
                
                # Проверяем, авторизована ли сессия
                if await client.is_user_authorized():
                    me = await client.get_me()
                    loaded.append({
                        'client': client,
                        'name': session_file,
                        'user_id': me.id,
                        'phone': me.phone if me.phone else 'Unknown',
                        'username': me.username if me.username else 'NoUsername'
                    })
                    logger.info(f"✅ Загружена сессия: {session_file} (@{me.username})")
                else:
                    logger.warning(f"❌ Сессия не авторизована: {session_file}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {session_file}: {e}")
        
        self.session_clients = loaded
        logger.info(f"✅ Загружено активных сессий: {len(loaded)}")
        return loaded
    
    async def check_user_access(self, user_id):
        """Проверка доступа пользователя"""
        
        # Проверяем, является ли пользователь администратором
        if user_id in ADMIN_IDS or self.db.is_admin(user_id):
            return {
                'access': True, 
                'type': 'admin', 
                'limit': 999999,
                'used': 0,
                'is_admin': True
            }
        
        # Проверка платной подписки
        sub = self.db.check_subscription(user_id)
        if sub:
            limit = SUBSCRIPTION_LIMITS.get(sub['type'], 0)
            if sub['reports_used'] < limit:
                return {
                    'access': True,
                    'type': sub['type'],
                    'limit': limit,
                    'used': sub['reports_used'],
                    'end_date': sub['end_date'],
                    'is_admin': False
                }
            else:
                return {
                    'access': False,
                    'reason': 'Лимит исчерпан',
                    'limit': limit,
                    'used': sub['reports_used']
                }
        
        return {'access': False, 'reason': 'Нет подписки'}
    
    async def start_bot(self):
        """Запуск бота"""
        # Загружаем сессии из папки session
        sessions = await self.load_sessions()
        
        # Создаем клиента бота
        self.bot_client = TelegramClient('bot_session', None, None)
        await self.bot_client.start(bot_token=BOT_TOKEN)
        
        logger.info(f"🚀 Бот запущен! Активных сессий для жалоб: {len(sessions)}")
        
        # Отправляем уведомление админам о запуске
        for admin_id in ADMIN_IDS:
            try:
                await self.bot_client.send_message(
                    admin_id,
                    f"✅ <b>Бот запущен!</b>\n\n"
                    f"📊 Загружено сессий: {len(sessions)}\n"
                    f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode='html'
                )
            except:
                pass
        
        # Регистрируем обработчики
        self.register_handlers()
        
        await self.bot_client.run_until_disconnected()
    
    def register_handlers(self):
        """Регистрация всех обработчиков"""
        
        @self.bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = event.sender_id
            username = event.sender.username or "NoUsername"
            
            # Добавляем пользователя в БД
            self.db.add_user(user_id, username)
            
            # Проверяем доступ
            access = await self.check_user_access(user_id)
            
            if access['access']:
                await self.show_main_menu(event, access)
            else:
                await self.show_subscription_menu(event)
        
        @self.bot_client.on(events.NewMessage(pattern='/admin'))
        async def admin_handler(event):
            if not self.db.is_admin(event.sender_id) and event.sender_id not in ADMIN_IDS:
                await event.reply("❌ У вас нет прав администратора!")
                return
            await self.show_admin_panel(event)
        
        @self.bot_client.on(events.NewMessage(pattern='/profile'))
        async def profile_handler(event):
            user_id = event.sender_id
            user = self.db.get_user(user_id)
            access = await self.check_user_access(user_id)
            
            if user:
                text = f"""
👤 <b>Ваш профиль</b>

📊 <b>Статистика:</b>
• Всего жалоб: {user[5] or 0}
• Дата регистрации: {user[6][:10] if user[6] else 'Неизвестно'}

"""
                if access['access']:
                    if access.get('is_admin'):
                        text += f"👑 <b>Статус:</b> Администратор"
                    else:
                        text += f"""
💎 <b>Подписка:</b>
• Тип: {access['type']}
• Действует до: {access['end_date'].strftime('%d.%m.%Y %H:%M')}
• Использовано: {access['used']}/{access['limit']}
"""
                else:
                    text += "\n❌ <b>У вас нет активной подписки</b>"
                
                await event.reply(text, parse_mode='html', buttons=[
                    [Button.inline("💎 Купить подписку", data="buy_subscription")],
                    [Button.inline("◀️ Главное меню", data="main_menu")]
                ])
        
        @self.bot_client.on(events.CallbackQuery)
        async def callback_handler(event):
            data = event.data.decode('utf-8')
            user_id = event.sender_id
            
            if data == "main_menu":
                access = await self.check_user_access(user_id)
                await self.show_main_menu(event, access, edit=True)
            
            elif data == "buy_subscription":
                await self.show_subscription_plans(event)
            
            elif data.startswith("buy_plan_"):
                plan = data.replace("buy_plan_", "")
                await self.create_payment_check(event, plan)
            
            elif data.startswith("check_payment_"):
                check_id = data.replace("check_payment_", "")
                await self.check_payment_result(event, check_id)
            
            elif data.startswith("report_"):
                access = await self.check_user_access(user_id)
                if not access['access']:
                    await event.answer("❌ У вас нет активной подписки!", alert=True)
                    return
                
                report_type = data.replace("report_", "")
                await self.show_report_reasons(event, report_type)
            
            elif data.startswith("reason_"):
                await self.handle_reason_selection(event)
            
            elif data == "admin_panel":
                if not self.db.is_admin(user_id) and user_id not in ADMIN_IDS:
                    await event.answer("❌ У вас нет прав!", alert=True)
                    return
                await self.show_admin_panel(event)
            
            elif data == "admin_list_users":
                if not self.db.is_admin(user_id) and user_id not in ADMIN_IDS:
                    return
                await self.show_users_list(event)
            
            elif data == "admin_stats":
                if not self.db.is_admin(user_id) and user_id not in ADMIN_IDS:
                    return
                await self.show_admin_stats(event)
            
            elif data == "admin_actions":
                if not self.db.is_admin(user_id) and user_id not in ADMIN_IDS:
                    return
                await self.show_admin_actions(event)
    
    async def show_main_menu(self, event, access, edit=False):
        """Главное меню"""
        sessions_count = len(self.session_clients)
        
        menu_text = f"""
🤖 <b>PREMIUM REPORT BOT</b>

{'👑' if access.get('is_admin') else '💎' if access['access'] else '❌'} <b>Статус:</b> {
    'Администратор' if access.get('is_admin') else 
    f'Premium ({access["type"]})' if access['access'] else 
    'Бесплатный'
}

📊 <b>Активных сессий:</b> {sessions_count}
📈 <b>Отправлено жалоб:</b> {access.get('used', 0)}/{access.get('limit', 0)}

<b>Выберите тип жалобы:</b>
"""
        buttons = [
            [Button.inline("👤 На пользователя", data="report_user"),
             Button.inline("📢 На канал", data="report_channel")],
            [Button.inline("🤖 На бота", data="report_bot"),
             Button.inline("💬 На чат", data="report_chat")],
            [Button.inline("👤 Профиль", data="profile"),
             Button.inline("💎 Подписка", data="buy_subscription")]
        ]
        
        # Добавляем кнопку админ-панели для админов
        if access.get('is_admin'):
            buttons.append([Button.inline("👑 Админ панель", data="admin_panel")])
        
        if edit:
            await event.edit(menu_text, buttons=buttons, parse_mode='html')
        else:
            await event.reply(menu_text, buttons=buttons, parse_mode='html')
    
    async def show_subscription_menu(self, event):
        """Меню подписки для новых пользователей"""
        text = """
❌ <b>У вас нет доступа к боту</b>

Для использования бота необходимо приобрести подписку:

<b>Доступные тарифы:</b>
• 1 день - 100 жалоб - 2$
• 3 дня - 350 жалоб - 5$  
• 7 дней - 1000 жалоб - 10$
• 30 дней - 5000 жалоб - 30$

<i>Оплата через CryptoBot (USDT, BTC, TON)</i>
"""
        buttons = [
            [Button.inline("💎 Купить подписку", data="buy_subscription")],
            [Button.url("📱 Поддержка", "https://t.me/support")]
        ]
        
        await event.reply(text, buttons=buttons, parse_mode='html')
    
    async def show_subscription_plans(self, event):
        """Показ тарифов подписки"""
        plans_text = """
💎 <b>Выберите тариф подписки:</b>

<b>Тарифы:</b>
• 🌟 1 день - 100 жалоб - 2$
• 🌟🌟 3 дня - 350 жалоб - 5$
• 🌟🌟🌟 7 дней - 1000 жалоб - 10$
• 💎 30 дней - 5000 жалоб - 30$

<i>✅ Мгновенная активация после оплаты</i>
"""
        buttons = [
            [Button.inline("🌟 1 день - 2$", data="buy_plan_1_day")],
            [Button.inline("🌟🌟 3 дня - 5$", data="buy_plan_3_days")],
            [Button.inline("🌟🌟🌟 7 дней - 10$", data="buy_plan_7_days")],
            [Button.inline("💎 30 дней - 30$", data="buy_plan_30_days")],
            [Button.inline("◀️ Назад", data="main_menu")]
        ]
        
        await event.edit(plans_text, buttons=buttons, parse_mode='html')
    
    async def create_payment_check(self, event, plan):
        """Создание чека для оплаты"""
        price = SUBSCRIPTION_PRICES.get(plan, 0)
        days = int(plan.split('_')[0])
        
        await event.edit(
            f"🔄 <b>Создание чека...</b>\n\n"
            f"Тариф: {days} дней\n"
            f"Сумма: {price}$",
            parse_mode='html'
        )
        
        try:
            check = await self.crypto.create_check(
                amount=price,
                currency="USD",
                description=f"Подписка ReportBot на {days} дней"
            )
            
            if check:
                check_url = check.get('pay_url')
                check_id = check.get('check_id')
                
                self.db.add_transaction(check_id, event.sender_id, price, "USD", plan)
                
                await event.edit(
                    f"✅ <b>Чек создан!</b>\n\n"
                    f"💰 Сумма: {price}$\n"
                    f"📅 Тариф: {days} дней\n\n"
                    f"Для оплаты нажмите кнопку ниже:",
                    buttons=[
                        [Button.url("💳 Перейти к оплате", check_url)],
                        [Button.inline("✅ Я оплатил", data=f"check_payment_{check_id}")],
                        [Button.inline("◀️ Назад", data="buy_subscription")]
                    ],
                    parse_mode='html'
                )
                
                asyncio.create_task(self.check_payment_status(check_id, event.sender_id, plan, days))
            else:
                await event.edit(
                    "❌ <b>Ошибка создания чека</b>",
                    buttons=[[Button.inline("◀️ Назад", data="buy_subscription")]],
                    parse_mode='html'
                )
        except Exception as e:
            await event.edit(
                f"❌ <b>Ошибка:</b> {str(e)}",
                buttons=[[Button.inline("◀️ Назад", data="buy_subscription")]],
                parse_mode='html'
            )
    
    async def check_payment_status(self, check_id, user_id, plan, days):
        """Проверка статуса оплаты"""
        for _ in range(30):
            await asyncio.sleep(10)
            try:
                status = await self.crypto.check_payment_status(check_id)
                if status and status.get('status') == 'paid':
                    self.db.update_subscription(user_id, plan, days)
                    self.db.update_transaction(check_id, 'paid')
                    
                    try:
                        await self.bot_client.send_message(
                            user_id,
                            f"✅ <b>Оплата получена!</b>\n\n"
                            f"Ваша подписка на {days} дней активирована!",
                            parse_mode='html'
                        )
                    except:
                        pass
                    break
            except:
                continue
    
    async def check_payment_result(self, event, check_id):
        """Проверка результата оплаты по кнопке"""
        status = await self.crypto.check_payment_status(check_id)
        if status and status.get('status') == 'paid':
            await event.edit(
                "✅ <b>Оплата подтверждена!</b>\n\nИспользуйте /start для начала работы",
                buttons=[[Button.inline("🏠 Главное меню", data="main_menu")]],
                parse_mode='html'
            )
        else:
            await event.answer("❌ Оплата не найдена или еще не подтверждена", alert=True)
    
    async def show_report_reasons(self, event, report_type):
        """Показ причин для жалобы"""
        reasons_text = f"📝 <b>Выберите причину жалобы на {report_type}:</b>\n\n"
        
        for key, reason in REPORT_REASONS.items():
            reasons_text += f"• {reason['name']} - {reason['desc']}\n"
        
        buttons = []
        row = []
        
        for key, reason in REPORT_REASONS.items():
            row.append(Button.inline(reason['name'], data=f"reason_{report_type}_{key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([Button.inline("◀️ Назад", data="main_menu")])
        
        await event.edit(reasons_text, buttons=buttons, parse_mode='html')
    
    async def handle_reason_selection(self, event):
        """Обработка выбора причины"""
        data = event.data.decode('utf-8')
        parts = data.split('_')
        report_type = parts[1]
        reason = parts[2]
        
        self.user_states[event.sender_id] = {
            'step': 'waiting_target',
            'report_type': report_type,
            'reason': reason
        }
        
        prompts = {
            'user': "👤 Введите username пользователя (например: @username):",
            'channel': "📢 Введите ссылку на канал (например: @channel или https://t.me/channel):",
            'bot': "🤖 Введите username бота (например: @botusername):",
            'chat': "💬 Введите ссылку на чат:"
        }
        
        await event.edit(
            prompts.get(report_type, "Введите цель жалобы:"),
            buttons=[[Button.inline("◀️ Отмена", data="main_menu")]],
            parse_mode='html'
        )
    
    @self.bot_client.on(events.NewMessage)
    async def handle_report_input(self, event):
        """Обработка ввода цели жалобы"""
        if event.sender_id not in self.user_states:
            return
        
        state = self.user_states[event.sender_id]
        
        if state['step'] == 'waiting_target':
            target = event.message.text.strip()
            state['target'] = target
            state['step'] = 'waiting_evidence'
            
            await event.reply(
                "📎 Отправьте ссылку на доказательство (или отправьте '-' если нет):",
                buttons=[[Button.inline("◀️ Отмена", data="main_menu")]]
            )
        
        elif state['step'] == 'waiting_evidence':
            evidence = event.message.text.strip()
            if evidence == '-':
                evidence = None
            
            await self.send_reports(event, state, evidence)
            del self.user_states[event.sender_id]
    
    async def send_reports(self, event, state, evidence):
        """Отправка жалоб через все сессии"""
        if not self.session_clients:
            await event.reply("❌ Нет активных сессий для отправки жалоб!")
            return
        
        await event.reply(
            f"🔄 <b>Начинаю отправку жалоб...</b>\n"
            f"Используется сессий: {len(self.session_clients)}",
            parse_mode='html'
        )
        
        report_type = state['report_type']
        target = state['target']
        reason_key = state['reason']
        
        reason_info = REPORT_REASONS.get(reason_key, REPORT_REASONS['other'])
        reason = self.reason_mapping.get(reason_key, InputReportReasonOther())
        
        report_text = f"Жалоба на {report_type} {target}. Причина: {reason_info['name']}"
        if evidence:
            report_text += f"\nДоказательства: {evidence}"
        
        success = 0
        failed = 0
        errors = []
        
        for session_data in self.session_clients:
            try:
                client = session_data['client']
                
                try:
                    entity = await client.get_entity(target)
                except Exception as e:
                    failed += 1
                    errors.append(f"{session_data['name']}: Не найден пользователь")
                    continue
                
                await client(ReportRequest(
                    peer=entity,
                    id=[entity.id],
                    reason=reason,
                    message=report_text
                ))
                
                success += 1
                self.db.increment_reports(event.sender_id)
                await asyncio.sleep(random.uniform(2, 5))
                
            except Exception as e:
                failed += 1
                errors.append(f"{session_data['name']}: {str(e)[:50]}")
        
        result_text = f"""
✅ <b>Жалобы отправлены!</b>

🎯 Тип: {report_type}
👤 Цель: {target}
📝 Причина: {reason_info['name']}

📊 <b>Результат:</b>
• Успешно: {success}
• Ошибок: {failed}
• Всего сессий: {len(self.session_clients)}
"""
        
        if errors and len(errors) <= 3:
            result_text += "\n<b>Ошибки:</b>\n" + "\n".join(errors[:3])
        
        await event.reply(result_text, parse_mode='html', buttons=[
            [Button.inline("📊 Еще жалоба", data=f"report_{report_type}"),
             Button.inline("🏠 Главное меню", data="main_menu")]
        ])
    
    async def show_admin_panel(self, event):
        """Панель администратора"""
        stats = self.db.get_admin_stats()
        
        text = f"""
👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>

📊 <b>Статистика:</b>
• Всего пользователей: {stats['total_users']}
• Активных подписок: {stats['active_subs']}
• Всего жалоб: {stats['total_reports']}
• Доход: {stats['total_revenue']:.2f}$

<b>Подписки по типам:</b>
• 1 день: {stats['subscriptions']['1_day']}
• 3 дня: {stats['subscriptions']['3_days']}  
• 7 дней: {stats['subscriptions']['7_days']}
• 30 дней: {stats['subscriptions']['30_days']}

<b>Активных сессий:</b> {len(self.session_clients)}
"""
        buttons = [
            [Button.inline("📋 Список пользователей", data="admin_list_users")],
            [Button.inline("📊 Детальная статистика", data="admin_stats")],
            [Button.inline("📜 История действий", data="admin_actions")],
            [Button.inline("◀️ Назад", data="main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='html')
    
    async def show_users_list(self, event):
        """Список пользователей"""
        users = self.db.get_all_users(limit=10)
        
        text = "📋 <b>Последние 10 пользователей:</b>\n\n"
        
        for user in users:
            user_id, username, sub_type, sub_end, used, total, joined, last = user
            status = "✅" if sub_end and datetime.fromisoformat(sub_end) > datetime.now() else "❌"
            text += f"{status} <b>{username}</b> (ID: {user_id})\n"
            text += f"   📅 Регистрация: {joined[:10]}\n"
            text += f"   📊 Жалоб: {total}\n\n"
        
        buttons = [[Button.inline("◀️ Назад", data="admin_panel")]]
        await event.edit(text, buttons=buttons, parse_mode='html')
    
    async def show_admin_stats(self, event):
        """Детальная статистика"""
        stats = self.db.get_admin_stats()
        
        # Статистика по сессиям
        sessions_text = "\n<b>Активные сессии:</b>\n"
        for s in self.session_clients:
            sessions_text += f"• @{s['username']} ({s['phone']})\n"
        
        text = f"""
📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>

👥 <b>Пользователи:</b>
• Всего: {stats['total_users']}
• С подпиской: {stats['active_subs']}

💎 <b>Подписки:</b>
• 1 день: {stats['subscriptions']['1_day']}
• 3 дня: {stats['subscriptions']['3_days']}
• 7 дней: {stats['subscriptions']['7_days']}
• 30 дней: {stats['subscriptions']['30_days']}

💰 <b>Доход:</b>
• Всего: {stats['total_revenue']:.2f}$

📊 <b>Активность:</b>
• Всего жалоб: {stats['total_reports']}
{sessions_text}
"""
        buttons = [[Button.inline("◀️ Назад", data="admin_panel")]]
        await event.edit(text, buttons=buttons, parse_mode='html')
    
    async def show_admin_actions(self, event):
        """История действий админов"""
        actions = self.db.get_admin_actions(limit=10)
        
        text = "📜 <b>Последние действия:</b>\n\n"
        
        for action in actions:
            admin_id, action_type, target, details, created = action
            text += f"• [{created[11:16]}] {action_type}\n"
            text += f"  Админ: {admin_id}\n"
            text += f"  Цель: {target}\n"
            text += f"  Детали: {details}\n\n"
        
        buttons = [[Button.inline("◀️ Назад", data="admin_panel")]]
        await event.edit(text, buttons=buttons, parse_mode='html')

async def main():
    bot = PremiumReportBot()
    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == '__main__':
    asyncio.run(main())
