# CLIPFORGE

CLIPFORGE is a local browser operator that researches a video in the **ChatGPT chat UI**, passes the research brief into the **Claude chat UI + OpusClip connector**, then sends a Telegram notification. It does not call ChatGPT, Claude, or OpusClip APIs, and it never uploads to YouTube.

## Workflow

1. The local Windows operator asks for a YouTube URL, requested clip count, style, and duration.
2. It opens a dedicated Chrome profile for ChatGPT. You sign in if needed.
3. It submits a research request through the visible ChatGPT chat UI and captures the assistant's research response.
4. It opens a separate dedicated Chrome profile for Claude. You sign in and ensure the OpusClip connector is enabled.
5. It passes the source URL, clip instructions, and ChatGPT research brief into Claude's visible chat UI.
6. It waits for Claude's response and sends a Telegram message with detected OpusClip links, or a warning if direct links cannot be verified.

You review/download the finished clips yourself and upload them to YouTube yourself.

## Windows setup

- Install Python 3.10+ and Google Chrome.
- Copy `.env.example` to `.env`.
- Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`.
- Run `local_agent\\run_windows.bat`.

The first run installs Playwright and creates separate persistent Chrome profiles at `local_agent\\chatgpt_chrome_profile` and `local_agent\\claude_chrome_profile`. Sign in to both services in their respective windows. Your normal Chrome profile and passwords are not read.

## Telegram setup

Create a bot with Telegram's @BotFather, obtain your chat ID, and start a conversation with the bot before testing notifications. Keep the bot token private in the local `.env` file; never commit it.

## Important limitations

- This is an initial browser-automation foundation, not a claim of fully tested end-to-end operation. ChatGPT/Claude UI selectors and connector flows can change.
- ChatGPT research is only as reliable as the source/transcript it can actually access. The research prompt requires inaccessible information and uncertain timestamps to be labelled rather than invented.
- You may need to complete sign-in, connector authorization, or OpusClip confirmation manually.
- Completion detection is heuristic. A stable Claude response is not absolute proof that OpusClip finished processing; inspect the Telegram message and OpusClip links.
- The local PC must remain on, connected to the internet, and both Chrome sessions must remain open while the task runs.
- No YouTube upload or publishing is performed.
- Only use videos you own or have permission to edit and repurpose.
