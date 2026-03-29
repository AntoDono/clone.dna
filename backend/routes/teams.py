"""
Teams router — CRUD for teams and role slots.

Each team has a fixed layout of 4 role slots (1 PM, 2 SWE, 1 Designer) created
atomically on team creation. Deleting a team cascades to all slots, candidates,
and chat messages.
"""

import json
import secrets
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticModel

from db import db
from models import Team, RoleSlot, Candidate

router = APIRouter()

ROLE_LAYOUT = [
    {"role": "pm",       "slot_index": 0},
    {"role": "swe",      "slot_index": 0},
    {"role": "swe",      "slot_index": 1},
    {"role": "designer", "slot_index": 0},
]

JSON_FIELDS = {"top_repos", "languages", "skills", "soft_skills",
               "architectural_patterns", "code_quality_signals", "domain_expertise"}


class CreateTeamRequest(PydanticModel):
    name: str


@router.post("/teams", status_code=201)
def create_team(body: CreateTeamRequest):
    """Create a team with a fixed layout of 4 role slots (1 PM, 2 SWE, 1 Designer), generated atomically."""
    with db.atomic():
        pair_code = secrets.token_hex(3)
        team = Team.create(name=body.name.strip(), discord_pair_code=pair_code)
        for r in ROLE_LAYOUT:
            RoleSlot.create(team=team, role=r["role"], slot_index=r["slot_index"])
    return team.to_dict()


@router.get("/teams")
def list_teams():
    """Return all teams ordered by creation date descending."""
    return [t.to_dict() for t in Team.select().order_by(Team.created_at.desc())]


@router.get("/teams/{team_id}")
def get_team(team_id: int):
    """Return a single team with all role slots and their assigned candidates."""
    try:
        return Team.get_by_id(team_id).to_dict()
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(team_id: int):
    """Delete a team and all associated role slots, candidates, and messages."""
    try:
        Team.get_by_id(team_id).delete_instance(recursive=True)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")


# ── Shared helpers (also used by candidates router) ───────────────────────────

def get_slot(team_id: int, slot_id: int) -> RoleSlot:
    """Fetch a RoleSlot by ID, verifying it belongs to the specified team. Raises 404 if not found or team mismatch."""
    try:
        slot = RoleSlot.get_by_id(slot_id)
    except RoleSlot.DoesNotExist:
        raise HTTPException(404, "Role slot not found")
    if slot.team_id != team_id:
        raise HTTPException(400, "Slot does not belong to this team")
    return slot


def save_candidate(slot: RoleSlot, profile: dict) -> dict:
    """Persist a candidate profile to a slot inside a transaction, replacing any previous candidate and marking the slot as filled."""
    scalar = {k: v for k, v in profile.items() if k not in JSON_FIELDS}
    with db.atomic():
        Candidate.delete().where(Candidate.role_slot == slot).execute()
        candidate = Candidate.create(
            role_slot=slot,
            selected_at=datetime.utcnow(),
            top_repos=json.dumps(profile.get("top_repos", [])),
            languages=json.dumps(profile.get("languages", {})),
            skills=json.dumps(profile.get("skills", [])),
            soft_skills=json.dumps(profile.get("soft_skills", [])),
            architectural_patterns=json.dumps(profile.get("architectural_patterns", [])),
            code_quality_signals=json.dumps(profile.get("code_quality_signals", [])),
            domain_expertise=json.dumps(profile.get("domain_expertise", [])),
            **scalar,
        )
        slot.filled = True
        slot.save()
    return candidate.to_dict()
