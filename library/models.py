"""Domain models for the library management system."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Book:
    """A book in the catalogue together with its copy counts."""

    id: str
    title: str
    author: str
    isbn: str
    category: str
    total_copies: int
    available_copies: int

    def __post_init__(self) -> None:
        for field_name in ("id", "title", "author", "isbn", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        for field_name in ("total_copies", "available_copies"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative")

        if self.available_copies > self.total_copies:
            raise ValueError("available_copies cannot exceed total_copies")

    @property
    def is_available(self) -> bool:
        """Return True when at least one copy can be lent."""
        return self.available_copies > 0
