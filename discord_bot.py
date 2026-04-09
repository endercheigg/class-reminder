# -*- coding: utf-8 -*-
import re
from datetime import datetime, timedelta
import discord
from discord import app_commands
from database import (
    add_class, get_user_classes, get_linked_ids, delete_class, link_user,
    move_class_temp, get_class_by_name, create_share_code, consume_share_code,
    get_user_timezone, set_user_timezone, get_all_classes_by_owner
)
from link_codes import consume_code
from timezone_utils import validate_timezone, local_to_utc, utc_to_local

DAYS = {
    1: "Monday",  2: "Tuesday", 3: "Wednesday",
    4: "Thursday",5: "Friday",  6: "Saturday",  7: "Sunday",
}


def setup_discord_handlers(client):

    tree = app_commands.CommandTree(client)

    @client.event
    async def on_ready():
        await tree.sync()
        print(f"Discord bot logged in as {client.user}")

    # ── /help ─────────────────────────────────────────────────────────────────

    @tree.command(name="help", description="Show available commands")
    async def help_command(interaction: discord.Interaction):
        await interaction.response.send_message(
            "📖 **Commands:**\n\n"
            "`/add` — Add a class\n"
            "`/schedule` — Show all your classes\n"
            "`/next` — Show your next upcoming class\n"
            "`/delete` — Delete a class by name\n"
            "`/move` — Move a class to a different time (just for this week)\n"
            "`/config` — Generate a share code (use `\\@` for all classes)\n"
            "`/join` — Join a shared class using a code\n"
            "`/sync` — Link this Discord account to your Telegram account\n"
            "`/timezone` — Set your local timezone\n"
            "`/help` — Show this message",
            ephemeral=True
        )

    # ── /timezone ─────────────────────────────────────────────────────────────

    @tree.command(name="timezone", description="Set your local timezone")
    async def set_timezone(interaction: discord.Interaction, timezone: str):
        if not validate_timezone(timezone):
            await interaction.response.send_message(
                "❌ Invalid timezone. Example: `America/New_York`\n"
                "See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                ephemeral=True
            )
            return
        dc = str(interaction.user.id)
        set_user_timezone(dc=dc, tz=timezone)
        await interaction.response.send_message(f"✅ Timezone set to `{timezone}`", ephemeral=True)

    # ── /sync ─────────────────────────────────────────────────────────────────

    @tree.command(name="sync", description="Link your Discord account to Telegram. Get a code via /link in Telegram first.")
    async def sync(interaction: discord.Interaction, code: str):
        tg = consume_code(code)

        if tg is None:
            await interaction.response.send_message(
                "❌ Invalid or expired code.\n"
                "Run `/link` in Telegram to get a fresh one (valid for 5 minutes).",
                ephemeral=True
            )
            return

        dc = str(interaction.user.id)
        
        print(f"Linking Telegram ID: {tg} with Discord ID: {dc}")
        
        try:
            link_user(tg, dc)
            
            verification = get_linked_ids(dc=dc)
            if verification and verification[0] == tg:
                await interaction.response.send_message(
                    "✅ Accounts linked! Your classes are now synced between Telegram and Discord.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ There was an issue linking your accounts. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"Error linking: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while linking. Please try again.",
                ephemeral=True
            )

    # ── /add ──────────────────────────────────────────────────────────────────

    @tree.command(name="add", description="Add a class. Day: 1=Mon … 7=Sun, Time: HH:MM (your local time)")
    async def add(interaction: discord.Interaction, lesson: str, day: int, time: str):

        if day < 1 or day > 7:
            await interaction.response.send_message("Day must be between 1 and 7.", ephemeral=True)
            return

        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", time):
            await interaction.response.send_message("Time must be in HH:MM format.", ephemeral=True)
            return

        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        tz = get_user_timezone(dc=dc)

        utc_day, utc_time = local_to_utc(time, day, tz)
        add_class(lesson, utc_day, utc_time, tg, dc)

        await interaction.response.send_message(
            f"✅ Added: {lesson} — {DAYS[day]} at {time} (your local time)"
        )

    # ── /move ─────────────────────────────────────────────────────────────────

    @tree.command(name="move", description="Move a class to a different time (just for this week)")
    async def move(interaction: discord.Interaction, lesson: str, day: int, time: str):

        if day < 1 or day > 7:
            await interaction.response.send_message("Day must be between 1 and 7.", ephemeral=True)
            return

        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", time):
            await interaction.response.send_message("Time must be in HH:MM format.", ephemeral=True)
            return

        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        tz = get_user_timezone(dc=dc)

        class_info = get_class_by_name(lesson, dc=dc)
        if not class_info:
            await interaction.response.send_message(
                f"❌ Class '{lesson}' not found. Use `/schedule` to see your classes.",
                ephemeral=True
            )
            return

        utc_day, utc_time = local_to_utc(time, day, tz)
        success = move_class_temp(lesson, utc_day, utc_time, tg, dc)
        
        if success:
            await interaction.response.send_message(
                f"🕐 **Moved for this week only!**\n"
                f"• {lesson} — {DAYS[day]} at {time} (your local time)\n\n"
                f"_Next week it will return to its original time._"
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to move the class. Please try again.",
                ephemeral=True
            )

    # ── /config ───────────────────────────────────────────────────────────────

    @tree.command(name="config", description="Generate a share code (use \\@ for all classes)")
    async def config(interaction: discord.Interaction, lesson: str, expires_in_hours: int = 24):
        """
        Usage:
        - /config Math          → share only the class "Math"
        - /config \\@            → share ALL your classes with one code
        - /config Math 48       → share Math with 48 hour expiry
        """
        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        
        is_all_classes = (lesson == "\\@")
        
        if not is_all_classes:
            class_info = get_class_by_name(lesson, dc=dc)
            if not class_info:
                await interaction.response.send_message(
                    f"❌ Class '{lesson}' not found. Use `/schedule` to see your classes.",
                    ephemeral=True
                )
                return
            display_name = lesson
        else:
            all_classes = get_all_classes_by_owner(owner_dc=dc)
            if not all_classes:
                await interaction.response.send_message(
                    "❌ You have no classes to share. Add some with `/add` first.",
                    ephemeral=True
                )
                return
            display_name = "ALL your classes"
        
        if expires_in_hours < 1 or expires_in_hours > 168:
            await interaction.response.send_message(
                "❌ Expiration must be between 1 and 168 hours (1 week).",
                ephemeral=True
            )
            return
        
        code = create_share_code(tg, dc, "__ALL__" if is_all_classes else lesson, expires_in_hours)
        
        await interaction.response.send_message(
            f"🔗 **Share Code Generated!**\n\n"
            f"Sharing: **{display_name}**\n"
            f"Code: `{code}`\n"
            f"Expires in: {expires_in_hours} hours\n\n"
            f"Share this code. Others can use `/join {code}` to add **{'all your classes' if is_all_classes else lesson}** to their schedule.",
            ephemeral=True
        )

    # ── /join ─────────────────────────────────────────────────────────────────

    @tree.command(name="join", description="Join a shared class using a code from /config")
    async def join(interaction: discord.Interaction, code: str):
        
        share_data = consume_share_code(code)
        
        if not share_data:
            await interaction.response.send_message(
                "❌ Invalid or expired code.",
                ephemeral=True
            )
            return
        
        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        tz = get_user_timezone(dc=dc)
        
        owner_tg = share_data["owner_tg"]
        owner_dc = share_data["owner_dc"]
        lesson_name = share_data["lesson_name"]
        
        # Special case: "__ALL__" means add all classes of the owner
        if lesson_name == "__ALL__":
            all_classes = get_all_classes_by_owner(owner_tg=owner_tg, owner_dc=owner_dc)
            if not all_classes:
                await interaction.response.send_message(
                    "❌ The owner has no classes to share anymore.",
                    ephemeral=True
                )
                return
            
            added_count = 0
            for class_lesson, class_day, class_time in all_classes:
                existing = get_user_classes(tg, dc)
                already_has = any(c[1] == class_lesson for c in existing)
                if not already_has:
                    add_class(class_lesson, class_day, class_time, tg, dc)
                    added_count += 1
            
            if added_count == 0:
                await interaction.response.send_message(
                    "ℹ️ You already have all those classes.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ **Added {added_count} classes!**\n\n"
                    f"You've joined all classes shared by the owner.\n"
                    f"Use `/schedule` to see them.",
                    ephemeral=True
                )
            return
        
        # Normal single class sharing
        conn = __import__('sqlite3').connect("classes.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT lesson_day, lesson_time FROM classes WHERE lesson_name=? AND (telegram_id=? OR discord_id=?)",
            (lesson_name, owner_tg, owner_dc)
        )
        class_row = cur.fetchone()
        conn.close()
        
        if not class_row:
            await interaction.response.send_message(
                "❌ The shared class no longer exists.",
                ephemeral=True
            )
            return
        
        utc_day, utc_time = class_row
        
        add_class(lesson_name, utc_day, utc_time, tg, dc)
        
        local_day, local_time = utc_to_local(utc_day, utc_time, tz)
        await interaction.response.send_message(
            f"✅ **Class Added!**\n\n"
            f"You've joined: **{lesson_name}** — {DAYS[local_day]} at {local_time} (your local time)",
            ephemeral=True
        )

    # ── /schedule ─────────────────────────────────────────────────────────────

    @tree.command(name="schedule", description="Show your classes")
    async def schedule(interaction: discord.Interaction):

        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        tz = get_user_timezone(dc=dc)

        classes = get_user_classes(tg, dc)

        if not classes:
            await interaction.response.send_message("No classes saved.")
            return

        text = "📅 **Your classes:**\n\n"
        local_classes = []
        for class_id, lesson, utc_day, utc_time, class_type in classes:
            local_day, local_time = utc_to_local(utc_day, utc_time, tz)
            local_classes.append((local_day, local_time, lesson, class_type))
        
        for local_day, local_time, lesson, class_type in sorted(local_classes, key=lambda x: (x[0], x[1])):
            prefix = "🕐 " if class_type == "temp" else "• "
            if class_type == "temp":
                text += f"{prefix} {lesson} — {DAYS[local_day]} at {local_time} _(moved for this week only)_\n"
            else:
                text += f"{prefix} {lesson} — {DAYS[local_day]} at {local_time}\n"

        await interaction.response.send_message(text)

    # ── /next ─────────────────────────────────────────────────────────────────

    @tree.command(name="next", description="Show your next upcoming class")
    async def next_class(interaction: discord.Interaction):

        dc = str(interaction.user.id)
        ids = get_linked_ids(dc=dc)
        tg = ids[0] if ids else "none"
        tz = get_user_timezone(dc=dc)

        classes = get_user_classes(tg, dc)

        if not classes:
            await interaction.response.send_message("No classes saved.")
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
            await interaction.response.send_message("Could not determine the next class.")
            return

        lesson, day, time, class_type = best
        hours, mins = divmod(int(best_minutes), 60)
        
        move_note = " _(moved for this week)_" if class_type == "temp" else ""

        await interaction.response.send_message(
            f"⏭ **Next class:** {lesson}{move_note}\n"
            f"📅 {DAYS[day]} at {time}\n"
            f"⏱ In {hours}h {mins}m"
        )

    # ── /delete ───────────────────────────────────────────────────────────────

    @tree.command(name="delete", description="Delete a class by name")
    async def delete(interaction: discord.Interaction, lesson: str):

        dc = str(interaction.user.id)
        delete_class(lesson, dc=dc)
        await interaction.response.send_message(f"🗑 Deleted class: {lesson}")