"""Transcript acquisition adapters used before agent analysis."""
from __future__ import annotations

import re


class TranscriptUnavailable(RuntimeError):
    pass


def youtube_video_id(url: str) -> str:
    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise TranscriptUnavailable("Unsupported YouTube URL or missing video ID")


def fetch_youtube_transcript(url: str, languages: list[str] | None = None) -> str:
    video_id = youtube_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages or ["en", "hi"])
        rows = fetched.to_raw_data()
        lines = []
        for row in rows:
            start = float(row["start"])
            text = str(row["text"]).replace("\n", " ").strip()
            if text:
                lines.append(f"[{start:.2f}] {text}")
        transcript = "\n".join(lines)
        if len(transcript) < 20:
            raise TranscriptUnavailable("The video transcript is empty or too short")
        return transcript[:150000]
    except TranscriptUnavailable:
        raise
    except Exception as exc:
        raise TranscriptUnavailable(
            "Could not retrieve captions. The video may have captions disabled, "
            "be restricted, or require a supported language."
        ) from exc
