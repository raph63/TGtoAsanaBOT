# Telegram-Asana Bot

A Telegram bot that integrates with Asana, allowing you to forward messages (including media) and create Asana tasks with AI-generated context and formatting.

## Features

- **Forward Messages**: Forward any message from Telegram to create an Asana task.
- **Batch Messages**: Combine multiple forwarded messages into a single task for better organization.
- **AI-Powered Task Generation**: Automatically generate task titles and descriptions using AI for clarity and context.
- **Media Attachments**: Support for forwarding documents (PDFs, Word files, etc.) and photos/images, which are attached to the Asana task.
- **Clear Formatting**: Tasks in Asana are formatted clearly, including original message content, sender information, and forwarding details.
- **Interactive Menu**: Use the interactive menu to navigate through options and commands easily.

## Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/raph63/TGtoAsanaBOT.git
   cd TGtoAsanaBOT
   ```

2. **Create a Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file in the project root with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ASANA_PAT=your_asana_personal_access_token
   OPENAI_API_KEY=your_openai_api_key
   ASANA_PROJECT_IDS=project_id1,project_id2
   ASANA_PROJECT_NAMES=Project1,Project2
   ```

5. **Run the Bot**:
   ```bash
   python bot.py
   ```

## Usage

1. **Start the Bot**: Use the `/start` command to begin interacting with the bot.
2. **Access the Menu**: Use `/menu` to view available options and commands.
3. **Forward Messages**: Forward any message to the bot to create an Asana task.
4. **Title Input**: Reply with a title for the task, or let the bot use your previous message as the title.
5. **Select Project**: Choose the Asana project where the task should be created.

## Commands

- `/start` - Start the bot and receive a welcome message.
- `/menu` - Display the main menu with available options.
- `/help` - Show help information and usage instructions.

## License

MIT License 