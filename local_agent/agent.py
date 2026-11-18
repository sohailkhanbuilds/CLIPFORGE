from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
CHATGPT_PROFILE = ROOT / "chatgpt_chrome_profile"
CLAUDE_PROFILE = ROOT / "claude_chrome_profile"
load_dotenv(ROOT.parent / ".env")

CHATGPT_URL = "https://chatgpt.com/"
CLAUDE_URL = "https://claude.ai/new"


def valid_video_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
        "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"
    }


def research_prompt(video_url: str, count: int, style: str, duration: str) -> str:
    return f"""Research this YouTube video before any clips are created.

VIDEO: {video_url}
REQUESTED CLIPS: {count}
STYLE: {style}
PREFERRED DURATION: {duration}

Use web research and the video's available transcript/captions if accessible. Do not pretend to have watched or inspected content you cannot access. Identify the strongest moments for short-form clips and provide:
1. A concise factual summary and main topics.
2. A ranked list of exactly {count} candidate moments where evidence permits.
3. For each: start/end timestamps, hook, why it works, key quote or action, and context needed to avoid misleading edits.
4. Any uncertain timestamps or unavailable source information, clearly labelled.
5. A compact editor brief for Claude/OpusClip.

Prioritize self-contained moments, strong opening hooks, clear context, and no misleading cuts. Do not create clips or claim to have created them. Return a structured, concise research brief that can be passed to an editing tool."""


def build_claude_prompt(video_url: str, count: int, style: str, duration: str, research: str) -> str:
    return f"""Use the OpusClip connector available in this Claude conversation. Do not use direct APIs, scripts, or third-party transcript APIs.

SOURCE VIDEO: {video_url}
REQUESTED CLIPS: {count}
STYLE: {style}
PREFERRED DURATION: {duration}

CHATGPT RESEARCH BRIEF (use as editorial guidance; verify against the source in OpusClip and do not blindly trust uncertain timestamps):
{research[:18000]}

TASK:
- Use the OpusClip connector and its supported workflow to create the requested clips.
- Prefer the strongest supported moments from the research brief, but verify the moments against the actual source/transcript in OpusClip.
- Create exactly {count} clips where the connector permits. If fewer are possible, explain why.
- Use suitable vertical short-form framing and captions when supported.
- Do not invent completed work. Wait until OpusClip reports processing is finished.
- Return each finished clip's title, duration, and direct preview/download link if available.
- Clearly state whether all clips are ready. Do not publish or upload anything to YouTube."""


async def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram is not configured; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False},
        )
        response.raise_for_status()


async def submit_chat_request(page, prompt: str, assistant_selector: str, label: str) -> str:
    composer = page.locator('[contenteditable="true"]').last
    await composer.wait_for(state="visible", timeout=240000)
    await composer.fill(prompt)
    await page.wait_for_timeout(700)
    send_button = page.get_by_role("button", name=re.compile(r"send", re.I))
    if await send_button.count():
        await send_button.last.click()
    else:
        await composer.press("Enter")

    print(f"{label}: request submitted. Waiting for the answer...")
    assistant_messages = page.locator(assistant_selector)
    deadline = time.monotonic() + 20 * 60
    answer = ""
    previous = ""
    stable_since = time.monotonic()
    saw_answer = False

    while time.monotonic() < deadline:
        await page.wait_for_timeout(4000)
        try:
            if await assistant_messages.count():
                current = (await assistant_messages.last.inner_text(timeout=8000)).strip()
                if current:
                    saw_answer = True
                    if current != previous:
                        previous = current
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= 18:
                        answer = current
                        break
        except PlaywrightTimeoutError:
            continue

    if not saw_answer or not answer:
        raise RuntimeError(f"{label}: no stable assistant response detected. Check the open browser tab.")
    return answer


async def open_chrome(p, profile: Path):
    return await p.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )


async def main() -> None:
    print("\nCLIPFORGE — ChatGPT research → Claude + OpusClip → Telegram")
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

    async with async_playwright() as p:
        chatgpt_context = await open_chrome(p, CHATGPT_PROFILE)
        chatgpt_page = chatgpt_context.pages[0] if chatgpt_context.pages else await chatgpt_context.new_page()
        await chatgpt_page.goto(CHATGPT_URL, wait_until="domcontentloaded")
        print("\nSTEP 1/2 — ChatGPT research")
        print("Sign in to ChatGPT in this dedicated Chrome profile if needed.")
        try:
            research = await submit_chat_request(
                chatgpt_page,
                research_prompt(video_url, count, style, duration),
                '[data-message-author-role="assistant"]',
                "ChatGPT research",
            )
        except Exception:
            print("ChatGPT research did not complete. Leaving its Chrome window open for inspection.")
            raise

        print("\nChatGPT research captured. Opening Claude for clip generation.")
        claude_context = await open_chrome(p, CLAUDE_PROFILE)
        claude_page = claude_context.pages[0] if claude_context.pages else await claude_context.new_page()
        await claude_page.goto(CLAUDE_URL, wait_until="domcontentloaded")
        print("STEP 2/2 — Claude + OpusClip")
        print("Sign in to Claude and ensure the OpusClip connector is enabled in this profile.")
        try:
            result = await submit_chat_request(
                claude_page,
                build_claude_prompt(video_url, count, style, duration, research),
                '[data-testid="chat-message"], [data-message-author-role="assistant"]',
                "Claude/OpusClip",
            )
        except Exception:
            print("Claude/OpusClip did not complete. Browser windows are being left open for inspection.")
            raise

        urls = list(dict.fromkeys(re.findall(r"https?://[^\s)\]>]+", result)))
        clip_urls = [u.rstrip(".,;") for u in urls if "opus.pro" in u.lower() or "opusclip" in u.lower()]
        if clip_urls:
            message = "✅ CLIPFORGE: Claude's response indicates the OpusClip task is finished. Please verify the clips in OpusClip.\n\n" + "\n".join(clip_urls[:20])
        else:
            message = (
                "⚠️ CLIPFORGE: Claude responded, but I could not detect direct OpusClip clip links. "
                "Check Claude/OpusClip before treating the clips as ready.\n\n" + result[-2500:]
            )
        await send_telegram(message)
        print("\nTelegram notification sent (if bot credentials are configured).")
        await claude_context.close()
        await chatgpt_context.close()


if __name__ == "__main__":
    asyncio.run(main())
