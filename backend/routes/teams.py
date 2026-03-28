import json
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

JSON_FIELDS = {"top_repos", "languages", "skills", "soft_skills"}


class CreateTeamRequest(PydanticModel):
    name: str


@router.post("/teams", status_code=201)
def create_team(body: CreateTeamRequest):
    with db.atomic():
        team = Team.create(name=body.name.strip())
        for r in ROLE_LAYOUT:
            RoleSlot.create(team=team, role=r["role"], slot_index=r["slot_index"])
    return team.to_dict()


@router.get("/teams")
def list_teams():
    return [t.to_dict() for t in Team.select().order_by(Team.created_at.desc())]


@router.get("/teams/{team_id}")
def get_team(team_id: int):
    try:
        return Team.get_by_id(team_id).to_dict()
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(team_id: int):
    try:
        Team.get_by_id(team_id).delete_instance(recursive=True)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")


# ── Shared helpers (also used by candidates router) ───────────────────────────

def get_slot(team_id: int, slot_id: int) -> RoleSlot:
    try:
        slot = RoleSlot.get_by_id(slot_id)
    except RoleSlot.DoesNotExist:
        raise HTTPException(404, "Role slot not found")
    if slot.team_id != team_id:
        raise HTTPException(400, "Slot does not belong to this team")
    return slot


def save_candidate(slot: RoleSlot, profile: dict) -> dict:
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
            **scalar,
        )
        slot.filled = True
        slot.save()
    return candidate.to_dict()
