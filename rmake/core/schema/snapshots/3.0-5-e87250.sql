SET search_path = public, pg_catalog;

-- shorten_uuid
--
-- Returns the last 12 digits of a UUID.
--
CREATE FUNCTION shorten_uuid(uuid) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$ SELECT substring(CAST($1 AS text) from 25) $$;
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
    task_zone text,
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
SET search_path = jobs, public, pg_catalog;

-- rmake_set_task
--
-- Inserts or updates the given task, returning the new row. If the update was
-- superseded by a higher-numbered call, the superseding row is returned.
--
CREATE FUNCTION rmake_set_task(
    new_task_uuid uuid, new_job_uuid uuid, new_task_name text, new_task_type text,

    upd_task_data bytea, upd_node_assigned text,
    upd_status_code smallint, upd_status_text text, upd_status_detail text,
    upd_time_ticks integer, upd_is_started boolean, upd_is_finished boolean

    ) RETURNS tasks LANGUAGE plpgsql VOLATILE
    AS $$
DECLARE
    ret jobs.tasks%ROWTYPE;
    v_time_started timestamptz;
    v_time_finished timestamptz;
BEGIN
    IF upd_is_started THEN v_time_started := current_timestamp; END IF;
    IF upd_is_finished THEN v_time_finished := current_timestamp; END IF;

    LOOP
        -- Try to update the existing row, if it's there.
        RAISE WARNING 'pre-update';
        UPDATE jobs.tasks SET
                task_data = upd_task_data,
                node_assigned = upd_node_assigned,
                status_code = upd_status_code,
                status_text = upd_status_text,
                status_detail = upd_status_detail,
                time_ticks = upd_time_ticks,
                time_started = v_time_started,
                time_updated = current_timestamp,
                time_finished = v_time_finished
            WHERE task_uuid = new_task_uuid AND time_ticks < upd_time_ticks
            RETURNING jobs.tasks.*
            INTO ret;

        -- It was there -- return the new row.
        IF FOUND THEN
            RAISE WARNING 'update successful';
            RETURN ret;
        END IF;

        -- It wasn't there -- Has this update been superseded?
        SELECT * INTO ret FROM jobs.tasks WHERE
            task_uuid = new_task_uuid AND time_ticks >= upd_time_ticks;
        IF FOUND THEN
            RAISE WARNING 'select successful';
            RETURN ret;
        END IF;

        -- Not superseded, so try to insert.
        BEGIN
            INSERT INTO jobs.tasks (
                    task_uuid, job_uuid, task_name, task_type,

                    task_data, node_assigned,
                    status_code, status_text, status_detail,
                    time_ticks, time_started, time_updated, time_finished
                ) VALUES (
                    new_task_uuid, new_job_uuid, new_task_name, new_task_type,

                    upd_task_data, upd_node_assigned,
                    upd_status_code, upd_status_text, upd_status_detail,
                    upd_time_ticks, v_time_started, current_timestamp, v_time_finished
                ) RETURNING jobs.tasks.*
                INTO ret;
            RAISE WARNING 'insert successful';
            RETURN ret;
        EXCEPTION WHEN unique_violation THEN
            RAISE WARNING 'insert failed';
            -- Conflict with another client. Go back to square one.
        END;
    END LOOP;
END;
$$;
CREATE SCHEMA build;
SET search_path = build, public, pg_catalog;


-- build.binary_troves
CREATE TABLE binary_troves (
    job_uuid uuid NOT NULL REFERENCES jobs.jobs ON UPDATE CASCADE ON DELETE CASCADE,
    name text NOT NULL,
    version text NOT NULL,
    flavor text NOT NULL
);


-- build.job_troves
CREATE TABLE job_troves (
    job_uuid uuid NOT NULL REFERENCES jobs.jobs ON UPDATE CASCADE ON DELETE CASCADE,
    source_name text NOT NULL,
    source_version text NOT NULL,
    build_flavor text NOT NULL,
    build_context text NOT NULL,
    PRIMARY KEY ( job_uuid, source_version, build_flavor, build_context )
);


-- build.jobs
CREATE TABLE jobs (
    job_uuid uuid PRIMARY KEY REFERENCES jobs.jobs ON UPDATE CASCADE ON DELETE CASCADE,
    job_id bigserial UNIQUE NOT NULL,
    job_name text UNIQUE
);
CREATE SCHEMA admin;
SET search_path = admin;


-- admin.workers
-- List of workers that are permitted to connect.
CREATE TABLE permitted_workers (
    worker_jid text PRIMARY KEY
);
