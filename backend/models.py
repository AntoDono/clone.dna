import json
from datetime import datetime
from peewee import (
    Model,
    CharField,
    TextField,
    IntegerField,
    BooleanField,
    DateTimeField,
    ForeignKeyField,
)
from db import db


class BaseModel(Model):
    class Meta:
        database = db


class Team(BaseModel):
    name = CharField()
    discord_pair_code = CharField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "discord_pair_code": self.discord_pair_code,
            "created_at": self.created_at.isoformat(),
            "slots": [s.to_dict() for s in self.slots.order_by(RoleSlot.id)],
        }


class RoleSlot(BaseModel):
    team = ForeignKeyField(Team, backref="slots", on_delete="CASCADE")
    role = CharField()        # 'pm' | 'swe' | 'designer'
    slot_index = IntegerField(default=0)
    filled = BooleanField(default=False)

    def to_dict(self) -> dict:
        candidate = None
        first = self.candidates.first()
        if first:
            candidate = first.to_dict()
        return {
            "id": self.id,
            "role": self.role,
            "slot_index": self.slot_index,
            "filled": self.filled,
            "candidate": candidate,
        }


class Candidate(BaseModel):
    role_slot = ForeignKeyField(RoleSlot, backref="candidates", null=True, on_delete="SET NULL")
    github_handle = CharField()
    name = CharField(null=True)
    avatar_url = CharField(null=True)
    bio = TextField(null=True)
    location = CharField(null=True)
    followers = IntegerField(default=0)
    public_repos = IntegerField(default=0)
    top_repos = TextField(default="[]")   # JSON list
    languages = TextField(default="{}")   # JSON dict
    skills = TextField(default="[]")      # JSON list — technical + soft, ordered by relevance
    soft_skills = TextField(default="[]") # JSON list — soft/interpersonal skills
    description = TextField(null=True)    # generated role-fit summary sentence
    profile_url = CharField(null=True)
    selected_at = DateTimeField(null=True)
    dna_cloned    = BooleanField(default=False)
    dna_path      = CharField(null=True)   # e.g. "dnas/1/torvalds"
    dna_cloned_at = DateTimeField(null=True)
    system_prompt = TextField(null=True)   # generated identity prompt saved after clone-dna
    personality_profile = TextField(null=True)  # JSON: structured personality/style analysis

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "github_handle": self.github_handle,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "location": self.location,
            "followers": self.followers,
            "public_repos": self.public_repos,
            "top_repos": json.loads(self.top_repos or "[]"),
            "languages": json.loads(self.languages or "{}"),
            "skills": json.loads(self.skills or "[]"),
            "soft_skills": json.loads(self.soft_skills or "[]"),
            "description": self.description,
            "profile_url": self.profile_url,
            "selected_at": self.selected_at.isoformat() if self.selected_at else None,
            "dna_cloned": self.dna_cloned,
            "dna_path": self.dna_path,
            "dna_cloned_at": self.dna_cloned_at.isoformat() if self.dna_cloned_at else None,
            "system_prompt": self.system_prompt,
            "personality_profile": json.loads(self.personality_profile) if self.personality_profile else None,
        }


class ChatMessage(BaseModel):
    team       = ForeignKeyField(Team, backref="messages", on_delete="CASCADE")
    thread     = CharField()     # github_handle for DMs, "orchestrate" for PM orchestration
    sender     = CharField()     # "user" | github_handle | "orchestrate"
    content    = TextField()
    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "thread": self.thread,
            "sender": self.sender,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class DiscordPairing(BaseModel):
    discord_user_id = CharField(unique=True)
    team = ForeignKeyField(Team, backref="discord_pairings", on_delete="CASCADE")
    paired_at = DateTimeField(default=datetime.utcnow)
