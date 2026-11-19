"""Tests for member registration validation."""

import json
import tempfile
import unittest
from pathlib import Path

from members import (
    DuplicateEmailError,
    InvalidMemberError,
    Member,
    MemberRegistry,
    MemberRepository,
)


class MemberValidationTests(unittest.TestCase):
    def test_accepts_valid_member_and_normalizes_details(self) -> None:
        member = Member(name="  Ada Lovelace  ", email="  Ada@Example.COM ")

        self.assertEqual(member.name, "Ada Lovelace")
        self.assertEqual(member.email, "ada@example.com")

    def test_accepts_common_email_formats(self) -> None:
        emails = (
            "ada@example.com",
            "ada.lovelace+library@example.co.uk",
            "ada@sub-domain.example.org",
        )

        for email in emails:
            with self.subTest(email=email):
                self.assertEqual(Member("Ada", email).email, email)

    def test_name_is_required(self) -> None:
        for name in ("", "   ", None):
            with self.subTest(name=name):
                with self.assertRaisesRegex(InvalidMemberError, "Name is required"):
                    Member(name=name, email="ada@example.com")  # type: ignore[arg-type]

    def test_email_is_required(self) -> None:
        for email in ("", "   ", None):
            with self.subTest(email=email):
                with self.assertRaisesRegex(InvalidMemberError, "Email is required"):
                    Member(name="Ada", email=email)  # type: ignore[arg-type]

    def test_invalid_email_addresses_are_rejected(self) -> None:
        invalid_emails = (
            "ada",
            "ada@",
            "@example.com",
            "ada@example",
            "ada @example.com",
            "ada@@example.com",
            "ada@exa mple.com",
            "ada@example..com",
            "ada@.com",
        )

        for email in invalid_emails:
            with self.subTest(email=email):
                with self.assertRaisesRegex(
                    InvalidMemberError, "A valid email is required"
                ):
                    Member(name="Ada", email=email)

    def test_registration_errors_are_value_errors(self) -> None:
        self.assertTrue(issubclass(InvalidMemberError, ValueError))


class MemberRegistryTests(unittest.TestCase):
    def test_registers_a_valid_member(self) -> None:
        registry = MemberRegistry()

        member = registry.register("  Ada Lovelace  ", "  Ada@Example.COM ")

        self.assertEqual(member.name, "Ada Lovelace")
        self.assertEqual(member.email, "ada@example.com")
        self.assertEqual(registry.list_members(), [member])
        self.assertEqual(len(registry), 1)

    def test_rejects_a_duplicate_email_address(self) -> None:
        registry = MemberRegistry()
        registry.register("Ada Lovelace", "ada@example.com")

        with self.assertRaisesRegex(DuplicateEmailError, "already registered"):
            registry.register("Another Member", "ada@example.com")

        self.assertEqual(len(registry), 1)
        self.assertEqual(registry.list_members()[0].name, "Ada Lovelace")

    def test_duplicate_check_ignores_case_and_surrounding_whitespace(self) -> None:
        registry = MemberRegistry()
        registry.register("Ada Lovelace", "ada@example.com")

        with self.assertRaises(DuplicateEmailError):
            registry.register("Another Member", "  ADA@EXAMPLE.COM  ")

    def test_registration_applies_name_and_email_validation(self) -> None:
        registry = MemberRegistry()

        with self.assertRaisesRegex(InvalidMemberError, "Name is required"):
            registry.register("   ", "ada@example.com")

        with self.assertRaisesRegex(InvalidMemberError, "A valid email is required"):
            registry.register("Ada Lovelace", "not-an-email")

        self.assertEqual(len(registry), 0)

    def test_duplicate_emails_in_the_initial_members_are_rejected(self) -> None:
        members = [
            Member("Ada Lovelace", "ada@example.com"),
            Member("Another Member", "ADA@example.com"),
        ]

        with self.assertRaises(DuplicateEmailError):
            MemberRegistry(members)

    def test_lists_members_sorted_by_name(self) -> None:
        registry = MemberRegistry()
        registry.register("Zoe", "zoe@example.com")
        registry.register("ada", "ada@example.com")
        registry.register("Grace", "grace@example.com")

        names = [member.name for member in registry.list_members()]

        self.assertEqual(names, ["ada", "Grace", "Zoe"])


class MemberRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.path = Path(temp_dir.name) / "members.json"

    def test_missing_file_loads_as_an_empty_list(self) -> None:
        self.assertEqual(MemberRepository(self.path).load(), [])

    def test_saved_members_can_be_loaded_again(self) -> None:
        repository = MemberRepository(self.path)
        members = [
            Member("Ada Lovelace", "ada@example.com"),
            Member("Grace Hopper", "grace@example.com"),
        ]

        repository.save(members)

        self.assertEqual(repository.load(), members)

    def test_load_rejects_duplicate_emails(self) -> None:
        self.path.write_text(
            json.dumps(
                [
                    {"name": "Ada", "email": "ada@example.com"},
                    {"name": "Another", "email": "ADA@example.com"},
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "duplicates email"):
            MemberRepository(self.path).load()

    def test_save_rejects_duplicate_emails(self) -> None:
        repository = MemberRepository(self.path)

        with self.assertRaises(DuplicateEmailError):
            repository.save(
                [
                    Member("Ada", "ada@example.com"),
                    Member("Another", "ada@example.com"),
                ]
            )


if __name__ == "__main__":
    unittest.main()
