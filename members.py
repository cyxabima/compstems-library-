"""Member registration and validation."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

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
