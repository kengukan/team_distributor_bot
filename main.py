import os
import logging
import sqlite3
import random
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, ConversationHandler
)

# 🔥 Flask сервер для Webview и UptimeRobot
app = Flask('')

@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>🤖 Team Distributor Bot</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    background: rgba(255,255,255,0.1);
                    padding: 30px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Team Distributor Bot</h1>
                <p>Бот работает и готов к использованию!</p>
                <p>Найдите бота в Telegram и отправьте /start</p>
                <p>🟢 Статус: <strong>Активен</strong></p>
                <p>⏰ 24/7 мониторинг включен</p>
            </div>
        </body>
    </html>
    """

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """Запускает Flask сервер в отдельном потоке"""
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🌐 Web-сервер запущен для Replit Webview")

# Запускаем Flask сервер ДО всего остального
keep_alive()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ USER_ID (узнайте через @userinfobot)
ADMIN_IDS = [641655716]

# Состояния разговора
FIO, CONFIRM = range(2)

class TeamManager:
    def __init__(self, db_path='teams.db'):
        self.db_path = db_path
        self.num_teams = 12
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                fio TEXT NOT NULL,
                team_number INTEGER NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных инициализирована")
    
    def get_user_info(self, user_id):
        """Получить информацию о пользователе"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT fio, team_number FROM users WHERE user_id = ?', 
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result if result else None
    
    def assign_random_team(self, user_id, fio):
        """Случайное распределение по командам с балансировкой"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 🔄 ВАЖНО: Проверяем, есть ли уже пользователь
        existing = self.get_user_info(user_id)
        if existing:
            conn.close()
            print(f"🔁 Пользователь {user_id} уже в команде {existing[1]}")
            return existing[1]  # Возвращаем существующую команду
        
        # Получаем текущее распределение по командам
        cursor.execute('''
            SELECT team_number, COUNT(*) as count 
            FROM users 
            GROUP BY team_number 
            ORDER BY team_number
        ''')
        
        team_counts = {i: 0 for i in range(1, self.num_teams + 1)}
        for team, count in cursor.fetchall():
            team_counts[team] = count
        
        # Находим команды с минимальным количеством участников
        min_count = min(team_counts.values())
        available_teams = [team for team, count in team_counts.items() if count == min_count]
        
        # 🎲 СЛУЧАЙНОЕ распределение из доступных команд
        assigned_team = random.choice(available_teams)
        
        # Добавляем пользователя в базу
        cursor.execute('''
            INSERT INTO users (user_id, fio, team_number)
            VALUES (?, ?, ?)
        ''', (user_id, fio, assigned_team))
        
        conn.commit()
        conn.close()
        print(f"✅ Новый пользователь {fio} добавлен в команду {assigned_team}")
        return assigned_team
    
    def get_teams_with_members(self):
        """Получить список всех команд с участниками"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT team_number, fio 
            FROM users 
            ORDER BY team_number, registered_at
        ''')
        
        teams = {}
        for team_number, fio in cursor.fetchall():
            if team_number not in teams:
                teams[team_number] = []
            teams[team_number].append(fio)
        
        conn.close()
        return teams
    
    def get_team_stats(self):
        """Получить статистику по командам"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT team_number, COUNT(*) as count 
            FROM users 
            GROUP BY team_number 
            ORDER BY team_number
        ''')
        
        stats = cursor.fetchall()
        conn.close()
        return stats
    
    def get_total_users(self):
        """Получить общее количество пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        
        return count

# Инициализация менеджера команд
team_manager = TeamManager()

# 🎯 ДВЕ ПОСТОЯННЫЕ КНОПКИ ВНИЗУ
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🎯 Узнать свою команду", "📊 Статистика"]
    ],
    resize_keyboard=True,
    persistent=True  # Кнопки всегда будут видны
)

def start(update: Update, context: CallbackContext):
    """Начало работы с ботом"""
    user = update.message.from_user
    print(f"👤 Пользователь {user.id} вызвал /start")
    
    # Проверяем, есть ли пользователь уже в системе
    existing_user = team_manager.get_user_info(user.id)
    
    if existing_user:
        fio, team_number = existing_user
        update.message.reply_text(
            f"👋 С возвращением, {fio}!\n\n"
            f"✅ Вы в команде №{team_number}\n\n"
            "Используйте кнопки ниже:",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END
    else:
        update.message.reply_text(
            "👋 Добро пожаловать на нулевую сессию!\n\n"
            "🎯 Нажмите кнопку ниже, чтобы узнать свою команду!",
            reply_markup=MAIN_KEYBOARD
        )
        return FIO

def button_handler(update: Update, context: CallbackContext):
    """Обработчик нажатия кнопок"""
    user = update.message.from_user
    button_text = update.message.text
    
    if button_text == "🎯 Узнать свою команду":
        print(f"🎯 Пользователь {user.id} нажал 'Узнать команду'")
        
        # Проверяем, есть ли пользователь уже в системе
        existing_user = team_manager.get_user_info(user.id)
        
        if existing_user:
            fio, team_number = existing_user
            update.message.reply_text(
                f"👋 {fio}!\n\n"
                f"✅ Вы в команде №{team_number}\n\n"
                "Для просмотра списка всех команд используйте /list",
                reply_markup=MAIN_KEYBOARD
            )
            return ConversationHandler.END
        else:
            update.message.reply_text(
                "📝 Пожалуйста, введите ваше ФИО (Фамилия Имя Отчество):\n\n"
                "Пример: Иванов Иван Иванович"
            )
            return FIO
    
    elif button_text == "📊 Статистика":
        print(f"📊 Пользователь {user.id} нажал 'Статистика'")
        return show_stats(update, context)

def get_fio(update: Update, context: CallbackContext):
    """Получение ФИО от пользователя"""
    fio = update.message.text.strip()
    print(f"📝 Пользователь {update.message.from_user.id} ввел ФИО: {fio}")
    
    # Простая валидация ФИО
    if len(fio) < 5 or len(fio.split()) < 2:
        update.message.reply_text(
            "❌ Пожалуйста, введите полное ФИО (Фамилия Имя Отчество)\n\n"
            "Пример: Иванов Иван Иванович"
        )
        return FIO
    
    # Сохраняем ФИО в контексте
    context.user_data['fio'] = fio
    
    # Подтверждение с кнопками
    update.message.reply_text(
        f"✅ Проверьте ваши данные:\n\n"
        f"ФИО: {fio}\n\n"
        f"Всё верно?",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Да, всё верно"], ["❌ Нет, исправить"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return CONFIRM

def confirm_fio(update: Update, context: CallbackContext):
    """Подтверждение ФИО и распределение по команде"""
    choice = update.message.text
    user_id = update.message.from_user.id
    
    if choice == "✅ Да, всё верно":
        fio = context.user_data['fio']
        
        # 🎲 Распределяем по команде (случайно с балансировкой)
        team_number = team_manager.assign_random_team(user_id, fio)
        
        update.message.reply_text(
            f"🎉 Поздравляем, {fio}!\n\n"
            f"🏆 Вы в команде №{team_number}!\n\n"
            "Теперь вы можете использовать кнопки ниже:",
            reply_markup=MAIN_KEYBOARD
        )
        
        # Очищаем временные данные
        context.user_data.clear()
        return ConversationHandler.END
    
    else:
        update.message.reply_text(
            "📝 Пожалуйста, введите ваше ФИО заново:\n\n"
            "Пример: Иванов Иван Иванович",
            reply_markup=MAIN_KEYBOARD
        )
        return FIO

def cancel(update: Update, context: CallbackContext):
    """Отмена регистрации"""
    update.message.reply_text(
        "Регистрация отменена.\n"
        "Если захотите зарегистрироваться, используйте кнопки ниже:",
        reply_markup=MAIN_KEYBOARD
    )
    context.user_data.clear()
    return ConversationHandler.END

def show_teams_list(update: Update, context: CallbackContext):
    """Показать список всех команд с участниками"""
    teams = team_manager.get_teams_with_members()
    
    if not teams:
        update.message.reply_text(
            "📋 Список команд пуст.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    response = "📋 СПИСОК КОМАНД И УЧАСТНИКОВ:\n\n"
    
    for team_number in sorted(teams.keys()):
        members = teams[team_number]
        response += f"🏆 КОМАНДА {team_number} ({len(members)} чел.):\n"
        
        for i, member in enumerate(members, 1):
            response += f"   {i}. {member}\n"
        
        response += "\n"
    
    # Если сообщение слишком длинное, разбиваем на части
    if len(response) > 4000:
        parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for part in parts:
            update.message.reply_text(part, reply_markup=MAIN_KEYBOARD)
    else:
        update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)

def show_stats(update: Update, context: CallbackContext):
    """Показать статистику распределения"""
    stats = team_manager.get_team_stats()
    total_users = team_manager.get_total_users()
    
    if not stats:
        update.message.reply_text(
            "📊 Статистика пока недоступна.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    response = "📊 СТАТИСТИКА РАСПРЕДЕЛЕНИЯ:\n\n"
    
    for team, count in stats:
        response += f"Команда {team}: {count} чел.\n"
    
    response += f"\nВсего участников: {total_users}"
    response += f"\nВсего команд: {len(stats)}"
    response += f"\nСреднее в команде: {total_users/len(stats):.1f} чел."
    
    update.message.reply_text(response, reply_markup=MAIN_KEYBOARD)

def restart_bot(update: Update, context: CallbackContext):
    """Перезагрузка бота (только для админов)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        update.message.reply_text(
            "❌ Эта команда только для администраторов",
            reply_markup=MAIN_KEYBOARD
        )
        return
    
    update.message.reply_text(
        "🔄 Бот работает! Для перезагрузки нажмите 'Run' в Replit.",
        reply_markup=MAIN_KEYBOARD
    )

def main():
    """Основная функция"""
    # Получаем токен из Secrets
    BOT_TOKEN = os.environ.get('BOT_TOKEN')
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не установлен!")
        print("💡 Установите Secret в Replit: BOT_TOKEN=ваш_токен")
        return
    
    print("🚀 Запуск Telegram бота...")
    print(f"📊 Количество команд: {team_manager.num_teams}")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    
    try:
        updater = Updater(BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher
        
        # Обработчик разговора для регистрации
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', start),
                MessageHandler(Filters.regex('^(🎯 Узнать свою команду|📊 Статистика)$'), button_handler)
            ],
            states={
                FIO: [MessageHandler(Filters.text & ~Filters.command, get_fio)],
                CONFIRM: [MessageHandler(Filters.text & ~Filters.command, confirm_fio)],
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
        # Добавляем обработчики
        dispatcher.add_handler(conv_handler)
        dispatcher.add_handler(CommandHandler('list', show_teams_list))
        dispatcher.add_handler(CommandHandler('stats', show_stats))
        dispatcher.add_handler(CommandHandler('restart', restart_bot))
        
        print("✅ Бот успешно запущен и готов к работе!")
        print("🎯 Две кнопки всегда доступны внизу экрана")
        print("🌐 Web-сервер активен - Webview должен появиться")
        
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        print("🔄 Перезапустите repl кнопкой 'Run'")

if __name__ == '__main__':
    main()
