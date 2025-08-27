# GPT-5 Telegram Bot

A Telegram bot that integrates with GPT-5 API to provide intelligent responses with conversation context support.

## Features

- **Direct messaging**: Responds to all messages in private chats
- **Group support**: Responds when mentioned with @ or using /ask command
- **Context awareness**: Maintains last 10 messages for each chat
- **Context management**: Clear conversation history with /resetc
- **Clean architecture**: Modular, maintainable code structure

## Setup

### 1. Create Telegram Bot

1. Open Telegram and search for @BotFather
2. Send `/newbot` and follow instructions
3. Save the bot token

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

1. Copy `.env.template` to `.env`
2. Add your Telegram bot token to `.env`
3. Verify the AGENT_ACCESS_ID is correct

### 4. Run the Bot

```bash
python bot.py
```

## Usage

### Commands

- `/start` - Initialize the bot
- `/help` - Show available commands
- `/ask <question>` - Ask a question (works in groups)
- `/resetc` - Clear conversation context

### Group Usage

In groups, the bot responds when:
- Mentioned with @yourbotname
- Using the `/ask` command

### Private Chat

In private chats, the bot responds to all messages automatically.

## Architecture

```
bot.py
├── ConversationManager  # Manages chat contexts
├── GPT5Client          # Handles API communication
└── TelegramBot         # Main bot logic
```

### Key Components

- **ConversationManager**: Maintains conversation history with deque for efficient memory management
- **GPT5Client**: Handles API requests with proper error handling and timeout management
- **TelegramBot**: Processes messages, manages commands, and coordinates components

## Error Handling

- Request timeouts (30s default)
- API errors with user-friendly messages
- Automatic logging for debugging

## Development

The code is structured for easy extension:
- Add new commands in `TelegramBot` class
- Modify context size in `MAX_CONTEXT_SIZE`
- Adjust timeout in `REQUEST_TIMEOUT`

## Security

- Environment variables for sensitive data
- No hardcoded credentials
- Proper error handling without exposing internal details