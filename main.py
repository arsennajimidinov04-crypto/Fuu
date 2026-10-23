import asyncio
import math
import os
import logging
from datetime import datetime
from aiohttp import ClientSession, web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8846213727:AAEIeC8ZrWGG8rlwk5jQZiNj-0M3ny1PmZc"
API_FOOTBALL_KEY = "6cfaa52e1c30a7c303e479037c5cbc0d"
API_FOOTBALL_URL = "https://v3.football.api-sports.io"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- МАТЕМАТИЧЕСКАЯ МОДЕЛЬ (ПУАССОН) ---
def poisson_prob(lmbda, k):
    return (lmbda ** k * math.exp(-lmbda)) / math.factorial(k)

def analyze_match_advanced(home_xg: float, away_xg: float, max_goals: int = 7):
    p_home_win, p_draw, p_away_win = 0.0, 0.0, 0.0
    totals = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    btts_yes = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_prob(home_xg, h) * poisson_prob(away_xg, a)
            if h > a: p_home_win += p
            elif h == a: p_draw += p
            else: p_away_win += p
                
            total_goals = h + a
            if total_goals > 1.5: totals[1.5] += p
            if total_goals > 2.5: totals[2.5] += p
            if total_goals > 3.5: totals[3.5] += p
            if h > 0 and a > 0: btts_yes += p

    return {
        "p1": p_home_win * 100, "px": p_draw * 100, "p2": p_away_win * 100,
        "over_2.5": totals[2.5] * 100, "under_2.5": (1 - totals[2.5]) * 100,
        "btts": btts_yes * 100,
        "fair_1": round(1 / p_home_win, 2) if p_home_win > 0 else 99.0,
        "fair_x": round(1 / p_draw, 2) if p_draw > 0 else 99.0,
        "fair_2": round(1 / p_away_win, 2) if p_away_win > 0 else 99.0,
    }

# --- КОМАНДЫ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "⚽ **Элитный Футбольный Аналитик & Live** активирован!\n\n"
        "📌 Отправь `/matches`, чтобы увидеть список матчей, время и получить кнопки для Live-анализа и рекомендаций по ставкам."
    )

@dp.message(Command("matches"))
async def cmd_matches(message: types.Message):
    msg = await message.answer("🔄 Загружаю матчи на сегодня...")
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    today = datetime.now().strftime("%Y-%m-%d")

    async with ClientSession() as session:
        async with session.get(f"{API_FOOTBALL_URL}/fixtures?date={today}", headers=headers) as response:
            if response.status != 200:
                await msg.edit_text("❌ Ошибка соединения с сервером статистики.")
                return
            
            data = await response.json()
            fixtures = data.get("response", [])[:5]

            if not fixtures:
                await msg.edit_text("На сегодня матчей не обнаружено.")
                return

            text = "📊 **Доступные матчи на сегодня:**\nВыбери матч для просмотра прогноза или Live-анализа:"
            
            builder = InlineKeyboardBuilder()
            for fix in fixtures:
                fixture_id = fix["fixture"]["id"]
                home = fix["teams"]["home"]["name"]
                away = fix["teams"]["away"]["name"]
                
                raw_time = fix["fixture"]["date"]
                match_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).strftime("%H:%M") if raw_time else "ТБД"
                
                # Кнопка для каждого матча
                builder.button(text=f"⏰ {match_time} | {home[:10]} vs {away[:10]}", callback_data=f"match_{fixture_id}")
            
            builder.adjust(1)
            await msg.edit_text(text, reply_markup=builder.as_markup())

# --- ОБРАБОТКА КНОПОК (ПРЕХОД В LIVE И АНАЛИЗ) ---
@dp.callback_query(lambda c: c.data.startswith("match_") or c.data.startswith("live_"))
async def process_callbacks(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    action = data_parts[0]
    fixture_id = data_parts[1]

    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    async with ClientSession() as session:
        async with session.get(f"{API_FOOTBALL_URL}/fixtures?id={fixture_id}", headers=headers) as response:
            if response.status != 200:
                await callback.answer("Ошибка получения данных матча!", show_alert=True)
                return
            
            res_data = await response.json()
            fixtures = res_data.get("response", [])
            if not fixtures:
                await callback.answer("Матч не найден.", show_alert=True)
                return
            
            fix = fixtures[0]
            home = fix["teams"]["home"]["name"]
            away = fix["teams"]["away"]["name"]
            league = fix["league"]["name"]
            status_short = fix["fixture"]["status"]["short"] # NS, 1H, HT, 2H, FT и т.д.
            elapsed = fix["fixture"]["status"]["elapsed"] or 0
            
            home_goals = fix["goals"]["home"] if fix["goals"]["home"] is not None else 0
            away_goals = fix["goals"]["away"] if fix["goals"]["away"] is not None else 0

            # 1. Обычный предматчевый анализ
            if action == "match":
                home_xg, away_xg = 1.55, 1.20
                model = analyze_match_advanced(home_xg, away_xg)
                
                text = (
                    f"🏆 *{league}*\n"
                    f"⚔️ **{home} vs {away}**\n"
                    f"📈 *xG Модель:* {home_xg} — {away_xg}\n\n"
                    f"• **П1:** {model['p1']:.1f}% (Кф: {model['fair_1']})\n"
                    f"• **Ничья (X):** {model['px']:.1f}% (Кф: {model['fair_x']})\n"
                    f"• **П2:** {model['p2']:.1f}% (Кф: {model['fair_2']})\n"
                    f"• **ТБ 2.5:** {model['over_2.5']:.1f}% | **ТМ 2.5:** {model['under_2.5']:.1f}%\n"
                    f"• **Обе забьют:** {model['btts']:.1f}%\n"
                )

                builder = InlineKeyboardBuilder()
                builder.button(text="🔄 Запросить Live-анализ", callback_data=f"live_{fixture_id}")
                builder.button(text="🔙 К списку матчей", callback_data="back_to_list")
                builder.adjust(1)

                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

            # 2. Live-анализ матча в реальном времени
            elif action == "live":
                if status_short in ["NS", "TBD"]:
                    live_text = (
                        f"🔴 **Live Анализ: {home} vs {away}**\n\n"
                        f"⏳ Матч еще **не начался** (Статус: Ожидается).\n"
                        f"💡 *Рекомендация:* Дождитесь стартового свистка или используйте предматчевый прогноз."
                    )
                else:
                    # Корректируем xG с учетом текущего счета и минуты матча
                    time_factor = max(elapsed, 1) / 90.0
                    live_home_xg = round(1.4 * (1 - time_factor) + home_goals * 0.9, 2)
                    live_away_xg = round(1.1 * (1 - time_factor) + away_goals * 0.9, 2)
                    
                    live_model = analyze_match_advanced(live_home_xg, live_away_xg)
                    
                    # Генерация умной рекомендации для ставки в лайве
                    recommendation = "⏸ Нет явного валуя, лучше пропустить."
                    if home_goals > away_goals and elapsed > 65 and live_model['p1'] > 60:
                        recommendation = f"🔥 **Рекомендация:** Победа {home} (Хозяева удерживают преимущество и доминируют)."
                    elif away_goals > home_goals and elapsed > 65 and live_model['p2'] > 60:
                        recommendation = f"🔥 **Рекомендация:** Победа {away} (Гости грамотно играют по счету)."
                    elif home_goals == away_goals and elapsed > 70:
                        recommendation = "🔥 **Рекомендация:** ТБ (Тотал больше) с учетом возможного штурма в концовке."
                    else:
                        recommendation = "⚡️ **Рекомендация:** Игра равная, следите за опасными моментами (удаления/натиск)."

                    live_text = (
                        f"🔴 **LIVE АНАЛИЗ В РЕАЛЬНОМ ВРЕМЕНИ**\n"
                        f"🏆 *{league}*\n"
                        f"⚔️ **{home} {home_goals} : {away_goals} {away}**\n"
                        f"⏱ **Статус:** Минута `{elapsed}'` ({status_short})\n\n"
                        f"📊 **Остаточный потенциал (Live xG):** {live_home_xg} — {live_away_xg}\n"
                        f"• Вероятность победы 1: `{live_model['p1']:.1f}%`\n"
                        f"• Вероятность ничьей: `{live_model['px']:.1f}%`\n"
                        f"• Вероятность победы 2: `{live_model['p2']:.1f}%`\n\n"
                        f"{recommendation}"
                    )

                builder = InlineKeyboardBuilder()
                builder.button(text="🔄 Обновить Live", callback_data=f"live_{fixture_id}")
                builder.button(text="🔙 Назад к прогнозу", callback_data=f"match_{fixture_id}")
                builder.adjust(1)

                await callback.message.edit_text(live_text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery):
    await callback.message.edit_text("Отправь команду `/matches`, чтобы заново открыть список матчей.", parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle_ping(request):
    return web.Response(text="Bot live analytics core is active 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
