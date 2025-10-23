import os
import logging
import sqlite3
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, ConversationHandler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ USER_ID!
# Узнайте через @userinfobot в Telegram
ADMIN_IDS = [123456789]

# Состояния разговора
FIO, CONFIRM = range(2)

class TeamManager:
    def __init__(self, db_path='/data/teams.db'):
        self.db_path = db_path
        self.num_teams = 12
        self.init_database()
    
    def init_database(self):
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
    
    def get_user_info(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT fio, team_number FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result if result else None
    
    def assign_random_team(self, user_id, fio):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже пользователь
        existing = self.get_user_info(user_id)
        if existing:
            conn.close()
            return existing[1]
        
        # Случайное распределение с балансировкой
        cursor.execute('SELECT team_number, COUNT(*) FROM users GROUP BY team_number')
        team_counts = {i: 0 for i in range(1, self.num_teams + 1)}
        for team, count in cursor.fetchall():
            team_counts[team] = count
        
        min_count = min(team_counts.values())
        available_teams = [team for team, count in team_counts.items() if count == min_count]
        assigned_team = random.choice(available_teams)
        
        cursor.execute('INSERT INTO users (user_id, fio, team_number) VALUES (?, ?, ?)',
                      (user_id, fio, assigned_team))
        conn.commit()
        conn.close()
        return assigned_team
    
    def get_teams_with_members(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT team_number, fio FROM users ORDER BY team_number, registered_at')
        teams = {}
        for team_number, fio in cursor.fetchall():
            if team_number not in teams:
                teams[team_number] = []
            teams[team_number].append(fio)
        conn.close()
        return teams

team_manager = TeamManager()

def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    
    # Проверяем, есть ли пользователь уже в системе
    existing_user = team_manager.get_user_info(user.id)
    
    if existing_user:
        fio, team_number = existing_user
        update.message.reply_text(
            f"👋 С возвращением, {fio}!\n\n"
            f"Вы уже в команде №{team_number}\n\n"
            "Используйте команды:\n"
            "/list - посмотреть список всех команд\n"
            "/stats - статистика распределения"
        )
        return ConversationHandler.END
    else:
        update.message.reply_text(
            "👋 Добро пожаловать в систему распределения по командам!\n\n"
            "📝 Пожалуйста, введите ваше ФИО (Фамилия Имя Отчество):\n\n"
            "Пример: Иванов Иван Иванович"
        )
        return FIO

def get_fio(update: Update, context: CallbackContext):
    fio = update.message.text.strip()
    
    if len(fio) < 5 or len(fio.split()) < 2:
        update.message.reply_text(
            "❌ Пожалуйста, введите полное ФИО (Фамилия Имя Отчество)\n\n"
            "Пример: Иванов Иван Иванович"
        )
        return FIO
    
    context.user_data['fio'] = fio
    
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
    choice = update.message.text
    
    if choice == "✅ Да, всё верно":
        fio = context.user_data['fio']
        user_id = update.message.from_user.id
        
        team_number = team_manager.assign_random_team(user_id, fio)
        
        update.message.reply_text(
            f"🎉 Поздравляем, {fio}!\n\n"
            f"🏆 Вы в команде №{team_number}!\n\n"
            "Используйте команды:\n"
            "/list - посмотреть список всех команд\n"
            "/stats - статистика распределения",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    else:
        update.message.reply_text(
            "📝 Пожалуйста, введите ваше ФИО заново:\n\n"
            "Пример: Иванов Иван Иванович"
        )
        return FIO

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Регистрация отменена.\n"
        "Если захотите зарегистрироваться, отправьте /start"
    )
    context.user_data.clear()
    return ConversationHandler.END

def show_teams_list(update: Update, context: CallbackContext):
    teams = team_manager.get_teams_with_members()
    
    if not teams:
        update.message.reply_text("📋 Список команд пуст.")
        return
    
    response = "📋 СПИСОК КОМАНД И УЧАСТНИКОВ:\n\n"
    
    for team_number in sorted(teams.keys()):
        members = teams[team_number]
        response += f"🏆 КОМАНДА {team_number} ({len(members)} чел.):\n"
        
        for i, member in enumerate(members, 1):
            response += f"   {i}. {member}\n"
        
        response += "\n"
    
    if len(response) > 4000:
        parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for part in parts:
            update.message.reply_text(part)
    else:
        update.message.reply_text(response)

def show_stats(update: Update, context: CallbackContext):
    teams = team_manager.get_teams_with_members()
    total_users = sum(len(members) for members in teams.values())
    
    response = "📊 СТАТИСТИКА РАСПРЕДЕЛЕНИЯ:\n\n"
    
    for team_number in sorted(teams.keys()):
        count = len(teams[team_number])
        response += f"Команда {team_number}: {count} чел.\n"
    
    response += f"\nВсего участников: {total_users}"
    
    update.message.reply_text(response)

def restart_bot(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    update.message.reply_text("🔄 Бот работает! Для обновления кода используйте деплой в Railway.")

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен!")
        return
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Обработчик разговора для регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
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
    
    print("🚀 Бот запущен на Railway!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()