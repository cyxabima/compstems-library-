"""Member registration and validation."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MEMBERS_PATH = Path(__file__).resolve().parent / "data" / "members.json"

_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)


class MemberError(ValueError):
    """Base class for member registration errors."""


class InvalidMemberError(MemberError):
    """Raised when a member's name or email is missing or invalid."""


class DuplicateEmailError(MemberError):
    """Raised when an email address is already registered."""


def normalize_name(name: str) -> str:
    """Return a trimmed member name, rejecting blank values."""
    if not isinstance(name, str) or not name.strip():
        raise InvalidMemberError("Name is required")
    return name.strip()


def normalize_email(email: str) -> str:
    """Return a trimmed, lower-case email, rejecting invalid addresses."""
    if not isinstance(email, str) or not email.strip():
        raise InvalidMemberError("Email is required")

    normalized = email.strip().casefold()
    if not _EMAIL_PATTERN.fullmatch(normalized):
        raise InvalidMemberError("A valid email is required")
    return normalized


@dataclass(frozen=True, slots=True)
class Member:
    """A registered library member."""

    name: str
    email: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", normalize_name(self.name))
        object.__setattr__(self, "email", normalize_email(self.email))


class MemberRegistry:
    """Keep registered members and enforce unique email addresses."""

    def __init__(self, members: Iterable[Member] = ()) -> None:
        self._members: dict[str, Member] = {}
        for member in members:
            self._add(member)

    def register(self, name: str, email: str) -> Member:
        """Validate and register a member with a unique email address."""
        return self._add(Member(name=name, email=email))

    def _add(self, member: Member) -> Member:
        if member.email in self._members:
            raise DuplicateEmailError(
                f"A member with email {member.email} is already registered"
            )
        self._members[member.email] = member
        return member

    def list_members(self) -> list[Member]:
        """Return registered members sorted by name, then email."""
        return sorted(
            self._members.values(),
            key=lambda member: (member.name.casefold(), member.email),
        )

    def __len__(self) -> int:
        return len(self._members)


class MemberRepository:
    """Read and write the registered-member list as JSON."""

    def __init__(self, path: str | Path = DEFAULT_MEMBERS_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[Member]:
        """Return registered members, or an empty list if the file is missing."""
        if not self.path.exists():
            return []

        try:
            raw = self.path.read_text(encoding="utf-8")
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Member file {self.path} is not valid JSON: {exc.msg}"
            ) from exc
        except OSError as exc:
            raise ValueError(f"Could not read member file {self.path}: {exc}") from exc

        if not isinstance(payload, list):
            raise ValueError(f"Member file {self.path} must contain a JSON list")

        members: list[Member] = []
        seen_emails: set[str] = set()
        for position, entry in enumerate(payload, start=1):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Member entry {position} in {self.path} must be a JSON object"
                )
            try:
                member = Member(**entry)
            except TypeError as exc:
                raise ValueError(
                    f"Member entry {position} in {self.path} does not match "
                    f"the member schema: {exc}"
                ) from exc
            except ValueError as exc:
                raise ValueError(
                    f"Member entry {position} in {self.path} is invalid: {exc}"
                ) from exc

            if member.email in seen_emails:
                raise ValueError(
                    f"Member entry {position} in {self.path} duplicates "
                    f"email {member.email}"
                )
            seen_emails.add(member.email)
            members.append(member)

        return members

    def save(self, members: Iterable[Member]) -> None:
        """Write members to disk, rejecting duplicate email addresses."""
        payload: list[dict[str, str]] = []
        seen_emails: set[str] = set()
        for member in members:
            if member.email in seen_emails:
                raise DuplicateEmailError(
                    f"A member with email {member.email} is already registered"
                )
            seen_emails.add(member.email)
            payload.append({"name": member.name, "email": member.email})

        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Could not save member file {self.path}: {exc}") from exc
