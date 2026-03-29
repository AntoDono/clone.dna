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
import json
import logging
import os
import re
from pathlib import Path

import discord

from db import db
from models import Team, RoleSlot, Candidate, ChatMessage, DiscordPairing
from trainer import openrouter_chat
# from trainer import claude_chat
from trainer.orchestrator import assign_tasks, build_pm_prompt
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


EDIT_INTERVAL = 1.5  # seconds between discord message edits

_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _clean_tool_calls(text: str) -> str:
    """Replace raw <tool_call> blocks with readable summaries."""
    import json as _json

    def _replace(m: re.Match) -> str:
        try:
            tc = _json.loads(m.group(1))
            name = tc.get("name", "unknown")
            args = tc.get("arguments", {})
            if name == "run_command":
                return f"`ran: {args.get('command', '?')}`"
            if name == "write_file":
                return f"`wrote: {args.get('path', '?')}`"
            if name == "edit_file":
                return f"`edited: {args.get('path', '?')}`"
            if name == "read_file":
                return f"`read: {args.get('path', '?')}`"
            if name == "create_folder":
                return f"`mkdir: {args.get('path', '?')}`"
            if name == "list_files":
                return f"`ls: {args.get('path', '.')}`"
            if name == "attach_file":
                return f"`attach: {args.get('path', '?')}`"
            return f"`{name}: {', '.join(f'{k}={v}' for k, v in args.items())}`"
        except Exception:
            return "`(tool call)`"

    return _TOOL_CALL_RE.sub(_replace, text)


_ATTACH_PREFIX = "__ATTACHMENT__:"


async def _stream_speaker(
    channel: discord.DMChannel,
    label: str,
    candidate: Candidate,
    history: list[dict],
    workspace: str,
) -> str:
    """Run claude_chat for one speaker, streaming edits to a Discord message.
    Returns the full response text."""
    buf: list[str] = []
    pending_attachments: list[dict] = []

    def emit(event: dict):
        tok = event.get("token")
        if tok:
            buf.append(tok)
        tr = event.get("tool_result")
        if tr and isinstance(tr.get("output"), str) and tr["output"].startswith(_ATTACH_PREFIX):
            try:
                att = json.loads(tr["output"][len(_ATTACH_PREFIX):])
                pending_attachments.append(att)
            except Exception:
                pass

    task = asyncio.to_thread(
        # claude_chat,
        openrouter_chat,
        candidate=candidate.to_dict(),
        history=history,
        emit=emit,
        workspace_dir=workspace,
        tools=TOOL_SCHEMAS,
    )

    msg = await channel.send(f"**{label}**\n...")
    last_len = 0

    async def poll_edits():
        nonlocal last_len
        while True:
            await asyncio.sleep(EDIT_INTERVAL)
            text = _clean_tool_calls("".join(buf))
            if len(text) > last_len:
                last_len = len(text)
                display = f"**{label}**\n{text}"
                if len(display) > DISCORD_MAX_LEN:
                    display = display[:DISCORD_MAX_LEN - 4] + " ..."
                try:
                    await msg.edit(content=display)
                except discord.HTTPException:
                    pass

    edit_task = asyncio.create_task(poll_edits())
    try:
        full_text = await task
    finally:
        edit_task.cancel()

    cleaned = _clean_tool_calls(full_text) if full_text else ""
    final = f"**{label}**\n{cleaned}" if cleaned else f"**{label}**\n*(no response)*"
    chunks = _split_message(final)
    try:
        await msg.edit(content=chunks[0])
    except discord.HTTPException:
        pass
    for extra in chunks[1:]:
        await channel.send(extra)

    ws_path = Path(workspace).resolve()
    for att in pending_attachments:
        file_path = (ws_path / att["path"]).resolve()
        if str(file_path).startswith(str(ws_path)) and file_path.is_file():
            try:
                await channel.send(file=discord.File(str(file_path), filename=att["name"]))
            except discord.HTTPException as exc:
                await channel.send(f"⚠️ Could not attach `{att['name']}`: {exc}")

    return full_text


async def run_orchestrate(team: Team, user_text: str, channel: discord.DMChannel) -> None:
    """Run the full PM orchestrate flow, streaming each speaker to Discord."""
    lead, cloned = _get_cloned_candidates(team)
    if not cloned or not lead:
        await channel.send("No cloned candidates on this team yet. Clone DNA first via the web UI.")
        return

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

    lead_handle = lead.github_handle

    # ── PM phase ─────────────────────────────────────────────────────────
    pm_history = list(orch_history)
    if pm_history and pm_history[-1].get("sender") == "user":
        enriched = build_pm_prompt(pm_history[-1]["content"], cloned, workspace)
        pm_history[-1] = {**pm_history[-1], "content": enriched}

    pm_text = await _stream_speaker(
        channel, f"@{lead_handle} (PM)", lead, pm_history, workspace,
    )

    # Strip delegation tag from PM text before saving/displaying
    wants_delegate = True
    if pm_text:
        if "[NO_DELEGATE]" in pm_text:
            wants_delegate = False
            pm_text = pm_text.replace("[NO_DELEGATE]", "").rstrip()
        elif "[DELEGATE]" in pm_text:
            pm_text = pm_text.replace("[DELEGATE]", "").rstrip()

    if pm_text:
        with db.atomic():
            ChatMessage.create(
                team=team_id, thread="orchestrate",
                sender=lead_handle, content=pm_text,
            )

    # ── Assign tasks ─────────────────────────────────────────────────────
    specialists = [c for c in cloned if c.github_handle != lead_handle]
    assignments: list[dict] = []
    if wants_delegate and specialists:
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

        spec_text = await _stream_speaker(
            channel,
            f"@{spec_handle} ({spec.role_slot.role})",
            spec,
            [{"sender": "user", "content": task}],
            workspace,
        )

        if spec_text:
            with db.atomic():
                ChatMessage.create(
                    team=team_id, thread="orchestrate",
                    sender=spec_handle, content=spec_text,
                )


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

    pair_result = try_pair(user_id, text)
    if pair_result:
        await message.reply(pair_result)
        return

    if not pairing:
        await message.reply(
            "Send me your team's pairing code to get started. "
            "You can find it on your team page in the web UI."
        )
        return

    team = pairing.team

    try:
        await run_orchestrate(team, text, message.channel)
    except Exception as e:
        logger.exception("Orchestrate failed for team %s", team.id)
        await message.reply(f"Something went wrong: {e}")


async def start_bot() -> None:
    """Start the Discord bot. Runs until the client is closed or token is missing."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.info("DISCORD_BOT_TOKEN not set — Discord bot disabled")
        return
    try:
        logger.info("Starting Discord bot...")
        await client.start(token)
    except Exception:
        logger.exception("Discord bot crashed")
