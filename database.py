import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_file="users.db"):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    subscription_type TEXT,
                    subscription_end TIMESTAMP,
                    reports_used INTEGER DEFAULT 0,
                    total_reports INTEGER DEFAULT 0,
                    joined_date TIMESTAMP,
                    last_activity TIMESTAMP
                )
            ''')
            
            # Таблица администраторов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_date TIMESTAMP
                )
            ''')
            
            # Таблица транзакций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    subscription_type TEXT,
                    status TEXT,
                    created_at TIMESTAMP,
                    paid_at TIMESTAMP
                )
            ''')
            
            # Таблица действий администраторов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    target_user INTEGER,
                    details TEXT,
                    created_at TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_user(self, user_id, username):
        """Добавление нового пользователя"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, joined_date, last_activity) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, datetime.now(), datetime.now()))
            conn.commit()
    
    def get_user(self, user_id):
        """Получение информации о пользователе"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()
    
    def check_subscription(self, user_id):
        """Проверка активной подписки"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT subscription_type, subscription_end, reports_used 
                FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            
            if not result or not result[1]:
                return None
            
            end_date = datetime.fromisoformat(result[1])
            if end_date > datetime.now():
                return {
                    'type': result[0],
                    'end_date': end_date,
                    'reports_used': result[2]
                }
            return None
    
    def update_subscription(self, user_id, sub_type, days):
        """Обновление подписки пользователя"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Получаем текущую подписку
            cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                current_end = datetime.fromisoformat(result[0])
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
            
            cursor.execute('''
                UPDATE users 
                SET subscription_type = ?, subscription_end = ?, reports_used = 0, last_activity = ?
                WHERE user_id = ?
            ''', (sub_type, new_end.isoformat(), datetime.now(), user_id))
            
            conn.commit()
            return new_end
    
    def give_subscription(self, user_id, sub_type, days, given_by):
        """Выдача подписки администратором"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            new_end = datetime.now() + timedelta(days=days)
            
            cursor.execute('''
                UPDATE users 
                SET subscription_type = ?, subscription_end = ?, reports_used = 0, last_activity = ?
                WHERE user_id = ?
            ''', (sub_type, new_end.isoformat(), datetime.now(), user_id))
            
            # Логируем действие
            cursor.execute('''
                INSERT INTO admin_actions (admin_id, action, target_user, details, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (given_by, 'give_subscription', user_id, f"{sub_type}_{days}days", datetime.now()))
            
            conn.commit()
            return new_end
    
    def remove_subscription(self, user_id):
        """Удаление подписки"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET subscription_type = NULL, subscription_end = NULL, reports_used = 0
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
    
    def increment_reports(self, user_id):
        """Увеличение счетчика отправленных жалоб"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET reports_used = reports_used + 1,
                    total_reports = total_reports + 1,
                    last_activity = ?
                WHERE user_id = ?
            ''', (datetime.now(), user_id))
            conn.commit()
    
    def is_admin(self, user_id):
        """Проверка является ли пользователь администратором"""
        from config import ADMIN_IDS
        if user_id in ADMIN_IDS:
            return True
        
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
            return cursor.fetchone() is not None
    
    def add_admin(self, user_id, added_by):
        """Добавление администратора"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO admins (user_id, added_by, added_date)
                VALUES (?, ?, ?)
            ''', (user_id, added_by, datetime.now()))
            
            # Логируем действие
            cursor.execute('''
                INSERT INTO admin_actions (admin_id, action, target_user, details, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (added_by, 'add_admin', user_id, f"Added admin", datetime.now()))
            
            conn.commit()
    
    def remove_admin(self, user_id, removed_by):
        """Удаление администратора"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            
            # Логируем действие
            cursor.execute('''
                INSERT INTO admin_actions (admin_id, action, target_user, details, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (removed_by, 'remove_admin', user_id, f"Removed admin", datetime.now()))
            
            conn.commit()
    
    def add_transaction(self, transaction_id, user_id, amount, currency, sub_type):
        """Добавление транзакции"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO transactions 
                (transaction_id, user_id, amount, currency, subscription_type, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, user_id, amount, currency, sub_type, 'pending', datetime.now()))
            conn.commit()
    
    def update_transaction(self, transaction_id, status):
        """Обновление статуса транзакции"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE transactions 
                SET status = ?, paid_at = ?
                WHERE transaction_id = ?
            ''', (status, datetime.now() if status == 'paid' else None, transaction_id))
            conn.commit()
    
    def get_all_users(self, limit=100, offset=0):
        """Получение списка пользователей"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, subscription_type, subscription_end, 
                       reports_used, total_reports, joined_date, last_activity
                FROM users ORDER BY joined_date DESC LIMIT ? OFFSET ?
            ''', (limit, offset))
            return cursor.fetchall()
    
    def get_admin_stats(self):
        """Статистика для администраторов"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Всего пользователей
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['total_users'] = cursor.fetchone()[0]
            
            # Активные подписки
            cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_end > ?', 
                          (datetime.now().isoformat(),))
            stats['active_subs'] = cursor.fetchone()[0]
            
            # По типам подписок
            sub_types = {}
            for sub in ['1_day', '3_days', '7_days', '30_days']:
                cursor.execute('''
                    SELECT COUNT(*) FROM users 
                    WHERE subscription_type = ? AND subscription_end > ?
                ''', (sub, datetime.now().isoformat()))
                sub_types[sub] = cursor.fetchone()[0]
            stats['subscriptions'] = sub_types
            
            # Доход
            cursor.execute('SELECT SUM(amount) FROM transactions WHERE status = "paid"')
            stats['total_revenue'] = cursor.fetchone()[0] or 0
            
            # Всего жалоб
            cursor.execute('SELECT SUM(total_reports) FROM users')
            stats['total_reports'] = cursor.fetchone()[0] or 0
            
            return stats
    
    def get_admin_actions(self, limit=50):
        """История действий администраторов"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT admin_id, action, target_user, details, created_at
                FROM admin_actions ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
