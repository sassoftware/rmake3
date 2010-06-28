SET search_path = public, pg_catalog;


CREATE TABLE database_metadata (
    schema text,
    name text,
    value text
);


-- shorten_uuid
--
-- Returns the last 12 digits of a UUID.
--
CREATE FUNCTION shorten_uuid(uuid) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$ SELECT substring(CAST($1 AS text) from 25) $$;
