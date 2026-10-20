
import os
import re
from collections import defaultdict, deque
from time import time

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
WARNINGS = defaultdict(int)
RECENT = defaultdict(lambda: deque(maxlen=10))
ALLOWED = set()

LINK_RE = re.compile(
    r"https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+",
    re.IGNORECASE,
)


async def admin(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "سلام! من اریکس هستم 🤖\n"
        "برای راهنما /help را بزن."
    )


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "/status - وضعیت ربات\n"
        "/allow example.com - مجازکردن دامنه\n"
        "/unallow example.com - حذف دامنه مجاز\n"
        "/warn - اخطار با ریپلای به پیام کاربر\n"
        "/mute 10 - محدودکردن کاربر با ریپلای\n"
        "/resetwarn - پاک‌کردن اخطار با ریپلای"
    )


async def status(update, context):
    await update.effective_message.reply_text(
        f"اریکس فعاله ✅ | دامنه‌های مجاز: {len(ALLOWED)}"
    )


async def moderate(update, context):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or await admin(update, context):
        return

    text = msg.text or msg.caption or ""

    for match in LINK_RE.findall(text):
        url = match.lower().rstrip(".,!?)")
        domain = re.sub(r"^https?://", "", url)
        domain = re.sub(r"^www\.", "", domain).split("/")[0]

        if not any(
            domain == d or domain.endswith("." + d)
            for d in ALLOWED
        ):
            try:
                await msg.delete()
                await context.bot.send_message(
                    chat.id, f"⚠️ {user.first_name}، ارسال لینک مجاز نیست."
                )
            except Exception:
                pass
            return

    now = time()
    key = (chat.id, user.id)
    queue = RECENT[key]

    while queue and now - queue[0][0] > 20:
        queue.popleft()

    if text and sum(old == text for _, old in queue) >= 2:
        try:
            await msg.delete()
        except Exception:
            pass
        return

    queue.append((now, text))


async def admin_only(update, context):
    if not await admin(update, context):
        await update.effective_message.reply_text("این دستور فقط برای ادمین‌هاست.")
        return False
    return True


async def allow_domain(update, context):
    if not await admin_only(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("مثال: /allow example.com")
        return
    domain = context.args[0].lower().strip()
    domain = re.sub(r"^https?://", "", domain).split("/")[0]
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        await update.effective_message.reply_text("دامنه معتبر نیست.")
        return
    ALLOWED.add(domain)
    await update.effective_message.reply_text(f"دامنه {domain} مجاز شد.")


async def unallow_domain(update, context):
    if not await admin_only(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("مثال: /unallow example.com")
        return
    domain = context.args[0].lower().strip()
    ALLOWED.discard(domain)
    await update.effective_message.reply_text(f"دامنه {domain} از فهرست مجاز حذف شد.")


async def warn(update, context):
    if not await admin_only(update, context):
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("روی پیام کاربر ریپلای کن و /warn بزن.")
        return
    target = msg.reply_to_message.from_user
    if not target or target.is_bot:
        return
    key = (update.effective_chat.id, target.id)
    WARNINGS[key] += 1
    await msg.reply_text(f"{target.first_name}: اخطار {WARNINGS[key]} از 3")
    if WARNINGS[key] >= 3:
        await msg.reply_text("این کاربر ۳ اخطار گرفته است.")


async def resetwarn(update, context):
    if not await admin_only(update, context):
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("روی پیام کاربر ریپلای کن.")
        return
    target = msg.reply_to_message.from_user
    if target:
        WARNINGS.pop((update.effective_chat.id, target.id), None)
        await msg.reply_text("اخطارهای کاربر پاک شد.")


async def mute(update, context):
    if not await admin_only(update, context):
        return
    msg = update.effective_message
    if not msg.reply_to_message or not context.args:
        await msg.reply_text("روی پیام کاربر ریپلای کن و /mute 10 بزن.")
        return
    try:
        minutes = int(context.args[0])
        if not 1 <= minutes <= 1440:
            raise ValueError
        target = msg.reply_to_message.from_user
        if not target or target.is_bot:
            return
        from datetime import datetime, timedelta, timezone
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
        await msg.reply_text(f"{target.first_name} برای {minutes} دقیقه محدود شد.")
    except ValueError:
        await msg.reply_text("مدت باید بین 1 تا 1440 دقیقه باشد.")
    except Exception:
        await msg.reply_text("محدودسازی ناموفق بود؛ دسترسی‌های ربات را بررسی کن.")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("allow", allow_domain))
    app.add_handler(CommandHandler("unallow", unallow_domain))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("resetwarn", resetwarn))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & (filters.TEXT | filters.CAPTION)
            & ~filters.COMMAND,
            moderate,
        )
    )
    app.run_polling()


if __name__ == "__main__":
    main()
