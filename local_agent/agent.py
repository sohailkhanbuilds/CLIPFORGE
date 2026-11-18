from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / "claude_chrome_profile"
CLAUDE_URL = "https://claude.ai/new"


def valid_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
        "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"
    }


def build_prompt(video_url: str, count: int, style: str, duration: str) -> str:
    return f"""Use the OpusClip connector available in this Claude conversation. Do not use direct APIs, scripts, or third-party transcript APIs.

Source video: {video_url}

Create exactly {count} short-form clips.
Style/instructions: {style}
Preferred clip duration: {duration}

Requirements:
- Work through the OpusClip connector and its supported workflow.
- Select self-contained, engaging moments with clear hooks.
- Keep the requested quantity exact where the tool permits; if fewer clips can be created, explain why.
- Do not invent completed work. Wait for OpusClip processing to finish.
- When finished, return each clip's title, duration, and direct preview/download link if available.
- Clearly say when all clips are ready. Do not publish or upload anything to YouTube.
"""


async def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram is not configured; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False})
        response.raise_for_status()


async def main() -> None:
    print("\nCLIPFORGE — Claude + OpusClip browser operator")
    video_url = input("YouTube video URL: ").strip()
    if not valid_video_url(video_url):
        raise SystemExit("Please enter a valid YouTube URL.")

    try:
        count = int(input("How many clips? ").strip())
        if not 1 <= count <= 20:
            raise ValueError
    except ValueError:
        raise SystemExit("Clip count must be between 1 and 20.")

    style = input("Clip instructions/style: ").strip() or "Choose the strongest moments for Shorts/Reels."
    duration = input("Preferred duration (e.g. 30–60 seconds): ").strip() or "30–60 seconds"
    prompt = build_prompt(video_url, count, style, duration)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(CLAUDE_URL, wait_until="domcontentloaded")
        print("\nChrome opened. Sign in to Claude and ensure OpusClip is connected in Claude.")
        print("The operator will place the request in the Claude chat composer.")
        try:
            composer = page.locator('[contenteditable="true"]').last
            await composer.wait_for(state="visible", timeout=180000)
            await composer.fill(prompt)
            await page.wait_for_timeout(800)
            # Submit through Claude's visible chat UI.
            send_button = page.get_by_role("button", name=re.compile(r"send", re.I))
            if await send_button.count():
                await send_button.last.click()
            else:
                await composer.press("Enter")
        except PlaywrightTimeoutError:
            await context.close()
            raise SystemExit("Claude chat was not ready. Sign in, then run the agent again.")

        print("\nRequest submitted through Claude's chat UI.")
        print("Waiting for Claude/OpusClip to finish. Keep this Chrome window open.")

        previous = ""
        stable_since = time.monotonic()
        final_text = ""
        deadline = time.monotonic() + 60 * 60
        while time.monotonic() < deadline:
            await page.wait_for_timeout(5000)
            try:
                body_text = await page.locator("body").inner_text(timeout=10000)
            except PlaywrightTimeoutError:
                continue
            # Keep a bounded snapshot; compare only recent visible text.
            snapshot = body_text[-14000:]
            if snapshot != previous:
                previous = snapshot
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= 25 and len(snapshot) > 500:
                final_text = snapshot
                break

        if not final_text:
            await context.close()
            raise SystemExit("Timed out waiting for Claude. No completion notification was sent.")

        # Pull likely OpusClip URLs from the visible Claude response.
        urls = list(dict.fromkeys(re.findall(r"https?://[^\s)\]>]+", final_text)))
        clip_urls = [u.rstrip(".,;") for u in urls if "opus.pro" in u.lower() or "opusclip" in u.lower()]
        if clip_urls:
            message = "✅ CLIPFORGE: Claude reports the clip task is finished.\n\n" + "\n".join(clip_urls[:20])
        else:
            message = (
                "⚠️ CLIPFORGE: Claude's response stopped changing, but I could not verify direct OpusClip links. "
                "Please check the open Claude tab before treating the clips as ready.\n\n"
                + final_text[-2500:]
            )
        await send_telegram(message)
        print("\nTelegram notification sent (if bot credentials are configured).")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
