ALTER TABLE jobs.jobs ADD job_priority integer DEFAULT 0 NOT NULL;
ALTER TABLE jobs.tasks ADD task_priority integer DEFAULT 0 NOT NULL;
