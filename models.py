"""SQLite data model for Examination Management Portal.
Tables and foreign-key relationships are defined here; created automatically on first run.
"""

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','examiner','student')),
 department TEXT DEFAULT '', approved INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS courses (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS exams (
 id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL REFERENCES courses(id),
 title TEXT NOT NULL, exam_type TEXT NOT NULL, duration INTEGER NOT NULL,
 max_marks INTEGER NOT NULL, creation_start TEXT NOT NULL, creation_end TEXT NOT NULL,
 booking_start TEXT NOT NULL, booking_end TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', published INTEGER NOT NULL DEFAULT 0,
 CHECK (duration>0 AND max_marks>0)
);
CREATE TABLE IF NOT EXISTS assignments (
 exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
 examiner_id INTEGER NOT NULL REFERENCES users(id), PRIMARY KEY(exam_id,examiner_id)
);
CREATE TABLE IF NOT EXISTS rubrics (
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
 criterion TEXT NOT NULL, max_marks INTEGER NOT NULL, description TEXT DEFAULT '', CHECK(max_marks>0)
);
CREATE TABLE IF NOT EXISTS slots (
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL REFERENCES exams(id),
 examiner_id INTEGER NOT NULL REFERENCES users(id), slot_date TEXT NOT NULL,
 start_time TEXT NOT NULL, end_time TEXT NOT NULL, capacity INTEGER NOT NULL,
 cancelled INTEGER NOT NULL DEFAULT 0, CHECK(capacity>0)
);
CREATE TABLE IF NOT EXISTS bookings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id),
 slot_id INTEGER NOT NULL REFERENCES slots(id), booked_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','cancelled','completed'))
);
CREATE TABLE IF NOT EXISTS scores (
 id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
 rubric_id INTEGER NOT NULL REFERENCES rubrics(id), marks INTEGER NOT NULL CHECK(marks>=0),
 UNIQUE(booking_id,rubric_id)
);
CREATE TABLE IF NOT EXISTS evaluations (
 booking_id INTEGER PRIMARY KEY REFERENCES bookings(id) ON DELETE CASCADE,
 remarks TEXT DEFAULT '', evaluated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(slot_id,status);
CREATE INDEX IF NOT EXISTS idx_bookings_student ON bookings(student_id,status);
'''

