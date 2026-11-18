"""CLIPFORGE multi-agent planning pipeline.

This module creates an editorial plan only. It never downloads, edits, exports,
or publishes media. Those actions remain behind separate provider adapters and
human approval.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


class AgentConfigurationError(RuntimeError):
    pass


class AgentExecutionError(RuntimeError):
    pass


class ClaudeAgent:
    def __init__(self, role: str, instructions: str, model: str | None = None):
        self.role = role
        self.instructions = instructions
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-latest")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AgentConfigurationError("ANTHROPIC_API_KEY is not configured")
        payload = {
            "model": self.model,
            "max_tokens": 5000,
            "system": self.instructions + "\nReturn only valid JSON. Do not use markdown fences.",
            "messages": [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
        }
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            raw = "".join(
                item.get("text", "") for item in data.get("content", [])
                if item.get("type") == "text"
            ).strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Agent response must be a JSON object")
            return parsed
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AgentExecutionError(f"{self.role} failed: {exc}") from exc


class ResearchAgent(ClaudeAgent):
    def __init__(self):
        super().__init__(
            "research",
            "You are the research agent for a creator-authorized video clipping system. "
            "Analyze only the supplied transcript and metadata. Do not invent facts. "
            "Return JSON keys: summary, topics (array), audience, notable_context (array), "
            "uncertainties (array). Clearly mark unsupported claims."
        )


class MomentSelectionAgent(ClaudeAgent):
    def __init__(self):
        super().__init__(
            "moment-selection",
            "You are an expert short-form video editor. Select compelling, self-contained "
            "moments from the supplied transcript. Use only timestamps supported by transcript "
            "segments. Return JSON key candidates: array of objects with start_seconds, "
            "end_seconds, hook, rationale, quote, and platform_fit. Prefer strong hooks, "
            "clear payoff, and context-complete moments. Do not fabricate dialogue."
        )


class EditorialStrategyAgent(ClaudeAgent):
    def __init__(self):
        super().__init__(
            "editorial-strategy",
            "You are the editorial strategy agent. Rank the candidate moments and create "
            "editing instructions for vertical 9:16 short-form videos. Return JSON keys: "
            "ranked_clips (array; include source_candidate_index, title, opening_hook, "
            "caption_style, pacing_notes, b_roll_notes, ending), global_style, "
            "risks (array). Do not claim to have edited any media."
        )


class SafetyReviewAgent(ClaudeAgent):
    def __init__(self):
        super().__init__(
            "safety-review",
            "You are the final rights and quality gate. Review the research, selected moments, "
            "and edit plan. Do not infer copyright permission from a URL or transcript. "
            "Return JSON keys: approved_for_human_review (boolean), blockers (array), "
            "quality_notes (array), required_human_checks (array). This is not permission "
            "to publish; human approval is always required."
        )


class ClipForgeOrchestrator:
    """Runs specialist agents sequentially and returns an approval-gated plan."""

    def __init__(self):
        self.research = ResearchAgent()
        self.moments = MomentSelectionAgent()
        self.strategy = EditorialStrategyAgent()
        self.safety = SafetyReviewAgent()

    async def run(self, *, video_url: str, creator: str, transcript: str) -> dict[str, Any]:
        if not transcript.strip():
            raise ValueError("A transcript is required before agent analysis")
        if len(transcript) > 150_000:
            raise ValueError("Transcript exceeds the 150,000 character limit")

        base = {
            "video_url": video_url,
            "creator": creator,
            "transcript": transcript,
            "rights_policy": "Creator authorization must be independently verified; never assume permission.",
        }
        research = await self.research.run(base)
        moments = await self.moments.run({**base, "research": research})
        strategy = await self.strategy.run({
            "video_url": video_url, "creator": creator,
            "research": research, "moment_candidates": moments,
        })
        safety = await self.safety.run({
            "video_url": video_url, "creator": creator,
            "research": research, "moment_candidates": moments,
            "editorial_strategy": strategy,
        })
        return {
            "pipeline_version": "1.0",
            "status": "awaiting_human_approval",
            "agents": {
                "research": research,
                "moment_selection": moments,
                "editorial_strategy": strategy,
                "safety_review": safety,
            },
            "approval": {
                "required": True,
                "approved": False,
                "note": "No editing, export, or publishing occurs until a human approves this plan.",
            },
        }
