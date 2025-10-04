import random
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import BotCommand

API_TOKEN = "8363009902:AAFZjpldsLbOPAU7OzrBxvsiNABkOFqkMUU"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

active_mines = {}  # активні ігри Mines
DB_FILE = "casino.db"

# --- База даних ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 1000,
                last_bonus INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def add_user(user_id: int, username: str = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()
        if username:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def update_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_last_bonus(user_id: int, timestamp: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
        await db.commit()

async def get_last_bonus(user_id: int) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def get_top_users(limit=15):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)) as cur:
            return await cur.fetchall()

async def set_commands():
    commands = [
        BotCommand(command="start", description="Запустити бота та створити акаунт"),
        BotCommand(command="balance", description="Показати ваш баланс"),
        BotCommand(command="bonus", description="Отримати бонус раз на 6 годин"),
        BotCommand(command="mins", description="Грати у гру Mines (/mins <ставка>)"),
        BotCommand(command="spin", description="Грати у Red або Black (/spin <ставка> <red/black>)"),
        BotCommand(command="dice", description="Грати у кидок кубика (/dice <ставка> <1-6>)"),
        BotCommand(command="guess", description="Грати у Вгадай число (/guess <ставка> <1-10>)"),
        BotCommand(command="pay", description="Переслати монети іншому користувачу (/pay <user_id> <сума>)"),
        BotCommand(command="top", description="Показати топ-15 гравців за балансом")
    ]
    await bot.set_my_commands(commands)

# --- Старт і баланс ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "🎰 Ласкаво просимо! Ваш акаунт створено. Початковий баланс: 1000 монет.\n"
        "Використайте /bonus, щоб отримати нагороду!\n"
        "Використайте /balance, щоб перевірити баланс.\n"
        "Використайте /mins <ставка>, щоб грати у Mines!\n"
        "Використайте /spin <ставка> <red/black>, щоб грати у Red або Black!\n"
        "Використайте /dice <ставка> <1-6>, щоб кинути кубик!\n"
        "Використайте /guess <ставка> <1-10>, щоб вгадати число!\n"
        "Використайте /pay <user_id> <сума>, щоб переслати монети.\n"
        "Використайте /top, щоб побачити топ-15 гравців за балансом!"
    )

@dp.message(Command("balance"))
async def balance_cmd(message: types.Message):
    bal = await get_balance(message.from_user.id)
    await message.answer(f"💰 Ваш баланс: {bal} монет")

@dp.message(Command("bonus"))
async def bonus_cmd(message: types.Message):
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.username)
    now = int(asyncio.get_event_loop().time())
    last = await get_last_bonus(user_id)

    if now - last < 21600:  # 6 годин
        wait = 21600 - (now - last)
        hours = wait // 3600
        minutes = (wait % 3600) // 60
        await message.answer(f"⏳ Наступний бонус можна отримати через {hours} год {minutes} хв.")
        return

    reward = random.randint(200, 2000)
    await update_balance(user_id, reward)
    await set_last_bonus(user_id, now)
    balance = await get_balance(user_id)
    await message.answer(f"🎁 Ви отримали {reward} монет!\n💰 Баланс: {balance}")

# --- Топ 15 ---
@dp.message(Command("top"))
async def top_cmd(message: types.Message):
    top_users = await get_top_users(15)
    if not top_users:
        await message.answer("Немає гравців у базі.")
        return
    text = "🏆 Топ-15 гравців за балансом:\n"
    for i, (username, balance) in enumerate(top_users, 1):
        name = username if username else "Без ніку"
        text += f"{i}. 👤 {name} — {balance} монет\n"
    await message.answer(text)

# --- Mines Game ---
@dp.message(Command("mins"))
async def mins_game(message: types.Message):
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.username)
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("Використання: /mins <ставка>")
        return

    bet = int(args[1])
    balance = await get_balance(user_id)
    if bet > balance:
        await message.answer("❌ Недостатньо монет!")
        return

    await update_balance(user_id, -bet)

    mines_count = 5
    cells = list(range(25))
    mines = set(random.sample(cells, mines_count))
    active_mines[user_id] = {
        "bet": bet,
        "multiplier": 1.0,
        "mines": mines,
        "opened": set()
    }

    buttons = [InlineKeyboardButton(text="❔", callback_data=str(i)) for i in range(25)]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons[i:i+5] for i in range(0, 25, 5)]
    )
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="💰 Зняти", callback_data="cashout")])

    await message.answer(f"🎮 Mines Game почалась! Ставка: {bet}\nВиберіть клітинку.", reply_markup=keyboard)

@dp.callback_query()
async def handle_cell(call: CallbackQuery):
    user_id = call.from_user.id
    if user_id not in active_mines:
        await call.answer("Немає активної гри.", show_alert=True)
        return

    game = active_mines[user_id]

    if call.data == "cashout":
        win_amount = int(game["bet"] * game["multiplier"])
        await update_balance(user_id, win_amount)
        await call.message.edit_text(f"💸 Ви зняли ставку! Ви виграли {win_amount} монет.")
        del active_mines[user_id]
        return

    cell = int(call.data)
    if cell in game["opened"]:
        await call.answer("Вже відкрито!", show_alert=True)
        return

    if cell in game["mines"]:
        await call.message.edit_text(f"💥 Бум! Ви натрапили на міну.\nВтрачені {game['bet']} монет.")
        del active_mines[user_id]
        return

    # Вдале відкриття
    game["opened"].add(cell)
    game["multiplier"] *= 1.65
    win_amount = int(game["bet"] * game["multiplier"])

    buttons = []
    for i in range(25):
        if i in game["opened"]:
            buttons.append(InlineKeyboardButton(text="✅", callback_data=str(i)))
        else:
            buttons.append(InlineKeyboardButton(text="❔", callback_data=str(i)))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons[i:i+5] for i in range(0, 25, 5)]
    )
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="💰 Зняти", callback_data="cashout")])

    await call.message.edit_text(
        f"🎮 Mines Game\nПоточний виграш: {win_amount} монет\nВиберіть іншу клітинку!",
        reply_markup=keyboard
    )

    if len(game["opened"]) >= 20:
        await update_balance(user_id, win_amount)
        await call.message.edit_text(f"🎉 Ви очистили поле! Ви виграли {win_amount} монет!")
        del active_mines[user_id]

# --- Spin / Dice / Guess / Pay залишаються без змін, можна додати за потреби ---

async def main():
    await init_db()
    await set_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

