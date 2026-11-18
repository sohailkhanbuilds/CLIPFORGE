# CLIPFORGE

CLIPFORGE is a local browser operator for creating short-form clips through the **Claude chat UI + OpusClip connector**. It does not call Claude's API or OpusClip APIs, and it never uploads to YouTube.

## Current scope

1. The local Windows operator asks for a YouTube URL, clip count, style, and preferred duration.
2. It opens a dedicated Chrome profile and navigates to Claude.
3. You sign in to Claude and connect/enable OpusClip in Claude if you have not already done so.
4. The operator enters the task into the visible Claude chat and submits it.
5. It waits for the visible response to settle, then sends a Telegram message with detected OpusClip links or a warning if readiness could not be verified.

You review/download the finished clips yourself and upload them to YouTube yourself.

## Windows setup

- Install Python 3.10+ and Google Chrome.
- Copy `.env.example` to `.env`.
- Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`.
- Run `local_agent\\run_windows.bat`.

The first run installs Playwright and creates a separate Chrome profile at `local_agent\\claude_chrome_profile`. Sign in to Claude in that Chrome window. Your normal Chrome profile and passwords are not read.

## Telegram setup

Create a bot with Telegram's @BotFather, then obtain your chat ID. Start a conversation with your bot before testing notifications. Keep the bot token private and only store it in the local `.env` file; never commit it.

## Important limitations

- This is a first browser-automation foundation, not a claim of fully tested end-to-end OpusClip execution. Claude's UI and connector confirmation flows can change.
- You may need to complete Claude sign-in, connector authorization, or an OpusClip confirmation manually.
- Completion detection is heuristic. If the operator cannot find an OpusClip link, Telegram will explicitly warn that readiness was not verified.
- The local PC must remain on, connected to the internet, and the Chrome window must remain open while the task runs.
- No YouTube upload or publishing is performed.
- Only use videos you own or have permission to edit and repurpose.
