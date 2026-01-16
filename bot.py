print("Файл bot.py запущен")

import sqlite3
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from datetime import datetime, timedelta

TOKEN = "8468917471:AAF62mZRqBAiFBAjFpoE_oMNndu49eCn2Yg"

# --- База SQLite ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id INTEGER,
    name TEXT,
    minutes INTEGER
)
""")
conn.commit()

# --- Состояния ---
user_state = {}
user_data = {}

# --- Главное меню ---
main_menu = ReplyKeyboardMarkup(
    [["📝 Создать сценарий", "📂 Мои сценарии"], ["🕒 Рассчитать время"]],
    resize_keyboard=True
)

# --- Работа с базой ---
def ensure_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def add_scenario(user_id, name):
    cursor.execute("INSERT INTO scenarios (user_id,name) VALUES (?,?)", (user_id,name))
    conn.commit()
    return cursor.lastrowid

def get_scenarios(user_id):
    cursor.execute("SELECT id,name FROM scenarios WHERE user_id=?", (user_id,))
    return cursor.fetchall()

def delete_scenario(scenario_id):
    cursor.execute("DELETE FROM tasks WHERE scenario_id=?", (scenario_id,))
    cursor.execute("DELETE FROM scenarios WHERE id=?", (scenario_id,))
    conn.commit()

def update_scenario_name(scenario_id, new_name):
    cursor.execute("UPDATE scenarios SET name=? WHERE id=?", (new_name, scenario_id))
    conn.commit()

def add_task(scenario_id, name, minutes):
    cursor.execute("INSERT INTO tasks (scenario_id,name,minutes) VALUES (?,?,?)", (scenario_id,name,minutes))
    conn.commit()

def get_tasks(scenario_id):
    cursor.execute("SELECT id,name,minutes FROM tasks WHERE scenario_id=?", (scenario_id,))
    return cursor.fetchall()

def delete_task(task_id):
    cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()

def update_task(task_id, new_name, new_minutes):
    cursor.execute("UPDATE tasks SET name=?, minutes=? WHERE id=?", (new_name,new_minutes,task_id))
    conn.commit()

# --- Напоминание ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data['user_id']
    scenario_id = context.job.data['scenario_id']
    tasks = get_tasks(scenario_id)
    total_minutes = sum(m for _,_,m in tasks)
    target_time = context.job.data['target_time']
    road_minutes = context.job.data['road_minutes']

    leave = target_time - timedelta(minutes=road_minutes)
    wake = leave - timedelta(minutes=total_minutes)
    scenario_name = next(name for sid,name in get_scenarios(user_id) if sid==scenario_id)

    msg = f"📂 Сценарий: {scenario_name}\n🛏 Проснуться: {wake.strftime('%H:%M')}\n🚪 Выйти: {leave.strftime('%H:%M')}"
    await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=main_menu)

# --- Бот ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    user_state[user_id] = None
    await update.message.reply_text(
        "Привет! Я помогу тебе управлять утренними сценариями ☀️\nВыбирай действие кнопками ниже.",
        reply_markup=main_menu
    )

async def show_scenario_menu(update, scenario_id):
    keyboard = [["✏️ Редактировать название", "🗑 Удалить сценарий"],
                ["📝 Добавить дело", "✏️ Редактировать дело", "🗑 Удалить дело"],
                ["👀 Показать дела"], ["↩️ Назад"]]
    await update.message.reply_text(
        "Выбери действие для сценария:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if not text: return
    text = text.strip()
    ensure_user(user_id)
    state = user_state.get(user_id)

    # --- Кнопка назад для редактирования/удаления дел ---
    if state in ["select_task_to_edit", "select_task_to_delete"] and text=="↩️ Назад":
        scenario_id = user_data[user_id]["scenario_id"]
        user_state[user_id] = "scenario_action"
        await show_scenario_menu(update, scenario_id)
        return

    # --- Создание сценария ---
    if text=="📝 Создать сценарий":
        user_state[user_id]="creating_scenario"
        await update.message.reply_text("Введи название сценария (пример: Утро на работу)")
        return

    if state=="creating_scenario":
        scenario_id = add_scenario(user_id, text)
        user_data[user_id]={"scenario_id":scenario_id}
        user_state[user_id]="adding_task"
        await update.message.reply_text("Сценарий создан! Добавь дело: пример 'Завтрак 15' или 'Тренировка 1.5'")
        return

    # --- Добавление дела ---
    if state=="adding_task" and text not in ["➕ Создать сценарий","📂 Мои сценарии","🕒 Рассчитать время"]:
        try:
            name,val=text.rsplit(" ",1)
            minutes=float(val.replace(",","."))
            if minutes<5: minutes=int(minutes*60)
            else: minutes=int(minutes)
            add_task(user_data[user_id]["scenario_id"], name, minutes)
            await update.message.reply_text(f"✅ Добавлено: {name} ({minutes} мин)\nДобавь ещё дело или выбери пункт меню.")
        except:
            await update.message.reply_text("Ошибка. Формат: Название 15 (минут) или 1.5 (часа)")
        return

    # --- Мои сценарии ---
    if text=="📂 Мои сценарии":
        scenarios=get_scenarios(user_id)
        if not scenarios:
            await update.message.reply_text("Нет сценариев.")
            return
        keyboard=[[name] for _,name in scenarios]
        await update.message.reply_text("Выбери сценарий для управления:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        user_state[user_id]="select_scenario_for_edit"
        return

    if state=="select_scenario_for_edit":
        scenarios=get_scenarios(user_id)
        selected=next((sid for sid,name in scenarios if name==text),None)
        if not selected:
            await update.message.reply_text("Выбери сценарий кнопкой")
            return
        user_data[user_id]={"scenario_id":selected}
        user_state[user_id]="scenario_action"
        await show_scenario_menu(update, selected)
        return

    # --- Действия со сценарием ---
    if state=="scenario_action":
        scenario_id=user_data[user_id]["scenario_id"]
        if text=="↩️ Назад":
            user_state[user_id]=None
            await update.message.reply_text("Возврат в главное меню", reply_markup=main_menu)
            return
        elif text=="🗑 Удалить сценарий":
            delete_scenario(scenario_id)
            user_state[user_id]=None
            await update.message.reply_text("Сценарий удалён", reply_markup=main_menu)
            return
        elif text=="✏️ Редактировать название":
            user_state[user_id]="editing_scenario_name"
            await update.message.reply_text("Введи новое название сценария")
            return
        elif text=="📝 Добавить дело":
            user_state[user_id]="adding_task"
            await update.message.reply_text("Добавь новое дело: пример 'Завтрак 15'")
            return
        elif text=="✏️ Редактировать дело":
            tasks=get_tasks(scenario_id)
            if not tasks:
                await update.message.reply_text("Нет дел для редактирования")
                return
            # ---- исправленная нумерация с 1 ----
            keyboard = []
            for idx, (_, name, minutes) in enumerate(tasks):
                keyboard.append([f"{idx+1}: {name} ({minutes} мин)"])
            keyboard.append(["↩️ Назад"])
            await update.message.reply_text("Выбери дело для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_state[user_id]="select_task_to_edit"
            return
        elif text=="🗑 Удалить дело":
            tasks=get_tasks(scenario_id)
            if not tasks:
                await update.message.reply_text("Нет дел для удаления")
                return
            keyboard = []
            for idx, (_, name, minutes) in enumerate(tasks):
                keyboard.append([f"{idx+1}: {name} ({minutes} мин)"])
            keyboard.append(["↩️ Назад"])
            await update.message.reply_text("Выбери дело для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            user_state[user_id]="select_task_to_delete"
            return
        elif text=="👀 Показать дела":
            tasks=get_tasks(scenario_id)
            if not tasks:
                await update.message.reply_text("Нет дел в сценарии")
            else:
                msg="Список дел:\n"
                for _,name,minutes in tasks:
                    msg+=f"• {name} ({minutes} мин)\n"
                await update.message.reply_text(msg)
            await show_scenario_menu(update, scenario_id)
            return
        else:
            await update.message.reply_text("Выбери действие кнопкой")
            return

    # --- Выбор дела для редактирования ---
    if state=="select_task_to_edit":
        try:
            tasks=get_tasks(user_data[user_id]["scenario_id"])
            choice_index=int(text.split(":")[0])-1
            task_id=tasks[choice_index][0]
            user_data[user_id]["task_id"]=task_id
            user_state[user_id]="editing_task"
            await update.message.reply_text("Введи новое название и время: пример 'Завтрак 20'")
        except:
            await update.message.reply_text("Ошибка выбора дела")
        return

    # --- Выбор дела для удаления ---
    if state=="select_task_to_delete":
        try:
            tasks=get_tasks(user_data[user_id]["scenario_id"])
            choice_index=int(text.split(":")[0])-1
            task_id=tasks[choice_index][0]
            delete_task(task_id)
            user_state[user_id]="scenario_action"
            await show_scenario_menu(update, user_data[user_id]["scenario_id"])
        except:
            await update.message.reply_text("Ошибка выбора дела")
        return

    # --- Расчёт времени ---
    if text=="🕒 Рассчитать время":
        scenarios=get_scenarios(user_id)
        if not scenarios:
            await update.message.reply_text("Сначала создай сценарий")
            return
        keyboard=[[name] for _,name in scenarios]
        await update.message.reply_text("Выбери сценарий:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        user_state[user_id]="choosing_scenario"
        return

    if state=="choosing_scenario":
        scenarios=get_scenarios(user_id)
        selected=next((sid for sid,name in scenarios if name==text),None)
        if not selected:
            await update.message.reply_text("Выбери кнопкой")
            return
        user_data[user_id]={"scenario_id":selected}
        user_state[user_id]="waiting_target_time"
        await update.message.reply_text("К какому времени нужно быть? (пример: 9:50)")
        return

    if state=="waiting_target_time":
        try:
            target_time=datetime.strptime(text,"%H:%M")
            user_data[user_id]["target_time"]=target_time
            user_state[user_id]="waiting_road"
            await update.message.reply_text("Сколько минут занимает дорога? Можно в часах 0.5")
        except:
            await update.message.reply_text("Формат: 9:50 или 09:50")
        return

    # --- Блок дороги с выводом результата сразу ---
    if state=="waiting_road":
        try:
            road_val=float(text.replace(",","."))
            if road_val<6: road_minutes=int(road_val*60)
            else: road_minutes=int(road_val)
        except:
            await update.message.reply_text("Введи число минут или часов")
            return

        scenario_id=user_data[user_id]["scenario_id"]
        tasks=get_tasks(scenario_id)
        total_minutes=sum(m for _,_,m in tasks)
        target=user_data[user_id]["target_time"]
        leave=target-timedelta(minutes=road_minutes)
        wake=leave-timedelta(minutes=total_minutes)

        # --- Сразу показываем пользователю ---
        scenario_name=next(name for sid,name in get_scenarios(user_id) if sid==scenario_id)
        await update.message.reply_text(
            f"📂 {scenario_name}\n🛏 Проснуться: {wake.strftime('%H:%M')}\n🚪 Выйти: {leave.strftime('%H:%M')}",
            reply_markup=main_menu
        )

        # --- Ставим JobQueue ---
        job_context = {"user_id":user_id, "scenario_id":scenario_id, "target_time":target, "road_minutes":road_minutes}
        old_jobs = context.application.job_queue.get_jobs_by_name(str(user_id))
        for j in old_jobs: j.schedule_removal()

        context.application.job_queue.run_daily(
            send_reminder,
            time=target.time(),
            context=job_context,
            name=str(user_id)
        )

        user_state[user_id]=None
        user_data.pop(user_id,None)
        return

# --- Основная функция ---
def main():
    app=ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__=="__main__":
    main()
