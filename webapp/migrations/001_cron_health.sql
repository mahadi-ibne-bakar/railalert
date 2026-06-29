-- Run once in Supabase's SQL Editor.
-- Adds run-health tracking to worker_state, used by the new /internal/cron
-- route (and, later, the admin dashboard) to show when the worker last
-- actually ran successfully.

ALTER TABLE worker_state ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ;
ALTER TABLE worker_state ADD COLUMN IF NOT EXISTS last_run_ok BOOLEAN;
ALTER TABLE worker_state ADD COLUMN IF NOT EXISTS last_run_summary TEXT;
