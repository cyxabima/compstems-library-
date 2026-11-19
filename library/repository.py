"""JSON-backed storage for the book catalogue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Book

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "books.json"


class BookRepository:
    """Read books from a JSON catalogue file."""

    def __init__(self, path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.path = Path(path)

    def load(self) -> list[Book]:
        """Return the catalogue contents, or an empty list if it does not exist."""
        if not self.path.exists():
            return []

        try:
            raw = self.path.read_text(encoding="utf-8")
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Book catalogue {self.path} is not valid JSON: {exc.msg}") from exc
        except OSError as exc:
            raise ValueError(f"Could not read book catalogue {self.path}: {exc}") from exc

        if not isinstance(payload, list):
            raise ValueError(f"Book catalogue {self.path} must contain a JSON list")

        books: list[Book] = []
        for position, entry in enumerate(payload, start=1):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"Book entry {position} in {self.path} must be a JSON object"
                )
            try:
                books.append(Book(**entry))
            except TypeError as exc:
                raise ValueError(
                    f"Book entry {position} in {self.path} does not match "
                    f"the book schema: {exc}"
                ) from exc
            except ValueError as exc:
                raise ValueError(
                    f"Book entry {position} in {self.path} is invalid: {exc}"
                ) from exc

        return books
