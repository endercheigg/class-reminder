from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from database import get_all_classes, get_current_week_start, get_user_timezone
from timezone_utils import utc_to_local
import sqlite3


def start_scheduler(telegram_app, discord_client):

    scheduler = AsyncIOScheduler()

    async def check_lessons():
        try:
            await cleanup_old_temp_moves()

            classes = get_all_classes()
            current_week = get_current_week_start()
            
            conn = sqlite3.connect("classes.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT lesson_name, temp_day, temp_time, telegram_id, discord_id FROM temp_moves WHERE week_start=?",
                (current_week,)
            )
            temp_moves = cur.fetchall()
            conn.close()
            
            class_dict = {}
            for lesson, day, time, tg, dc in classes:
                key = (lesson, tg, dc)
                class_dict[key] = {"day": day, "time": time, "tg": tg, "dc": dc, "is_temp": False}
            for lesson, day, time, tg, dc in temp_moves:
                key = (lesson, tg, dc)
                class_dict[key] = {"day": day, "time": time, "tg": tg, "dc": dc, "is_temp": True}
            
            for (lesson, tg, dc), info in class_dict.items():
                tz = get_user_timezone(tg=tg if tg != "none" else None, dc=dc if dc != "none" else None)
                if not tz:
                    tz = "UTC"
                
                local_day, local_time = utc_to_local(info["day"], info["time"], tz)
                now_local = datetime.now(ZoneInfo(tz))
                current_local_day = now_local.isoweekday()
                current_local_time = now_local.strftime("%H:%M")
                
                try:
                    class_local_dt = datetime.strptime(local_time, "%H:%M")
                    reminder_dt = class_local_dt - timedelta(minutes=5)
                    reminder_time = reminder_dt.strftime("%H:%M")
                except:
                    continue
                
                if current_local_day == local_day and current_local_time == reminder_time:
                    text = f"📚 {lesson} starts in 5 minutes!"
                    if info["is_temp"]:
                        text += " ⚠️ (Moved for this week)"
                    
                    if tg and tg != "none":
                        try:
                            await telegram_app.bot.send_message(chat_id=tg, text=text)
                        except Exception as e:
                            print(f"Failed to send Telegram reminder to {tg}: {e}")
                    
                    if dc and dc != "none":
                        try:
                            user = await discord_client.fetch_user(int(dc))
                            await user.send(text)
                        except Exception as e:
                            print(f"Failed to send Discord reminder to {dc}: {e}")
        except Exception as e:
            print(f"Scheduler error: {e}")

    async def cleanup_old_temp_moves():
        conn = sqlite3.connect("classes.db")
        cur = conn.cursor()
        current_week = get_current_week_start()
        cur.execute("DELETE FROM temp_moves WHERE week_start < ?", (current_week,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            print(f"Cleaned up {deleted} expired temp moves")

    scheduler.add_job(check_lessons, "interval", minutes=1)
    scheduler.start()
    print("Scheduler started - checking for reminders every minute (timezone-aware)")
