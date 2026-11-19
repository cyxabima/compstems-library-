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

## Project structure
```
main.py             Application entry point
library/models.py   Book domain model
library/repository.py JSON catalogue storage
library/service.py  Catalogue operations
library/cli.py      Command-line book list
data/books.json     Sample book catalogue
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

## Running the tests
```bash
python -m unittest
```