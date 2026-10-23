"""
⚽ Football Analytics Bot
Стек: Python 3.11+, aiogram 3.x, aiohttp
"""

import os
import math
import logging
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

BOT_TOKEN = "8846213727:AAEIeC8ZrWGG8rlwk5jQZiNj-0M3ny1PmZc"
FOOTBALL_API_KEY = "6cfaa52e1c30a7c303e479037c5cbc0d"
API_BASE = "https://v3.football.api-sports.io"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

HEADERS = {"x-apisports-key": FOOTBALL_API_KEY}


async def api_get(endpoint: str, params: dict | None = None) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}/{endpoint}", headers=HEADERS, params=params
        ) as resp:
            if resp.status != 200:
                return {"errors": [f"HTTP {resp.status}"]}
            return await resp.json()


async def get_today_fixtures(league_id: int = 39) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    data = await api_get("fixtures", {"league": league_id, "date": today})
    return data.get("response", [])


async def get_h2h(team1_id: int, team2_id: int, limit: int = 5) -> list[dict]:
    data = await api_get("fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": limit})
    return data.get("response", [])


def poisson_prob(lmbd: float, k: int) -> float:
    return math.exp(-lmbd) * (lmbd ** k) / math.factorial(k)


def predict_match(home_avg: float, away_avg: float) -> dict:
    home_win = draw = away_win = 0.0
    total_over_2_5 = 0.0

    for hg in range(8):
        for ag in range(8):
            p = poisson_prob(home_avg, hg) * poisson_prob(away_avg, ag)
            if hg > ag:
                home_win += p
            elif hg == ag:
                draw += p
            else:
                away_win += p

            if (hg + ag) > 2.5:
                total_over_2_5 += p

    total = home_win + draw + away_win
    return {
        "home": round(home_win / total * 100, 1),
        "draw": round(draw / total * 100, 1),
        "away": round(away_win / total * 100, 1),
        "tb_2_5": round(total_over_2_5 / total * 100, 1)
    }


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "⚽ <b>Football Analytics Bot</b>\n\n"
        "📊 <b>Доступные команды:</b>\n"
        "• /today — Матчи сегодня (АПЛ)\n"
        "• /predict <code>home_avg</code> <code>away_avg</code> — Расчёт по Пуассону\n"
        "• /h2h <code>id1</code> <code>id2</code> — Личные встречи двух команд по ID",
        parse_mode="HTML",
    )


@dp.message(Command("today"))
async def cmd_today(message: Message):
    fixtures = await get_today_fixtures(league_id=39)
    if not fixtures:
        await message.answer("Сегодня матчей в АПЛ нет 😴")
        return

    lines = ["⚽ <b>Матчи сегодня (АПЛ):</b>\n"]
    for fx in fixtures:
        h = fx["teams"]["home"]["name"]
        a = fx["teams"]["away"]["name"]
        t = datetime.fromisoformat(fx["fixture"]["date"]).strftime("%H:%M")
        status = fx["fixture"]["status"]["short"]
        score_h = fx["goals"]["home"]
        score_a = fx["goals"]["after"] if "after" in fx["goals"] else fx["goals"]["away"]

        if status in ("1H", "HT", "2H", "ET", "P"):
            lines.append(f"🔴 LIVE [{t}] {h} <b>{score_h}:{score_a}</b> {a}")
        elif status == "FT":
            lines.append(f"🏁 Завершен {h} <b>{score_h}:{score_a}</b> {a}")
        else:
            lines.append(f"🕐 {t}  {h} — {a}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("predict"))
async def cmd_predict(message: Message):
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            raise ValueError

        home_avg = float(args[0].replace(",", "."))
        away_avg = float(args[1].replace(",", "."))

        p = predict_match(home_avg, away_avg)

        await message.answer(
            f"🔮 <b>Прогноз (модель Пуассона):</b>\n\n"
            f"🏠 Победа хозяев (П1): <b>{p['home']}%</b>\n"
            f"🤝 Ничья (Х): <b>{p['draw']}%</b>\n"
            f"✈️ Победа гостей (П2): <b>{p['away']}%</b>\n\n"
            f"⚽ Тотал больше 2.5: <b>{p['tb_2_5']}%</b>",
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer(
            "⚠️ <b>Ошибка формата!</b>\nИспользуйте: <code>/predict 1.8 1.1</code>",
            parse_mode="HTML"
        )


@dp.message(Command("h2h"))
async def cmd_h2h(message: Message):
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            raise ValueError

        t1, t2 = int(args[0]), int(args[1])
        h2h_data = await get_h2h(t1, t2, limit=5)

        if not h2h_data:
            await message.answer("История личных встреч не найдена.")
            return

        lines = [f"⚔️ <b>Последние личные встречи (ID {t1} vs ID {t2}):</b>\n"]
        for match in h2h_data:
            date = match["fixture"]["date"][:10]
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            sh = match["goals"]["home"]
            sa = match["goals"]["away"]
            lines.append(f"🗓 <code>{date}</code> | {home} <b>{sh}:{sa}</b> {away}")

        await message.answer("\n".join(lines), parse_mode="HTML")
    except ValueError:
        await message.answer(
            "⚠️ <b>Ошибка формата!</b>\nИспользуйте ID команд: <code>/h2h 33 34</code>",
            parse_mode="HTML"
        )


async def main():
    log.info("Запуск бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
