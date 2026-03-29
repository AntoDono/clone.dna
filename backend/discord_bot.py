"""
Discord bot for Clone.dna — DM your team's PM from Discord.

Pairing flow:
  1. Create a team via the web UI (generates a discord_pair_code).
  2. DM this bot the 6-char code to link your Discord account to that team.
  3. After pairing, any DM is routed through the PM orchestrate flow.

Started automatically by main.py when DISCORD_BOT_TOKEN is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord

from db import db
from models import Team, RoleSlot, Candidate, ChatMessage, DiscordPairing
from trainer import grok_chat
from trainer.orchestrator import assign_tasks
from trainer.tools import TOOL_SCHEMAS

logger = logging.getLogger("discord_bot")

_WORKSPACE_ROOT = Path(os.getenv("AGENT_WORKSPACE_DIR", "agent-workspace"))
DISCORD_MAX_LEN = 2000


def _workspace_for_team(team_id: int) -> str:
    ws = _WORKSPACE_ROOT / str(team_id)
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


def _split_message(text: str, limit: int = DISCORD_MAX_LEN) -> list[str]:
    """Split text into chunks that fit within Discord's message limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ── Pairing ──────────────────────────────────────────────────────────────────


def try_pair(discord_user_id: str, code: str) -> str | None:
    """Attempt to pair a Discord user to a team via pair code.
    Returns a success message or None if the code doesn't match."""
    code = code.strip().lower()
    team = Team.select().where(Team.discord_pair_code == code).first()
    if not team:
        return None

    existing = DiscordPairing.select().where(
        DiscordPairing.discord_user_id == discord_user_id
    ).first()
    if existing:
        existing.team = team
        existing.save()
    else:
        DiscordPairing.create(discord_user_id=discord_user_id, team=team)

    return f"Paired to **{team.name}** (team #{team.id}). You can now chat with your team."


def get_pairing(discord_user_id: str) -> DiscordPairing | None:
    return (
        DiscordPairing.select()
        .where(DiscordPairing.discord_user_id == discord_user_id)
        .first()
    )


# ── Orchestrate ──────────────────────────────────────────────────────────────


def _get_cloned_candidates(team: Team) -> tuple[Candidate | None, list[Candidate]]:
    """Return (pm_or_lead, all_cloned) for a team."""
    cloned: list[Candidate] = []
    pm_candidate: Candidate | None = None
    for slot in team.slots.order_by(RoleSlot.id):
        first = slot.candidates.first()
        if first and first.dna_cloned:
            cloned.append(first)
            if slot.role == "pm" and pm_candidate is None:
                pm_candidate = first
    lead = pm_candidate or (cloned[0] if cloned else None)
    return lead, cloned


async def run_orchestrate(team: Team, user_text: str) -> str:
    """Run the full PM orchestrate flow and return a formatted response string."""
    lead, cloned = _get_cloned_candidates(team)
    if not cloned or not lead:
        return "No cloned candidates on this team yet. Clone DNA first via the web UI."

    workspace = _workspace_for_team(team.id)
    team_id = team.id

    with db.atomic():
        ChatMessage.create(
            team=team_id, thread="orchestrate", sender="user", content=user_text,
        )

    orch_history = [
        m.to_dict()
        for m in ChatMessage.select()
        .where(ChatMessage.team == team_id, ChatMessage.thread == "orchestrate")
        .order_by(ChatMessage.created_at)
    ]

    parts: list[str] = []
    lead_handle = lead.github_handle

    # ── PM phase ─────────────────────────────────────────────────────────
    collected: list[str] = []

    def pm_emit(event: dict):
        tok = event.get("token")
        if tok:
            collected.append(tok)

    pm_text = await asyncio.to_thread(
        grok_chat,
        candidate=lead.to_dict(),
        history=orch_history,
        emit=pm_emit,
        workspace_dir=workspace,
        tools=TOOL_SCHEMAS,
    )

    if pm_text:
        with db.atomic():
            ChatMessage.create(
                team=team_id, thread="orchestrate",
                sender=lead_handle, content=pm_text,
            )
        parts.append(f"**@{lead_handle}** (PM):\n{pm_text}")

    # ── Assign tasks ─────────────────────────────────────────────────────
    specialists = [c for c in cloned if c.github_handle != lead_handle]
    assignments = await asyncio.to_thread(
        assign_tasks, pm_text, specialists, user_text, workspace,
    )

    # ── Specialist phases ────────────────────────────────────────────────
    handle_map = {c.github_handle: c for c in specialists}
    for assignment in assignments:
        spec_handle = assignment.get("handle", "")
        task = assignment.get("task", user_text)
        spec = handle_map.get(spec_handle)
        if not spec:
            continue

        spec_collected: list[str] = []

        def spec_emit(event: dict, _buf=spec_collected):
            tok = event.get("token")
            if tok:
                _buf.append(tok)

        spec_text = await asyncio.to_thread(
            grok_chat,
            candidate=spec.to_dict(),
            history=[{"sender": "user", "content": task}],
            emit=spec_emit,
            workspace_dir=workspace,
            tools=TOOL_SCHEMAS,
        )

        if spec_text:
            with db.atomic():
                ChatMessage.create(
                    team=team_id, thread="orchestrate",
                    sender=spec_handle, content=spec_text,
                )
            parts.append(f"**@{spec_handle}** ({spec.role_slot.role}):\n{spec_text}")

    return "\n\n---\n\n".join(parts) if parts else "No response generated."


# ── Bot setup ────────────────────────────────────────────────────────────────


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info("Bot online as %s (id %s)", client.user, client.user.id)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return

    user_id = str(message.author.id)
    text = message.content.strip()
    if not text:
        return

    pairing = get_pairing(user_id)

    if not pairing:
        result = try_pair(user_id, text)
        if result:
            await message.reply(result)
        else:
            await message.reply(
                "Send me your team's pairing code to get started. "
                "You can find it on your team page in the web UI."
            )
        return

    team = pairing.team

    async with message.channel.typing():
        try:
            response = await run_orchestrate(team, text)
        except Exception as e:
            logger.exception("Orchestrate failed for team %s", team.id)
            await message.reply(f"Something went wrong: {e}")
            return

    for chunk in _split_message(response):
        await message.reply(chunk)


async def start_bot() -> None:
    """Start the Discord bot. Runs until the client is closed or token is missing."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.info("DISCORD_BOT_TOKEN not set — Discord bot disabled")
        return
    logger.info("Starting Discord bot...")
    await client.start(token)
