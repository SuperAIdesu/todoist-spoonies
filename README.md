# Todoist for 🥄Spoonies

Todoist automations for people who use [spoon theory](https://en.wikipedia.org/wiki/Spoon_theory) to manage their daily lives. Track your energy expenditure through a Telegram bot that integrates with Todoist.

## The workflow design

In Todoist:

- There is a list of labels (for example, `spoons-1`...`spoons-9`) with the same prefix before a number. They are used to tag tasks with the required energy levels.

- Apart from regular projects, there is a special "template" project that includes frequently performed daily activities, and/or placeholder tasks with a variety of spoon levels already attached. Compared to tasks in regular projects, which are usually scheduled, they can be completed anytime and/or multiple times in a day.

What the automation service will do:

- When tasks are completed in Todoist, it tracks the completion record in a local database, including the number of spent spoons.
- If the completed task is in the "template" project, re-add it back after a short delay. (The delay is there to avoid the task instantly reappearing in the Todoist UI, which could be interpreted as network error.)
- If tasks are uncompleted, the completion record will be deleted internally as well.

By using the Telegram bot, you can:

- Check the completed tasks and used spoons today
- Set a scheduled daily summary message
- Check the energy expenditure for the past few days

## Setup Instructions

### Prerequisites

The project is designed to be self-hosted. Apart from a Todoist account and a Telegram account, you will need a VPS (or other similar server environment) with a public IP, domain name and available 443 port.

### 1. Todoist Integration

Create a Todoist Integration to obtain `CLIENT_ID` and `CLIENT_SECRET`, and set webhook URL.

1. Go to [Todoist app management](https://app.todoist.com/app/settings/integrations/app-management), and click "Add new integration". You can input any app name and description.
2. In the newly created app settings:
   1. **Service URL**: The domain name you would like to use for this service, for example `https://todoist-spoonies.mydomain.com`
   2. Note down the **Client ID** and **Client Secret**
   3. In **OAuth redirect URL**, input the same URL as **Service URL**
   4. Expand the **Webhooks** section. In **Callback URL**, add the path `/todoist/webhook` after your service URL. Following the above example, you should input `https://todoist-spoonies.mydomain.com/todoist/webhook`
   5. Under **Webhook Events**, check `item:completed` and `item:uncompleted`
   6. Save your settings and "Update Webhook"


### 2. Telegram Integration

Create your own Telegram Bot, and get your own user ID so that the bot can only talk to you:

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts to create a bot
3. Copy the **bot token** (format: `123456789:ABCdefGHI...`)
4. To find your **user ID**, send a message to **@Getmyid_Work_Bot** and it will reply with your numeric ID

### 3. Hosting Environment and Reverse Proxy

1. **DNS**: In the DNS provider of your domain, set the chosen domain name (in step 1) to point to your server IP.
2. **Reverse proxy**: The app runs an HTTP server on localhost and expects a reverse proxy to forward webhook traffic. In addition, the Todoist & Telegram webhook services expect HTTPS.

You can use [Caddy](https://caddyserver.com/docs/install) for reverse proxy, and a simple `Caddyfile` that works is:
```
todoist-spoonies.mydomain.com

reverse_proxy :8001
```

Caddy will automatically obtain TLS certificate and serve HTTPS.

### 4. Todoist Workflow Setup

**Create a template project:**

1. In Todoist, create a new project named `Template` (or whatever you set as `TEMPLATE_PROJECT_NAME`)
2. Put some daily tasks in the project. You can use sections, but subtasks are currently unsupported.

**Set up spoon labels:**

1. In Todoist, create labels for each spoon count level (e.g., `spoons-1`)
2. The `LABEL_PREFIX` env var determines the prefix (e.g. `spoons-`)

### 5. Install and Run

On the server:

```bash
# Clone the project
git clone <repository-url>
cd todoist-spoonies

# Install dependencies
uv sync

# Copy environment template and fill in your values
cp .env.template .env
```

Edit `.env` with your configuration:

```
CLIENT_ID=your_todoist_client_id_in_step_1
CLIENT_SECRET=your_todoist_client_secret_in_step_1
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_in_step_2
TELEGRAM_USER_ID=your_telegram_user_id_in_step_2
URL=https://todoist-spoonies.mydomain.com
TEMPLATE_PROJECT_NAME=template_project_name_in_step_4
LABEL_PREFIX=label_prefix_in_step_4
```

Start the application:

```bash
uv run todoist_spoonies/app.py
```

In the first few lines of the output, the app will print a Todoist OAuth URL to the console. Look for a URL starting with `https://app.todoist.com/oauth/`. Open it in your browser and authorize the app. After authorization, Todoist will redirect to your server's root path, completing the token exchange.

**CLI options:**

| Flag | Default | Description |
|------|---------|-------------|
| `-l`, `--listen` | `127.0.0.1` | Host to bind the HTTP server |
| `-p`, `--port` | `8001` | Port to bind the HTTP server |

You can use tools like [pm2](https://pm2.keymetrics.io/docs/usage/quick-start/) to turn it into a background service, and monitor its status.

### 6. Interact with the Telegram bot

The service should be already up and running. Send a `/help` message to the Telegram bot for a list of available commands.

## Database export

The service stores all data in `data/db.json` using TinyDB. The file is a plain JSON, and the completed task records are under `"tasks"`. 

## LLM disclosure

A locally deployed Qwen-3.6-27B model was used to assist with small and well-scoped tasks. All code and documentation is reviewed and edited by humans.
