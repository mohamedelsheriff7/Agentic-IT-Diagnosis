from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Settings:
    database_url: str = 'sqlite:///./workstream.db'
    api_key: str = ''
    admin_api_key: str = ''
    demo_clock: str = '2026-10-01T12:00:00Z'
    public_base_url: str = ''

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv()
        return cls(**{k: os.getenv(k.upper(), f.default) for k, f in cls.__dataclass_fields__.items()})

    def now(self):
        value = datetime.fromisoformat(self.demo_clock.replace('Z', '+00:00')) if self.demo_clock else datetime.now(timezone.utc)
        if value.tzinfo is None:
            raise ValueError('DEMO_CLOCK must include a timezone')
        return value.astimezone(timezone.utc)
