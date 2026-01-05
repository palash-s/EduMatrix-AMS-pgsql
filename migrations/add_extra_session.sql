-- Migration: Add Extra Session support
-- Run this script to update your database schema

-- 1. Create the extra_session table
CREATE TABLE IF NOT EXISTS extra_session (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subject(subject_id),
    teacher_id VARCHAR(36) NOT NULL REFERENCES staff_profile(staff_id),
    section_id INTEGER NOT NULL REFERENCES class_section(section_id),
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    topic VARCHAR(255),
    meeting_link VARCHAR(500),
    status VARCHAR(20) DEFAULT 'Scheduled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add extra_session_id column to session_log (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'session_log' AND column_name = 'extra_session_id'
    ) THEN
        ALTER TABLE session_log ADD COLUMN extra_session_id INTEGER REFERENCES extra_session(id);
    END IF;
END $$;

-- 3. Make schedule_id nullable in session_log (if not already)
ALTER TABLE session_log ALTER COLUMN schedule_id DROP NOT NULL;

-- 4. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_extra_session_teacher ON extra_session(teacher_id);
CREATE INDEX IF NOT EXISTS idx_extra_session_section ON extra_session(section_id);
CREATE INDEX IF NOT EXISTS idx_extra_session_date ON extra_session(date);
CREATE INDEX IF NOT EXISTS idx_session_log_extra ON session_log(extra_session_id);

-- Done!