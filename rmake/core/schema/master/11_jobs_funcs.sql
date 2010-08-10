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
