# ExamFlow — Examination Management Portal (MAD-1 reference application)

## Folder structure

```text
EMP_Modern_Project/
  app.py                  Flask routes, validation, role authorization
  models.py               SQLite schema / table relationships
  requirements.txt        Python dependencies
  templates/              Jinja2 HTML pages
  static/style.css        Custom responsive design with Bootstrap
  README.md               Instructions
```

## How to run on Windows with VS Code

Open **the inner EMP_Modern_Project folder containing app.py**, then use **Terminal > New Terminal**:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000/login

If PowerShell denies activation, run `Set-ExecutionPolicy -Scope Process Bypass` and try activating again. Alternatively run `.\.venv\Scripts\python.exe app.py` without activation (after installing with that Python executable).

**All tables are created automatically** on first start in `emp.sqlite3`. No manual database creation is needed.

## Local demonstration accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@emp.local | ChangeMe123! |
| Examiner | examiner@emp.local | Examiner123! |
| Student | student@emp.local | Student123! |

The demo Examiner is already approved so you can demonstrate immediately. Newly registered Examiner accounts still require an Admin to approve them on **Users / Approvals**. Change default passwords before any deployment; only use these accounts locally.

If your existing database was created by a previous project with the same filename, **do not blindly delete it**. First back up `emp.sqlite3`; for a fresh demo you can rename the old file to `emp-backup.sqlite3` while the server is stopped.

## Suggested end-to-end demo

1. Admin login > Courses: add `MAD101` / `Modern Application Development`.
2. Admin > Exams: create an exam, with a creation date window including today and a future booking date window; set status `slot_creation`.
3. Admin > Manage (beside exam): assign **Demo Examiner** and add rubrics. Keep sum of rubric maximum marks within exam maximum.
4. Examiner login > Slots: create a future slot within the creation date window.
5. Admin login > Exams: edit the exam and change status to `booking_open`. Set booking window to include today.
6. Student login > Slots: book a seat. Test duplicate booking prevention. View Bookings.
7. Examiner login > Bookings: evaluate booked students; Admin > Manage: publish results; Student > Bookings: see feedback and marks.
8. Admin can reschedule bookings and reassign examiners when required.

The browser form inputs validate basic values; `app.py` checks role permissions, dates, capacity, duplicate bookings and ownership again on the server.

## Git repository (PRIVATE)

Create an empty **private** repository on GitHub, open the project folder, then:

```powershell
git init -b main
git add .
git commit -m "Build my examination portal"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_PRIVATE_REPO.git
git push -u origin main
```

Do not upload your SQLite database, `.venv` or secret keys. `.gitignore` excludes these. Git tracker registration and development history are separate course requirements: follow official instructions.

## Submission ZIP and academic integrity

The ZIP has a **single top-level project directory** containing `.py` files. Run the course's official ZIP validation before uploading. Prepare your own <=5-page report with an ER diagram, video link, truthful AI/LLM declaration and project details. Record a 5–10 minute demonstration, upload as a viewable Drive link. Only submit code that you have tested, understand and can modify during the viva.

Bootstrap CSS uses a CDN for styling; an internet connection improves the presentation, but the Flask/SQLite app runs locally.
