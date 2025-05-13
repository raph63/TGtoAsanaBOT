# Telegram-Asana Bot

A Telegram bot that integrates with Asana, allowing you to forward messages (including media) and create Asana tasks with AI-generated context and formatting.

## Features

- Forward messages from Telegram to create Asana tasks
- Batch multiple forwarded messages into a single task
- AI-powered task title and description generation
- Support for media attachments
- Clear formatting in Asana tasks
- Interactive menu system

## Setup

1. Clone the repository
2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ASANA_PAT=your_asana_personal_access_token
   OPENAI_API_KEY=your_openai_api_key
   ASANA_PROJECT_IDS=project_id1,project_id2
   ASANA_PROJECT_NAMES=Project1,Project2
   ```
5. Run the bot:
   ```bash
   python bot.py
   ```

## Usage

1. Start the bot with `/start`
2. Use `/menu` to see available options
3. Forward messages to create tasks
4. Reply with a title or let the bot use your previous message as the title
5. Select the Asana project for the task

## Commands

- `/start` - Start the bot
- `/menu` - Show the main menu
- `/help` - Show help information

## License

MIT License 