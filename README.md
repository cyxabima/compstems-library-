# <UK-H~AS> Library Management System
A simple Library Management System built in two sprints using Scrum and 
GitHub Projects.
## Team and roles
| Role | Name | GitHub username |
| --- | --- | --- |
| Product Owner (PO) | Ukasha Anwer | @cyxabima |
| Scrum Master (SM) | Hamdan Ahmed Siddiqui | @Hamdan-AS |
| Developer | Hamdan Ahmed Siddiqui| @Hamdan-AS |
| Developer |  UK  | @cyxabima |
| Stakeholder | Instructor | @Mahn00rMalik |
## Definition of Done
A user story is Done only when:
- [ ] Every acceptance criterion is met.
- [ ] Code is on a feature branch and merged to `main` through a pull 
request.
- [ ] The other Developer reviewed and approved the pull request.
- [ ] The pull request closes its issue (`Closes #<issue number>`).
- [ ] The program runs with `python main.py` without errors, and `python -m unittest` passes.
- [ ] The PO accepted the story at the Sprint Review

## Features
- **US-02 – List all books:** shows every book with its ID, title, author,
  ISBN, category and available/total copies, sorted by title.
- **US-05 – Member registration validation:** requires a name and a valid
  email, and rejects email addresses that are already registered.
- **US-06 – Issue a book:** lends only available copies, sets a 14-day due
  date, limits members to three active loans, and decrements availability.
- **US-07 – Return a book:** returns a loan by ID, restores one available
  copy, and lists active loans by default.
- **US-08 – Overdue loans and fines:** marks loans past their due date
  `OVERDUE`, charges Rs 10 per day late, and shows the fine on return.
- **US-09 – Dashboard:** shows counts of book titles, members, active loans
  and overdue loans, lists overdue loans, and resets data after confirmation.

## Project structure
```
main.py             Application entry point
library/models.py   Book domain model
library/repository.py JSON catalogue storage
library/service.py  Catalogue operations
library/cli.py      Command-line book list and issue screen
members.py          Member validation, registry and storage
loans.py            Loan rules, fines, storage and loan screens
dashboard.py        Library counts, dashboard and reset screens
data/books.json     Sample book catalogue
data/members.json   Sample registered members
data/loans.json     Recorded loans
tests/              Unit tests
```

## Running the application
Python 3.10 or newer is required; there are no third-party dependencies.

```bash
python main.py
```

The sample catalogue is listed as an aligned table:

```
ID    Title                       Author                      ISBN           Category              Available/Total
----  --------------------------  --------------------------  -------------  --------------------  ---------------
B006  Atomic Habits               James Clear                 9780735211292  Self-Help             2/3
B001  Clean Code                  Robert C. Martin            9780132350884  Software Engineering  2/3
B003  Introduction to Algorithms  Thomas H. Cormen            9780262046305  Computer Science      1/4
B004  Sapiens                     Yuval Noah Harari           9780062316097  History               1/1
B005  The Hobbit                  J. R. R. Tolkien            9780547928227  Fantasy               0/2
B002  The Pragmatic Programmer    Andrew Hunt & David Thomas  9780201616224  Software Engineering  2/2
```

Use another catalogue file with `python main.py --data <path>`.

## Registering members
Member details are validated when a `Member` is created or registered:

```python
from members import MemberRegistry

members = MemberRegistry()
members.register("Ada Lovelace", "ada@example.com")
```

A blank name, missing/invalid email, or an email that is already registered
raises a `ValueError` subclass (`InvalidMemberError` or `DuplicateEmailError`).
Email comparison is case-insensitive.

## Issuing a book
```bash
python main.py --issue
```

The screen lists only books with available copies and the registered members.
Choose a book ID and either a member number or email:

```
Available books:
  B001  Clean Code  (2/3)
Members:
  1. Ada Lovelace <ada@example.com>
Book ID: B001
Member number or email: 1
Issued 'Clean Code' to Ada Lovelace. Due 2026-12-03.
```

A loan is due 14 days after issue, members can hold at most three active
loans, and the available count drops by one. Loans are saved to
`data/loans.json`.

Use `--data`, `--members` and `--loans` to point at other JSON files.

## Returning a book
```bash
python main.py --return
```

The screen lists active loans, then accepts a loan ID:

```
Active loans:
Loan ID  Book   Member         Issued      Due         Returned
-------  -----  -------------  ----------  ----------  --------
L001     Alpha  Ada Lovelace   2026-11-19  2026-12-03  -
Loan ID: L001
Returned 'Alpha' (loan L001). Available copies: 1/2.
```

Returning a loan marks it returned and raises the available copy count by one.

## Listing loans
```bash
python main.py --list-loans
python main.py --list-loans --show-returned
```

Only active loans are shown by default. Add `--show-returned` to include
returned loans.

## Overdue loans and fines
```bash
python main.py --overdue
```

An active loan is overdue once the due date has passed. The screen marks each
loan `OVERDUE` and shows the days late and the fine:

```
Loan ID  Book   Member         Due         Days Late  Fine (Rs)  Status
-------  -----  -------------  ----------  ---------  ---------  -------
L001     Alpha  Ada Lovelace   2026-11-15  3          30         OVERDUE
```

The fine is Rs 10 for each day late. When an overdue book is returned, the
fine is shown with the return confirmation:

```
Returned 'Alpha' (loan L001). Available copies: 1/2.
Overdue by 3 day(s). Fine: Rs 30.
```

## Dashboard
```bash
python main.py --dashboard
```

The dashboard shows the key library counts and then lists every overdue loan:

```
Library dashboard
  Book titles:   6
  Members:       2
  Books on loan: 1
  Overdue loans: 1

Overdue loans:
Loan ID  Book   Member         Due         Days Late  Fine (Rs)  Status
-------  -----  -------------  ----------  ---------  ---------  -------
L001     Alpha  Ada Lovelace   2026-11-15  3          30         OVERDUE
```

## Resetting the library
```bash
python main.py --reset
```

The reset asks for confirmation first and only clears the catalogue, members
and loans when the answer is `y` or `yes`:

```
Reset all library data? [y/N]: n
Reset cancelled.
```

## Running the tests
```bash
python -m unittest
```