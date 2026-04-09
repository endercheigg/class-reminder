import re
from datetime import datetime, timedelta
from database import (
    add_class, get_user_classes, get_linked_ids, delete_class,
    move_class_temp, get_class_by_name, create_share_code, consume_share_code,
    get_user_timezone, set_user_timezone, get_all_classes_by_owner
)
from link_codes import generate_code
from timezone_utils import validate_timezone, local_to_utc, utc_to_local

DAYS = {
    "1": "Monday",  "2": "Tuesday", "3": "Wednesday",
    "4": "Thursday","5": "Friday",  "6": "Saturday", "7": "Sunday",
}


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update, context):
    await update.message.reply_text(
        "👋 Hello! I'm your class reminder bot.\n\n"
        "Use /help to see available commands.\n"
        "Use /timezone to set your local time zone."
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def help_command(update, context):
    await update.message.reply_text(
        "📖 **Commands:**\n\n"
        "/add [lesson day time] — Add a class\n"
        "/schedule — Show all your classes\n"
        "/next — Show your next upcoming class\n"
        "/delete <lesson name> — Delete a class\n"
        "/move <lesson> <day> <time> — Move a class (just for this week)\n"
        "/config <lesson> [hours] — Generate a code (use \\@ for all classes)\n"
        "/join <code> — Join a shared class\n"
        "/link — Get a code to sync with Discord\n"
        "/timezone <zone> — Set your local timezone\n"
        "/help — Show this message"
    )


# ── /timezone ─────────────────────────────────────────────────────────────────

async def timezone_command(update, context):
    """Set your local timezone"""
    if not context.args:
        await update.message.reply_text(
            "🌍 **Set your timezone**\n\n"
            "Usage: `/timezone <zone>`\n"
            "Example: `/timezone America/New_York`\n\n"
            "Common timezones:\n"
            "• America/New_York\n"
            "• America/Los_Angeles\n"
            "• Europe/London\n"
            "• Asia/Tokyo\n"
            "• Australia/Sydney\n\n"
            "Find yours at https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            parse_mode="Markdown"
        )
        return
    
    tz_name = " ".join(context.args)
    if not validate_timezone(tz_name):
        await update.message.reply_text("❌ Invalid timezone. Check spelling and try again.")
        return
    
    tg = str(update.message.from_user.id)
    set_user_timezone(tg=tg, tz=tz_name)
    await update.message.reply_text(f"✅ Timezone set to `{tz_name}`. All times will now show in your local time.", parse_mode="Markdown")


# ── /link ─────────────────────────────────────────────────────────────────────

async def link(update, context):
    tg = str(update.message.from_user.id)
    code = generate_code(tg)
    await update.message.reply_text(
        f"🔗 Your link code: <code>{code}</code>\n\n"
        "Go to Discord and run:\n"
        f"<code>/sync {code}</code>\n\n"
        "⏳ This code expires in 5 minutes.",
        parse_mode="HTML"
    )


# ── /move ─────────────────────────────────────────────────────────────────────

async def move(update, context):
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /move <lesson name> <day (1-7)> <time (HH:MM)>\n"
            "Example: /move Math 3 14:00\n\n"
            "This moves the class just for this week only!"
        )
        return
    
    lesson = " ".join(context.args[:-2])
    day = context.args[-2]
    time = context.args[-1]
    
    if day not in DAYS:
        await update.message.reply_text("Day must be 1–7.")
        return
    if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", time):
        await update.message.reply_text("Time must be HH:MM.")
        return
    
    tg = str(update.message.from_user.id)
    ids = get_linked_ids(tg=tg)
    dc = ids[1] if ids else "none"
    tz = get_user_timezone(tg=tg)
    
    class_info = get_class_by_name(lesson, tg=tg)
    if not class_info:
        await update.message.reply_text(f"❌ Class '{lesson}' not found. Use /schedule to see your classes.")
        return
    
    utc_day, utc_time = local_to_utc(time, int(day), tz)
    success = move_class_temp(lesson, utc_day, utc_time, tg, dc)
    
    if success:
        await update.message.reply_text(
            f"🕐 **Moved for this week only!**\n"
            f"• {lesson} — {DAYS[day]} at {time} (your local time)\n\n"
            f"_Next week it will return to its original time._"
        )
    else:
        await update.message.reply_text("❌ Failed to move the class. Please try again.")


# ── /config ───────────────────────────────────────────────────────────────────

async def config(update, context):
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage:\n"
            "/config <lesson name> [hours] – share one class\n"
            "/config \\@ [hours] – share ALL your classes\n\n"
            "Example: /config Math 24\n"
            "Example: /config \\@ 48"
        )
        return
    
    # Check if first argument is the special token "\@"
    first_arg = context.args[0]
    is_all_classes = (first_arg == "\\@")
    
    if is_all_classes:
        lesson = "__ALL__"
        expires_in_hours = 24
        if len(context.args) >= 2 and context.args[1].isdigit():
            expires_in_hours = int(context.args[1])
    else:
        # Normal: lesson name may be multiple words
        lesson = " ".join(context.args)
        expires_in_hours = 24
        if len(context.args) >= 2 and context.args[-1].isdigit():
            lesson = " ".join(context.args[:-1])
            expires_in_hours = int(context.args[-1])
    
    tg = str(update.message.from_user.id)
    ids = get_linked_ids(tg=tg)
    dc = ids[1] if ids else "none"
    
    if not is_all_classes:
        class_info = get_class_by_name(lesson, tg=tg)
        if not class_info:
            await update.message.reply_text(f"❌ Class '{lesson}' not found. Use /schedule to see your classes.")
            return
        display_name = lesson
    else:
        all_classes = get_all_classes_by_owner(owner_tg=tg)
        if not all_classes:
            await update.message.reply_text("❌ You have no classes to share. Add some with /add first.")
            return
        display_name = "ALL your classes"
    
    if expires_in_hours < 1 or expires_in_hours > 168:
        await update.message.reply_text("❌ Expiration must be between 1 and 168 hours (1 week).")
        return
    
    code = create_share_code(tg, dc, "__ALL__" if is_all_classes else lesson, expires_in_hours)
    
    await update.message.reply_text(
        f"🔗 **Share Code Generated!**\n\n"
        f"Sharing: **{display_name}**\n"
        f"Code: <code>{code}</code>\n"
        f"Expires in: {expires_in_hours} hours\n\n"
        f"Share this code. Others can use /join {code} to add **{'all your classes' if is_all_classes else lesson}** to their schedule.",
        parse_mode="HTML"
    )


# ── /join ─────────────────────────────────────────────────────────────────────

async def join(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /join <code>")
        return
    
    code = context.args[0]
    share_data = consume_share_code(code)
    
    if not share_data:
        await update.message.reply_text("❌ Invalid or expired code.")
        return
    
    tg = str(update.message.from_user.id)
    ids = get_linked_ids(tg=tg)
    dc = ids[1] if ids else "none"
    tz = get_user_timezone(tg=tg)
    
    owner_tg = share_data["owner_tg"]
    owner_dc = share_data["owner_dc"]
    lesson_name = share_data["lesson_name"]
    
    # Special case: "__ALL__" means add all classes of the owner
    if lesson_name == "__ALL__":
        all_classes = get_all_classes_by_owner(owner_tg=owner_tg, owner_dc=owner_dc)
        if not all_classes:
            await update.message.reply_text("❌ The owner has no classes to share anymore.")
            return
        
        added_count = 0
        for class_lesson, class_day, class_time in all_classes:
            existing = get_user_classes(tg, dc)
            already_has = any(c[1] == class_lesson for c in existing)
            if not already_has:
                add_class(class_lesson, class_day, class_time, tg, dc)
                added_count += 1
        
        if added_count == 0:
            await update.message.reply_text("ℹ️ You already have all those classes.")
        else:
            await update.message.reply_text(
                f"✅ **Added {added_count} classes!**\n\n"
                f"You've joined all classes shared by the owner.\n"
                f"Use /schedule to see them."
            )
        return
    
    # Normal single class
    import sqlite3
    conn = sqlite3.connect("classes.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT lesson_day, lesson_time FROM classes WHERE lesson_name=? AND (telegram_id=? OR discord_id=?)",
        (lesson_name, owner_tg, owner_dc)
    )
    class_row = cur.fetchone()
    conn.close()
    
    if not class_row:
        await update.message.reply_text("❌ The shared class no longer exists.")
        return
    
    utc_day, utc_time = class_row
    
    add_class(lesson_name, utc_day, utc_time, tg, dc)
    
    local_day, local_time = utc_to_local(utc_day, utc_time, tz)
    await update.message.reply_text(
        f"✅ **Class Added!**\n\n"
        f"You've joined: **{lesson_name}** — {DAYS[str(local_day)]} at {local_time} (your local time)"
    )


# ── /next ─────────────────────────────────────────────────────────────────────

async def next_class(update, context):
    tg = str(update.message.from_user.id)
    ids = get_linked_ids(tg=tg)
    dc = ids[1] if ids else "none"
    tz = get_user_timezone(tg=tg)

    classes = get_user_classes(tg, dc)

    if not classes:
        await update.message.reply_text("No classes saved.")
        return

    now_local = datetime.now()
    best = None
    best_minutes = None

    for class_id, lesson, utc_day, utc_time, class_type in classes:
        local_day, local_time = utc_to_local(utc_day, utc_time, tz)
        try:
            lesson_dt = datetime.strptime(local_time, "%H:%M")
        except ValueError:
            continue

        days_ahead = (local_day - now_local.isoweekday()) % 7
        candidate = now_local.replace(
            hour=lesson_dt.hour, minute=lesson_dt.minute, second=0, microsecond=0
        ) + timedelta(days=days_ahead)

        if candidate <= now_local:
            candidate += timedelta(weeks=1)

        minutes_until = (candidate - now_local).total_seconds() / 60

        if best_minutes is None or minutes_until < best_minutes:
            best_minutes = minutes_until
            best = (lesson, local_day, local_time, class_type)

    if not best:
        await update.message.reply_text("Could not determine the next class.")
        return

    lesson, day, time, class_type = best
    hours, mins = divmod(int(best_minutes), 60)
    move_note = " _(moved for this week)_" if class_type == "temp" else ""
    
    await update.message.reply_text(
        f"⏭ Next class: {lesson}{move_note}\n"
        f"📅 {DAYS.get(str(day), 'day ' + str(day))} at {time}\n"
        f"⏱ In {hours}h {mins}m"
    )


# ── /delete ───────────────────────────────────────────────────────────────────

async def delete(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /delete <lesson name>")
        return

    lesson = " ".join(context.args)
    tg = str(update.message.from_user.id)
    delete_class(lesson, tg=tg)
    await update.message.reply_text(f"🗑 Deleted class: {lesson}")


# ── /schedule ─────────────────────────────────────────────────────────────────

async def schedule(update, context):
    tg = str(update.message.from_user.id)
    ids = get_linked_ids(tg=tg)
    dc = ids[1] if ids else "none"
    tz = get_user_timezone(tg=tg)

    classes = get_user_classes(tg, dc)

    if not classes:
        await update.message.reply_text("No classes saved.")
        return

    text = "📅 Your classes:\n\n"
    local_classes = []
    for class_id, lesson, utc_day, utc_time, class_type in classes:
        local_day, local_time = utc_to_local(utc_day, utc_time, tz)
        local_classes.append((local_day, local_time, lesson, class_type))
    
    for local_day, local_time, lesson, class_type in sorted(local_classes, key=lambda x: (x[0], x[1])):
        prefix = "🕐 " if class_type == "temp" else "• "
        if class_type == "temp":
            text += f"{prefix} {lesson} — {DAYS[str(local_day)]} at {local_time} _(moved for this week only)_\n"
        else:
            text += f"{prefix} {lesson} — {DAYS[str(local_day)]} at {local_time}\n"

    await update.message.reply_text(text)


# ── /add (interactive flow) ───────────────────────────────────────────────────

async def handle_message(update, context):
    step = context.user_data.get("step")

    if step == "lesson_name":
        context.user_data["lesson"] = update.message.text
        context.user_data["step"] = "lesson_day"
        await update.message.reply_text("What day is the lesson? (1=Mon … 7=Sun)")
        return

    if step == "lesson_day":
        day = update.message.text
        if day not in DAYS:
            await update.message.reply_text("Please enter a number from 1 to 7.")
            return
        context.user_data["day"] = day
        context.user_data["step"] = "lesson_time"
        await update.message.reply_text("What time does the lesson start? (HH:MM) (your local time)")
        return

    if step == "lesson_time":
        time = update.message.text
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", time):
            await update.message.reply_text("Time must be in HH:MM format.")
            return

        lesson = context.user_data["lesson"]
        local_day = context.user_data["day"]
        tg = str(update.message.from_user.id)
        ids = get_linked_ids(tg=tg)
        dc = ids[1] if ids else "none"
        tz = get_user_timezone(tg=tg)

        utc_day, utc_time = local_to_utc(time, int(local_day), tz)
        add_class(lesson, utc_day, utc_time, tg, dc)
        
        await update.message.reply_text(
            f"✅ Added: {lesson} — {DAYS[local_day]} at {time} (your local time)\n"
            f"_Stored in UTC, will show correctly in any timezone._"
        )
        context.user_data.clear()
        return


async def add(update, context):
    # Quick add: /add Math 3 14:00
    if len(context.args) >= 3:
        lesson = " ".join(context.args[:-2])
        local_day = context.args[-2]
        local_time = context.args[-1]

        if local_day not in DAYS:
            await update.message.reply_text("Day must be 1–7.")
            return
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", local_time):
            await update.message.reply_text("Time must be HH:MM.")
            return

        tg = str(update.message.from_user.id)
        ids = get_linked_ids(tg=tg)
        dc = ids[1] if ids else "none"
        tz = get_user_timezone(tg=tg)

        utc_day, utc_time = local_to_utc(local_time, int(local_day), tz)
        add_class(lesson, utc_day, utc_time, tg, dc)
        
        await update.message.reply_text(
            f"✅ Added: {lesson} — {DAYS[local_day]} at {local_time} (your local time)"
        )
        return

    # Interactive
    context.user_data["step"] = "lesson_name"
    await update.message.reply_text("What is the lesson name?")