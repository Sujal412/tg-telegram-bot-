import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.error import TelegramError, BadRequest, Forbidden
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8080811246:AAHYceytHECmSlO8S7wgqd8Tb2H9WYQbz5o"
MAIN_CHANNEL_ID = "@studymaterial232"  # Using username instead of ID for better compatibility
CONTENT_CHANNEL_ID = -1002620628043  # fffffkkkdsa content channel ID
MAIN_CHANNEL_USERNAME = "@studymaterial232"
BOT_USERNAME = "study_mat342l_bot"  # Your bot username

media_store = {}
# Cache to store recent membership checks to avoid API spam
membership_cache = {}
CACHE_DURATION = 30  # seconds


async def check_membership_with_fallback(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Enhanced membership check with multiple strategies and caching"""

    # Check cache first
    cache_key = f"user_{user_id}"
    current_time = time.time()

    if cache_key in membership_cache:
        cached_time, cached_result = membership_cache[cache_key]
        if current_time - cached_time < CACHE_DURATION:
            logger.info(f"Using cached membership result for user {user_id}: {cached_result}")
            return cached_result

    logger.info(f"Starting comprehensive membership check for user {user_id}")

    # Strategy 1: Direct getChatMember with retries
    for attempt in range(4):  # Increased attempts
        try:
            member = await context.bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
            status = member.status
            logger.info(f"User {user_id} status: {status} (attempt {attempt + 1})")

            # Check for valid membership statuses
            if status in ["member", "administrator", "creator"]:
                membership_cache[cache_key] = (current_time, True)
                return True
            elif status in ["left", "kicked", "restricted"]:
                # If user left/kicked, they're definitely not a member
                membership_cache[cache_key] = (current_time, False)
                return False

            # Wait before retry, with increasing delays
            if attempt < 3:
                wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)

        except BadRequest as e:
            if "user not found" in str(e).lower():
                logger.error(f"User {user_id} not found: {e}")
                membership_cache[cache_key] = (current_time, False)
                return False
            logger.error(f"BadRequest error checking membership (attempt {attempt + 1}): {e}")
        except Forbidden as e:
            logger.error(f"Forbidden error - bot might not have access: {e}")
            # If bot doesn't have access, we can't verify membership
            # In this case, we might want to allow access or handle differently
            return False
        except TelegramError as e:
            logger.error(f"Telegram error checking membership (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking membership (attempt {attempt + 1}): {e}")

        if attempt < 3:
            await asyncio.sleep(2)

    # Strategy 2: Try alternative approach - check if user can receive messages
    # This is a fallback when getChatMember fails consistently
    try:
        logger.info(f"Trying alternative verification for user {user_id}")

        # Send a test message that we immediately delete
        # If user is not in channel, this will fail
        test_msg = await context.bot.send_message(
            chat_id=user_id,
            text="⚡ Verifying access...",
            disable_notification=True
        )
        await context.bot.delete_message(chat_id=user_id, message_id=test_msg.message_id)

        # If we got here, user exists and can receive messages
        # Now do a final membership check
        try:
            member = await context.bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
            is_member = member.status in ["member", "administrator", "creator"]
            membership_cache[cache_key] = (current_time, is_member)
            return is_member
        except:
            # If still failing, be more lenient for better UX
            logger.warning(f"Final membership check failed for user {user_id}, defaulting to False")
            membership_cache[cache_key] = (current_time, False)
            return False

    except Exception as e:
        logger.error(f"Alternative verification failed for user {user_id}: {e}")

    # All strategies failed
    logger.error(f"All membership verification strategies failed for user {user_id}")
    membership_cache[cache_key] = (current_time, False)
    return False


async def force_membership_refresh(user_id: int) -> None:
    """Force refresh of membership cache"""
    cache_key = f"user_{user_id}"
    if cache_key in membership_cache:
        del membership_cache[cache_key]
    logger.info(f"Cleared membership cache for user {user_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = context.args

    logger.info(f"Start command from user {user.id} (@{user.username}) with args: {args}")

    # Check if this is a media request
    if args and args[0].startswith("img"):
        image_id = args[0][3:]  # Remove 'img' prefix
        logger.info(f"Media request for ID: {image_id}")

        # Force refresh cache for this request
        await force_membership_refresh(user.id)

        # Check membership with enhanced method
        is_member = await check_membership_with_fallback(user.id, context)

        if not is_member:
            # Create inline keyboard with join button and check membership button
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MAIN_CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("✅ I Joined, Check Again", callback_data=f"check_membership_{image_id}")],
                [InlineKeyboardButton("🔄 Force Refresh", callback_data=f"force_check_{image_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🚫 **Access Denied!**\n\n"
                    f"You need to join {MAIN_CHANNEL_USERNAME} first to access this content.\n\n"
                    f"**Steps:**\n"
                    f"1️⃣ Click 'Join Channel'\n"
                    f"2️⃣ Join the channel\n"
                    f"3️⃣ Wait 10 seconds\n"
                    f"4️⃣ Click 'I Joined, Check Again'\n\n"
                    f"⚠️ If still not working, try 'Force Refresh'"
                ),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        # User is a member, send the content
        logger.info(f"User {user.id} verified as member, sending content...")
        await send_media_content(chat_id, image_id, context)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "👋 **Welcome to Study Material Bot!**\n\n"
                "Send me a valid content link to access media files.\n\n"
                f"Make sure you're a member of {MAIN_CHANNEL_USERNAME} first!\n\n"
                "🔗 Links look like: `/start img1`"
            ),
            parse_mode='Markdown'
        )


async def send_media_content(chat_id: int, image_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Send media content to user"""
    if image_id in media_store:
        media_type, file_id = media_store[image_id]
        try:
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption="📸 Here's your requested image! Thank you for being a member!"
                )
                logger.info(f"Successfully sent photo (ID: {image_id}) to user in chat {chat_id}")
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption="🎥 Here's your requested video! Thank you for being a member!"
                )
                logger.info(f"Successfully sent video (ID: {image_id}) to user in chat {chat_id}")
            else:
                await context.bot.send_message(chat_id=chat_id, text="❌ Unsupported media type.")
        except TelegramError as e:
            logger.error(f"Error sending media (ID: {image_id}): {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Error sending content. Please try again later or contact support."
            )
    else:
        logger.warning(f"Content not found for ID: {image_id}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Content not found or expired. Please get a new link from the channel."
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("check_membership_"):
        image_id = query.data.replace("check_membership_", "")
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        logger.info(f"Rechecking membership for user {user_id} for content ID: {image_id}")

        # Show "checking..." message
        await query.edit_message_text("🔄 **Checking membership...**\n\nPlease wait while we verify your status...",
                                      parse_mode='Markdown')

        # Wait a bit to let Telegram's systems update
        await asyncio.sleep(3)

        # Force refresh cache and check membership
        await force_membership_refresh(user_id)
        is_member = await check_membership_with_fallback(user_id, context)

        if is_member:
            await query.edit_message_text("✅ **Success!** Membership verified! Sending your content now...",
                                          parse_mode='Markdown')
            await send_media_content(chat_id, image_id, context)
        else:
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MAIN_CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("✅ I Joined, Check Again", callback_data=f"check_membership_{image_id}")],
                [InlineKeyboardButton("🔄 Force Refresh", callback_data=f"force_check_{image_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=(
                    f"❌ **Still Not Detected as Member**\n\n"
                    f"This can happen due to Telegram's caching. Please:\n\n"
                    f"1️⃣ Make sure you actually joined {MAIN_CHANNEL_USERNAME}\n"
                    f"2️⃣ Wait 30 seconds after joining\n"
                    f"3️⃣ Try 'Force Refresh' button\n"
                    f"4️⃣ If still failing, leave and rejoin the channel\n\n"
                    f"⚠️ **Note:** Telegram sometimes takes time to update membership status."
                ),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    elif query.data.startswith("force_check_"):
        image_id = query.data.replace("force_check_", "")
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        logger.info(f"Force checking membership for user {user_id}")

        await query.edit_message_text("🔄 **Force Refreshing...**\n\nClearing cache and doing deep verification...",
                                      parse_mode='Markdown')

        # Clear all cache for this user
        await force_membership_refresh(user_id)

        # Wait longer for force refresh
        await asyncio.sleep(5)

        # Do comprehensive check
        is_member = await check_membership_with_fallback(user_id, context)

        if is_member:
            await query.edit_message_text("🎉 **Force Refresh Successful!** Sending content...", parse_mode='Markdown')
            await send_media_content(chat_id, image_id, context)
        else:
            # Last resort - show debug info
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{MAIN_CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("🆘 Contact Support", url="https://t.me/YOURSUPPORTUSERNAME")]
                # Replace with your support
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=(
                    f"❌ **Force Refresh Failed**\n\n"
                    f"We still can't detect your membership in {MAIN_CHANNEL_USERNAME}.\n\n"
                    f"**Possible solutions:**\n"
                    f"• Leave the channel completely\n"
                    f"• Wait 2 minutes\n"
                    f"• Join again\n"
                    f"• Try again after 5 minutes\n\n"
                    f"**Or contact support with your User ID:** `{user_id}`"
                ),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media messages in content channel"""
    message = update.effective_message
    chat = update.effective_chat

    # Only process messages from the content channel
    if chat.id != CONTENT_CHANNEL_ID:
        logger.warning(f"Received media from unauthorized chat: {chat.id}")
        return

    # Generate unique media index
    media_index = str(len(media_store) + 1)

    # Store media information
    if message.photo:
        file_id = message.photo[-1].file_id  # Get highest quality photo
        media_store[media_index] = ("photo", file_id)
        media_type = "📸 Photo"
        logger.info(f"Stored photo with ID: {media_index}")
    elif message.video:
        file_id = message.video.file_id
        media_store[media_index] = ("video", file_id)
        media_type = "🎥 Video"
        logger.info(f"Stored video with ID: {media_index}")
    else:
        logger.warning("Received unsupported media type")
        return  # Not a supported media type

    # Create link using your bot username
    link = f"https://t.me/{BOT_USERNAME}?start=img{media_index}"

    # Send the link back to content channel with better formatting
    await context.bot.send_message(
        chat_id=CONTENT_CHANNEL_ID,
        text=(
            f"🔗 **New Content Generated!**\n\n"
            f"📋 **Details:**\n"
            f"• Type: {media_type}\n"
            f"• ID: `{media_index}`\n"
            f"• Status: ✅ Ready\n"
            f"• Timestamp: {time.strftime('%H:%M:%S')}\n\n"
            f"🔗 **Share Link:**\n`{link}`\n\n"
            f"👆 Copy this link and share it in your main channel!"
        ),
        parse_mode='Markdown'
    )

    logger.info(f"Generated and sent link for {media_type.lower()} (ID: {media_index}): {link}")


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced debug command"""
    chat = update.effective_chat
    user = update.effective_user

    debug_info = f"🔧 **Debug Information**\n\n"
    debug_info += f"**Chat Details:**\n"
    debug_info += f"• Chat ID: `{chat.id}`\n"
    debug_info += f"• Chat Type: `{chat.type}`\n"
    debug_info += f"• Chat Title: {getattr(chat, 'title', 'N/A')}\n\n"
    debug_info += f"**User Details:**\n"
    debug_info += f"• User ID: `{user.id}`\n"
    debug_info += f"• Username: @{user.username or 'None'}\n"
    debug_info += f"• First Name: {user.first_name}\n\n"
    debug_info += f"**Bot Status:**\n"
    debug_info += f"• Media Store Size: {len(media_store)}\n"
    debug_info += f"• Cache Entries: {len(membership_cache)}\n"
    debug_info += f"• Main Channel: {MAIN_CHANNEL_USERNAME}\n"
    debug_info += f"• Content Channel ID: `{CONTENT_CHANNEL_ID}`\n"

    # Enhanced membership check for private chats
    if chat.type == 'private':
        try:
            debug_info += f"\n**🔍 Membership Check:**\n"
            start_time = time.time()
            is_member = await check_membership_with_fallback(user.id, context)
            check_time = time.time() - start_time
            debug_info += f"• Status: {'✅ Member' if is_member else '❌ Not Member'}\n"
            debug_info += f"• Check Time: {check_time:.2f}s\n"

            # Show cache status
            cache_key = f"user_{user.id}"
            if cache_key in membership_cache:
                cached_time, cached_result = membership_cache[cache_key]
                age = time.time() - cached_time
                debug_info += f"• Cache Status: ✅ Cached ({age:.1f}s old)\n"
            else:
                debug_info += f"• Cache Status: ❌ Not Cached\n"

        except Exception as e:
            debug_info += f"• Membership Check: ❌ Error - {str(e)}\n"

    await update.message.reply_text(debug_info, parse_mode='Markdown')


async def test_channel_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test if bot can access the main channel"""
    try:
        # Try to get channel info
        chat_info = await context.bot.get_chat(MAIN_CHANNEL_ID)

        # Try to get administrators
        admins = await context.bot.get_chat_administrators(MAIN_CHANNEL_ID)
        bot_is_admin = any(admin.user.id == context.bot.id for admin in admins)

        result = f"🔍 **Channel Access Test**\n\n"
        result += f"✅ **Channel Found!**\n"
        result += f"• Title: {chat_info.title}\n"
        result += f"• Type: {chat_info.type}\n"
        result += f"• ID: `{chat_info.id}`\n"
        result += f"• Members: {getattr(chat_info, 'member_count', 'Unknown')}\n"
        result += f"• Bot is Admin: {'✅ Yes' if bot_is_admin else '❌ No'}\n"

        await update.message.reply_text(result, parse_mode='Markdown')

    except BadRequest as e:
        await update.message.reply_text(
            f"❌ **Channel Access Failed**\n\n"
            f"Error: `{str(e)}`\n\n"
            f"**Solutions:**\n"
            f"1. Add bot to {MAIN_CHANNEL_USERNAME} as admin\n"
            f"2. Give bot 'Read Messages' permission\n"
            f"3. Make sure channel username is correct",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Unexpected error: `{str(e)}`", parse_mode='Markdown')


async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear membership cache"""
    cache_size = len(membership_cache)
    membership_cache.clear()

    await update.message.reply_text(
        f"🗑️ **Cache Cleared!**\n\nRemoved {cache_size} cached entries.",
        parse_mode='Markdown'
    )
    logger.info(f"Cleared {cache_size} cache entries")


if __name__ == "__main__":
    # Create application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(
        filters.Chat(CONTENT_CHANNEL_ID) & (filters.PHOTO | filters.VIDEO),
        handle_media
    ))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("testchannel", test_channel_access))
    app.add_handler(CommandHandler("clearcache", clear_cache))

    logger.info("🤖 Enhanced Bot started successfully!")
    logger.info(f"📢 Main Channel: {MAIN_CHANNEL_USERNAME} (ID: {MAIN_CHANNEL_ID})")
    logger.info(f"📁 Content Channel ID: {CONTENT_CHANNEL_ID}")
    logger.info(f"🔗 Bot Username: @{BOT_USERNAME}")
    logger.info("✅ Enhanced membership checking enabled!")

    # Start polling
    app.run_polling()