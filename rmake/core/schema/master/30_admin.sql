CREATE SCHEMA admin;
SET search_path = admin;


-- admin.workers
-- List of workers that are permitted to connect.
CREATE TABLE permitted_workers (
    worker_jid text PRIMARY KEY
);
