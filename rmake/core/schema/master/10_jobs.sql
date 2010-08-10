CREATE SCHEMA jobs;
COMMENT ON SCHEMA jobs IS 'rMake jobs core';
SET search_path = jobs, public, pg_catalog;


-- jobs.jobs
CREATE TABLE jobs (
    job_uuid uuid PRIMARY KEY,
    job_type text NOT NULL,
    owner text NOT NULL,
    status_code smallint DEFAULT 0 NOT NULL,
    status_text text DEFAULT ''::text NOT NULL,
    status_detail text,
    time_started timestamp with time zone DEFAULT now(),
    time_updated timestamp with time zone DEFAULT now() NOT NULL,
    time_finished timestamp with time zone,
    expires_after interval,
    frozen_handler bytea,
    time_ticks integer DEFAULT (-1) NOT NULL,
    frozen_data bytea NOT NULL
);
CREATE INDEX jobs_active ON jobs ((1)) WHERE ( time_finished IS NULL );
CREATE INDEX jobs_uuids_short ON jobs ( public.shorten_uuid(job_uuid) );


-- jobs.tasks
CREATE TABLE tasks (
    task_uuid uuid PRIMARY KEY,
    job_uuid uuid NOT NULL REFERENCES jobs ON UPDATE CASCADE ON DELETE CASCADE,
    task_name text NOT NULL,
    task_type text NOT NULL,
    task_data bytea,
    time_started timestamp with time zone,
    time_finished timestamp with time zone,
    time_updated timestamp with time zone,
    node_assigned text,
    status_code smallint DEFAULT 0 NOT NULL,
    status_text text DEFAULT ''::text NOT NULL,
    status_detail text,
    time_ticks integer DEFAULT (-1) NOT NULL
);


-- jobs.artifacts
CREATE TABLE artifacts (
    job_uuid uuid NOT NULL REFERENCES jobs ON UPDATE CASCADE ON DELETE CASCADE,
    path text NOT NULL,
    size bigint NOT NULL,
    digest text,
    data bytea,
    PRIMARY KEY ( job_uuid, path )
);
COMMENT ON COLUMN artifacts.job_uuid IS 'The job to which this artifact is related.';
COMMENT ON COLUMN artifacts.path IS 'A filesystem-like name for the artifact, unique on a per-job basis.';
COMMENT ON COLUMN artifacts.size IS 'Size of the artifact in bytes.';
COMMENT ON COLUMN artifacts.digest IS 'A cryptographic hash of the artifact contents in the form method:hexstring
It may be NULL if the file is being actively appended to.';
COMMENT ON COLUMN artifacts.data IS 'Contents of the artifact, or NULL if it is on disk.';
