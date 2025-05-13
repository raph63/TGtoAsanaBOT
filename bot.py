import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
import asana
import openai
import threading
import time
import warnings
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

# Initialize clients
asana_client = asana.Client.access_token(os.getenv('ASANA_PAT'))
asana_client.options['headers'] = {
    "Asana-Enable": "new_user_task_lists,new_goal_memberships"
}
openai.api_key = os.getenv('OPENAI_API_KEY')

# Get project configuration
PROJECT_IDS = os.getenv('ASANA_PROJECT_IDS', '').split(',')
PROJECT_NAMES = os.getenv('ASANA_PROJECT_NAMES', '').split(',')

# Store forwarded messages and state temporarily
message_store = {}  # message_id: {'text': ..., 'state': ..., 'user_id': ...}

# Store batches of forwarded messages per user
batch_store = {}  # user_id: {'messages': [str], 'timer': threading.Timer, 'last_time': float, 'last_message_id': int}
BATCH_TIMEOUT = 2  # seconds

# Store recent prompt message IDs per user for flexible reply handling
recent_prompts = {}  # user_id: [prompt_message_id]
MAX_RECENT_PROMPTS = 5

# Store the last text message per user for caption/title detection
last_text_message = {}  # user_id: {'text': ..., 'timestamp': ...}

warnings.filterwarnings("ignore", message="python-telegram-bot is using upstream urllib3")

def log_all_messages(update: Update, context):
    logger.info(f"RAW MESSAGE: {update.message}")
    # Track last text message for each user
    if update.message.text and not update.message.forward_from and not update.message.forward_from_chat:
        user_id = update.message.from_user.id
        last_text_message[user_id] = {
            'text': update.message.text.strip(),
            'timestamp': time.time()
        }

def start(update: Update, context):
    print("Start handler called")
    try:
        update.message.reply_text('👋 Hi! Forward any message to me and I\'ll help you create an Asana task!')
    except Exception as e:
        print("Error sending reply:", e)

def help_command(update: Update, context):
    update.message.reply_text('📝 How to use:\n1. Forward a message\n2. Select project\n3. Get task link!')

def menu(update: Update, context):
    keyboard = [
        ["📋 Create Asana Task", "🗂 My Asana Projects"],
        ["❓ Help", "ℹ️ About"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(
        "Please choose an option:",
        reply_markup=reply_markup
    )

def handle_menu_option(update: Update, context):
    text = update.message.text
    if text == "📋 Create Asana Task":
        update.message.reply_text("Just forward one or more messages to me to start creating an Asana task!")
    elif text == "🗂 My Asana Projects":
        projects = '\n'.join([f"- {name}" for name in PROJECT_NAMES if name])
        update.message.reply_text(f"Your Asana projects:\n{projects}")
    elif text == "❓ Help":
        update.message.reply_text("Forward messages to create tasks. After forwarding, reply with a title, then pick a project. The bot will use AI to help format your task!")
    elif text == "ℹ️ About":
        update.message.reply_text("Telegram-Asana Bot by RCR. Integrates Telegram with Asana using AI for smart task creation.")

def handle_forwarded_message(update: Update, context):
    print("handle_forwarded_message called")
    # Accept if message is forwarded from a user, a chat (channel), or has a forward_date (robust to privacy settings)
    is_forwarded = bool(
        getattr(update.message, 'forward_from', None) or 
        getattr(update.message, 'forward_from_chat', None) or 
        getattr(update.message, 'forward_date', None)
    )
    if not is_forwarded:
        logger.warning("Message is not forwarded (no forward_from, forward_from_chat, or forward_date).")
        try:
            update.message.reply_text("Please forward a message to create a task.")
        except Exception as e:
            logger.error(f"Error sending not-forwarded reply: {e}")
        return
    user_id = update.message.from_user.id
    # Accept text, caption, or document caption
    message_text = update.message.text or update.message.caption or ""
    if not message_text:
        logger.warning("Forwarded message has no text or caption.")
        try:
            update.message.reply_text("Please forward a text message or a media message with a caption.")
        except Exception as e:
            logger.error(f"Error sending no-text reply: {e}")
        return
    logger.info(f"Batching for user {user_id}: {message_text}")
    now = time.time()
    # If user has an active batch, append; else, start new batch
    if user_id in batch_store:
        batch_store[user_id]['messages'].append(message_text)
        batch_store[user_id]['last_time'] = now
        batch_store[user_id]['last_message_id'] = update.message.message_id
        # Reset timer
        batch_store[user_id]['timer'].cancel()
    else:
        batch_store[user_id] = {
            'messages': [message_text],
            'last_time': now,
            'last_message_id': update.message.message_id,
            'timer': None
        }
    # Start new timer
    timer = threading.Timer(BATCH_TIMEOUT, prompt_for_title_or_use_caption, args=(update, context, user_id))
    batch_store[user_id]['timer'] = timer
    timer.start()

def prompt_for_title_or_use_caption(update, context, user_id):
    batch = batch_store.get(user_id)
    if not batch:
        return
    all_text = '\n'.join(batch['messages'])
    # Check for recent text message as caption/title
    user_last_text = last_text_message.get(user_id)
    use_caption = False
    user_title = None
    if user_last_text and (batch['last_time'] - user_last_text['timestamp'] <= 5):
        use_caption = True
        user_title = user_last_text['text']
    if use_caption:
        # Store in message_store and go straight to project selection
        last_message_id = batch['last_message_id']
        message_store[last_message_id] = {
            'text': all_text,
            'user_title': user_title,
            'state': 'awaiting_project',
            'user_id': user_id,
            'active': True
        }
        keyboard = [[InlineKeyboardButton(name, callback_data=f"project_{pid}:{last_message_id}")]
                    for name, pid in zip(PROJECT_NAMES, PROJECT_IDS)]
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📋 Using your previous message as the title:\n*{user_title}*\n\nWhich Asana project should I add this task to?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Prompt for title as before
        sent = context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="What should the title of the Asana task be?\n(Reply to this message with your title.)"
        )
        message_store[sent.message_id] = {
            'text': all_text,
            'state': 'awaiting_title',
            'user_id': user_id,
            'active': True
        }
        if user_id not in recent_prompts:
            recent_prompts[user_id] = []
        recent_prompts[user_id].append(sent.message_id)
        if len(recent_prompts[user_id]) > MAX_RECENT_PROMPTS:
            recent_prompts[user_id] = recent_prompts[user_id][-MAX_RECENT_PROMPTS:]
    del batch_store[user_id]
    logger.info(f"Prompted user {user_id} for title or used caption. Caption used: {use_caption}")

def handle_title_reply(update: Update, context):
    logger.info(f"handle_title_reply called. Message: {update.message}")
    if not update.message.reply_to_message:
        logger.warning("No reply_to_message in title reply.")
        return
    replied_id = update.message.reply_to_message.message_id
    user_id = update.message.from_user.id
    logger.info(f"Replying to message_id: {replied_id}, user_id: {user_id}")
    # Accept reply to any recent prompt for this user
    valid_prompt = False
    for pid in recent_prompts.get(user_id, []):
        if replied_id == pid:
            valid_prompt = True
            break
    if not valid_prompt:
        logger.warning(f"replied_id {replied_id} not in recent prompts for user {user_id}. Prompts: {recent_prompts.get(user_id, [])}")
        update.message.reply_text("This prompt is no longer active. Please forward new messages to create a new task.")
        return
    if replied_id not in message_store:
        logger.warning(f"replied_id {replied_id} not in message_store. Keys: {list(message_store.keys())}")
        update.message.reply_text("This prompt has expired. Please forward new messages to create a new task.")
        return
    if not message_store[replied_id].get('active', True):
        update.message.reply_text("This task has already been processed. Please forward new messages to create a new task.")
        return
    if message_store[replied_id].get('user_id') != user_id:
        logger.warning(f"User ID mismatch: {message_store[replied_id].get('user_id')} != {user_id}")
        return
    if message_store[replied_id]['state'] != 'awaiting_title':
        logger.warning(f"State is not 'awaiting_title': {message_store[replied_id]['state']}")
        return
    user_title = update.message.text.strip()
    original_text = message_store[replied_id]['text']
    message_store[replied_id]['user_title'] = user_title
    message_store[replied_id]['state'] = 'awaiting_project'
    # Ask for project selection
    keyboard = [[InlineKeyboardButton(name, callback_data=f"project_{pid}:{replied_id}")]
                for name, pid in zip(PROJECT_NAMES, PROJECT_IDS)]
    update.message.reply_text(
        "📋 Which Asana project should I add this task to?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logger.info(f"Prompted user {user_id} for project selection. Title: {user_title}")

def handle_title_standalone(update: Update, context):
    user_id = update.message.from_user.id
    # Only proceed if there is exactly one active prompt for this user
    active_prompts = [pid for pid in recent_prompts.get(user_id, []) if message_store.get(pid, {}).get('active', False)]
    if len(active_prompts) != 1:
        return  # Ignore if not exactly one active prompt
    replied_id = active_prompts[0]
    logger.info(f"handle_title_standalone: Using active prompt {replied_id} for user {user_id}")
    if replied_id not in message_store:
        return
    if message_store[replied_id].get('user_id') != user_id:
        return
    if message_store[replied_id]['state'] != 'awaiting_title':
        return
    user_title = update.message.text.strip()
    original_text = message_store[replied_id]['text']
    message_store[replied_id]['user_title'] = user_title
    message_store[replied_id]['state'] = 'awaiting_project'
    # Ask for project selection
    keyboard = [[InlineKeyboardButton(name, callback_data=f"project_{pid}:{replied_id}")]
                for name, pid in zip(PROJECT_NAMES, PROJECT_IDS)]
    update.message.reply_text(
        "📋 Which Asana project should I add this task to?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logger.info(f"Prompted user {user_id} for project selection (standalone title). Title: {user_title}")

def button_callback(update: Update, context):
    query = update.callback_query
    query.answer()
    try:
        project_part, original_message_id = query.data.split(":")
        project_id = project_part.split("_")[1]
        original_message_id = int(original_message_id)
    except Exception as e:
        logger.error(f"Error parsing callback data: {e}")
        query.edit_message_text("Error: Invalid callback data.")
        return
    # Retrieve stored info
    store = message_store.get(original_message_id)
    if not store:
        query.edit_message_text("Error: Message not found.")
        return
    if not store.get('active', True):
        query.edit_message_text("This task has already been processed. Please forward new messages to create a new task.")
        return
    user_title = store.get('user_title', '')
    original_text = store.get('text', '')
    try:
        # Use OpenAI to gently improve the title and generate the description
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "You are an assistant that helps create Asana tasks. "
                    "Given a user-suggested title and the original message, "
                    "gently improve the title (fix typos, grammar, capitalization, but do not rewrite or change the meaning), "
                    "and generate a concise description (max 50 words). "
                    "Return both as JSON: {\"title\": ..., \"description\": ...}"
                )},
                {"role": "user", "content": f"User title: {user_title}\nOriginal message: {original_text}"}
            ],
            max_tokens=100
        )
        ai_result = response.choices[0].message['content'].strip()
        logger.warning(f"OpenAI raw response: {ai_result}")
        try:
            ai_json = json.loads(ai_result)
            improved_title = ai_json.get('title', user_title)
            improved_description = ai_json.get('description', '')
        except Exception:
            improved_title = user_title
            improved_description = ''
        # Format description for Asana: bold subtitles (ALL CAPS) and lines for quotes
        indented_message = '\n'.join([f'{line}' for line in original_text.splitlines()])
        full_description = (
            f"CONTEXT: \n{improved_description}\n\n"
            f"------------------------------\n"
            f"ORIGINAL TG MESSAGE: \n{indented_message}\n"
            f"------------------------------"
        )
        # Create Asana task
        task = asana_client.tasks.create_task({
            'name': improved_title,
            'notes': full_description,
            'projects': [project_id]
        })
        # Send confirmation with task link
        task_url = f"https://app.asana.com/0/{project_id}/{task['gid']}"
        query.edit_message_text(f"✅ Task created: {task_url}")
        # Clean up
        store['active'] = False
        user_id = store.get('user_id')
        if user_id in recent_prompts:
            recent_prompts[user_id] = [pid for pid in recent_prompts[user_id] if pid != original_message_id]
        del message_store[original_message_id]
        logger.info(f"Task created and state cleaned for user {user_id}.")
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        try:
            query.edit_message_text("❌ Error creating task. Please try again later.")
        except Exception as edit_err:
            if "Message is not modified" in str(edit_err):
                logger.warning("Tried to edit message with the same content. Ignoring.")
            else:
                logger.error(f"Unexpected error editing message: {edit_err}")

def main():
    # Create and configure the updater
    updater = Updater(os.getenv('TELEGRAM_BOT_TOKEN'))
    dispatcher = updater.dispatcher

    # Set up bot commands
    commands = [
        ('start', 'Start the bot'),
        ('menu', 'Show the main menu'),
        ('help', 'Show help information')
    ]
    updater.bot.set_my_commands(commands)

    # Add raw logger at the very top
    dispatcher.add_handler(MessageHandler(Filters.all, log_all_messages), group=99)

    # Add handlers in correct order
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("menu", menu))
    # Forwarded message handlers FIRST
    dispatcher.add_handler(MessageHandler(Filters.forwarded & (Filters.text | Filters.caption), handle_forwarded_message))
    dispatcher.add_handler(MessageHandler(Filters.forwarded & Filters.document, handle_forwarded_message))
    # Reply handler
    dispatcher.add_handler(MessageHandler(Filters.reply, handle_title_reply))
    # Standalone title and menu handlers
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_title_standalone))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_menu_option))
    dispatcher.add_handler(CallbackQueryHandler(button_callback))

    # Start the bot
    if os.getenv('HEROKU_APP_NAME'):  # If running on Heroku
        port = int(os.environ.get('PORT', 5000))
        public_url = os.getenv('HEROKU_PUBLIC_URL')
        updater.start_webhook(
            listen='0.0.0.0',
            port=port,
            url_path=os.getenv('TELEGRAM_BOT_TOKEN'),
            webhook_url=f"https://{public_url}/{os.getenv('TELEGRAM_BOT_TOKEN')}"
        )
        logger.info("Bot started in webhook mode")
        logger.warning(f"TELEGRAM_BOT_TOKEN: {os.getenv('TELEGRAM_BOT_TOKEN')}")
        logger.warning(f"HEROKU_APP_NAME: {os.getenv('HEROKU_APP_NAME')}")
        logger.warning(f"HEROKU_PUBLIC_URL: {public_url}")
        logger.warning(f"Listening on path: /{os.getenv('TELEGRAM_BOT_TOKEN')}")
    else:  # If running locally
        updater.start_polling()
        logger.info("Bot started in polling mode")

    logger.warning("Bot entering idle mode")
    updater.idle()

if __name__ == '__main__':
    main() 