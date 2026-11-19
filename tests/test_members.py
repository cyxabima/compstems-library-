"""Tests for member registration validation."""

import unittest

from members import InvalidMemberError, Member


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


if __name__ == "__main__":
    unittest.main()
