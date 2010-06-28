CREATE SCHEMA build;
SET search_path = build, pg_catalog;


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
    trove_state integer NOT NULL,
    trove_status text NOT NULL,
    PRIMARY KEY ( job_uuid, source_version, build_flavor, build_context )
);


-- build.jobs
CREATE TABLE jobs (
    job_uuid uuid PRIMARY KEY REFERENCES jobs.jobs ON UPDATE CASCADE ON DELETE CASCADE,
    job_id bigserial UNIQUE NOT NULL,
    job_name text UNIQUE
);
