import asyncio
import math
import os
import sys
from datetime import datetime

from aiohttp import ClientSession, web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command

# --- НАСТРОЙКИ И КЛЮЧИ ---
BOT_TOKEN = "8846213727:AAEIeC8ZrWGG8rlwk5jQZiNj-0M3ny1PmZc"
API_FOOTBALL_KEY = "6cfaa52e1c30a7c303e479037c5cbc0d"
API_FOOTBALL_URL = "https://v3.football.api-sports.io"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- РАСЧЕТ ПУАССОНА ---
def poisson_probability(lmbda, k):
  return (lmbda**k * math.exp(-lmbda)) / math.factorial(k)


def calculate_match_probabilities(home_xg, away_xg, max_goals=5):
  prob_home_win = 0.0
  prob_draw = 0.0
  prob_away_win = 0.0
  total_under_2_5 = 0.0
  total_over_2_5 = 0.0

  for h in range(max_goals + 1):
    for a in range(max_goals + 1):
      p = poisson_probability(home_xg, h) * poisson_probability(away_xg, a)
      if h > a:
        prob_home_win += p
      elif h == a:
        prob_draw += p
      else:
        prob_away_win += p

      if h + a < 2.5:
        total_under_2_5 += p
      else:
        total_over_2_5 += p

  return {
      "p1": round(prob_home_win * 100, 1),
      "px": round(prob_draw * 100, 1),
      "p2": round(prob_away_win * 100, 1),
      "1x": round((prob_home_win + prob_draw) * 100, 1),
      "x2": round((prob_draw + prob_away_win) * 100, 1),
      "under_2_5": round(total_under_2_5 * 100, 1),
      "over_2_5": round(total_over_2_5 * 100, 1),
  }


# --- ОБРАБОТЧИКИ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  await message.answer(
      "⚽ **Футбольный Аналитик Бот** готов к работе!\n\n"
      "Отправь команду `/matches`, чтобы получить список ближайших матчей и их прогноз."
  )


@dp.message(Command("matches"))
async def cmd_matches(message: types.Message):
  await message.answer("🔄 Запрашиваю данные по матчам...")
  headers = {"x-apisports-key": API_FOOTBALL_KEY}
  today = datetime.now().strftime("%Y-%m-%d")

  async with ClientSession() as session:
    async with session.get(
        f"{API_FOOTBALL_URL}/fixtures?date={today}", headers=headers
    ) as response:
      if response.status != 200:
        await message.answer("❌ Ошибка при получении данных от API.")
        return
      data = await response.json()
      fixtures = data.get("response", [])[:5]

      if not fixtures:
        await message.answer("На сегодня запланированных матчей не найдено.")
        return

      res_text = "📊 **Прогноз на сегодня (Пуассон / xG):**\n\n"
      for fix in fixtures:
        home = fix["teams"]["home"]["name"]
        away = fix["teams"]["away"]["name"]

        # Заглушка xG средних значений для расчета
        home_xg, away_xg = 1.45, 1.15
        probs = calculate_match_probabilities(home_xg, away_xg)

        res_text += (
            f"⚔️ **{home} vs {away}**\n"
            f"• П1: {probs['p1']}% | X: {probs['px']}% | П2: {probs['p2']}%\n"
            f"• 1X: {probs['1x']}% | X2: {probs['x2']}%\n"
            f"• ТМ 2.5: {probs['under_2_5']}% | ТБ 2.5: {probs['over_2_5']}%\n\n"
        )

      await message.answer(res_text, parse_mode="Markdown")


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle_ping(request):
  return web.Response(text="Bot is online and running!")


async def start_web_server():
  app = web.Application()
  app.router.add_get("/", handle_ping)
  runner = web.AppRunner(app)
  await runner.setup()

  # Render автоматически передает порт в переменную окружения PORT
  port = int(os.environ.get("PORT", 10000))
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()


# --- ГЛАВНЫЙ ЗАПУСК ---
async def main():
  # Запускаем веб-сервер для порта и бота одновременно
  asyncio.create_task(start_web_server())
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
