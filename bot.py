import sqlite3
from telegram import Update, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER PRIMARY KEY,
        join_time TIMESTAMP,
        note TEXT
    )
    ''')
    conn.commit()
    conn.close()

def update_subscription(user_id, join_time, note=None):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO subscriptions (user_id, join_time, note)
    VALUES (?, ?, ?)
    ''', (user_id, join_time, note))
    conn.commit()
    conn.close()

def get_join_time(user_id):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('SELECT join_time FROM subscriptions WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def delete_subscription(user_id):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

async def ban_user(application, user_id, chat_id):
    try:
        await application.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        delete_subscription(user_id)
        logging.info(f"用户 {user_id} 被禁言并踢出")
    except Exception as e:
        logging.error(f"禁言和踢出用户 {user_id} 失败: {e}")

async def check_subscriptions(context):
    application = context.application
    current_time = datetime.now()
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, join_time FROM subscriptions')
    users = cursor.fetchall()
    conn.close()

    for user_id, join_time in users:
        join_time = datetime.fromisoformat(join_time)
        expiry_time = join_time + timedelta(days=1)
        if current_time >= expiry_time:
            try:
                await ban_user(application, user_id, '填写群组chat_id,样式应该是-开头，例如-12345')
            except Exception as e:
                logging.error(f"踢出用户 {user_id} 失败: {e}")

async def start(update: Update, context):
    await update.message.reply_text("欢迎使用我们的订阅服务！")

async def user_join(update: Update, context):
    user_id = update.message.new_chat_members[0].id
    current_time = datetime.now()

    update_subscription(user_id, current_time.isoformat())

    await update.message.reply_text(f"欢迎 {update.message.new_chat_members[0].first_name} 加入！您的订阅有效期为1天。")

async def add_time(update: Update, context):
    user = update.effective_user
    chat = update.effective_chat

    admins = await context.bot.get_chat_administrators(chat.id)
    if not any(admin.user.id == user.id for admin in admins):
        await update.message.reply_text("只有管理员可以使用此命令！")
        return

    try:
        args = context.args
        if len(args) != 1 or '|' not in args[0]:
            raise ValueError("参数格式不正确。正确格式为 /add 用户id|小时|备注")

        user_id, hours, note = args[0].split('|')
        user_id = int(user_id)
        hours = int(hours)

        logging.info(f"解析后的参数: user_id={user_id}, hours={hours}, note={note}")

        join_time = get_join_time(user_id)
        if join_time:
            new_join_time = datetime.fromisoformat(join_time) + timedelta(hours=hours)
            update_subscription(user_id, new_join_time.isoformat(), note)
            await update.message.reply_text(f"已为用户 {user_id} 增加 {hours} 小时，有效期延长至 {new_join_time}。备注：{note}")
        else:
            await update.message.reply_text(f"未找到用户 {user_id} 的订阅记录。")
    except Exception as e:
        logging.error(f"操作失败：{e}")
        await update.message.reply_text(f"操作失败：{e}")

async def reduce_time(update: Update, context):
    user = update.effective_user
    chat = update.effective_chat

    admins = await context.bot.get_chat_administrators(chat.id)
    if not any(admin.user.id == user.id for admin in admins):
        await update.message.reply_text("只有管理员可以使用此命令！")
        return

    try:
        args = context.args
        if len(args) != 1 or '|' not in args[0]:
            raise ValueError("参数格式不正确。正确格式为 /reduce 用户id|小时|备注")

        user_id, hours, note = args[0].split('|')
        user_id = int(user_id)
        hours = int(hours)

        logging.info(f"解析后的参数: user_id={user_id}, hours={hours}, note={note}")

        join_time = get_join_time(user_id)
        if join_time:
            new_join_time = datetime.fromisoformat(join_time) - timedelta(hours=hours)
            if new_join_time < datetime.now():
                await ban_user(context.application, user_id, chat.id)
                await update.message.reply_text(f"用户 {user_id} 的订阅时间已减少 {hours} 小时，已过期并被踢出。备注：{note}")
            else:
                update_subscription(user_id, new_join_time.isoformat(), note)
                await update.message.reply_text(f"已为用户 {user_id} 减少 {hours} 小时，有效期更新至 {new_join_time}。备注：{note}")
        else:
            await update.message.reply_text(f"未找到用户 {user_id} 的订阅记录。")
    except Exception as e:
        logging.error(f"操作失败：{e}")
        await update.message.reply_text(f"操作失败：{e}")

def main():
    application = Application.builder().token("填写telegram bot 的 密钥").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, user_join))
    application.add_handler(CommandHandler("add", add_time))
    application.add_handler(CommandHandler("reduce", reduce_time))

    application.job_queue.run_repeating(check_subscriptions, interval=60, first=0)  

    application.run_polling()

init_db()
main()
