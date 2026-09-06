-- Cloud SQL Studio-safe GlobeSync user purge.
--
-- How to use:
-- 1) Edit the single row in purge_params below.
-- 2) Leave apply = FALSE to preview the scoped row counts without deleting data.
-- 3) Set apply = TRUE only when you are ready to execute the purge.
-- 4) Run the separate GCS cleanup script before this database purge so object paths can still be resolved.

BEGIN;

CREATE TEMP TABLE purge_params AS
SELECT
  FALSE::boolean AS apply,
  'srivnamrata@gmail.com'::text AS email_1,
  'roboplaylab@gmail.com'::text AS email_2;

CREATE TEMP TABLE target_users AS
SELECT u.id, u.email
FROM users u
CROSS JOIN purge_params p
WHERE lower(u.email) = lower(p.email_1)
   OR (
        nullif(btrim(p.email_2), '') IS NOT NULL
        AND lower(u.email) = lower(p.email_2)
      );

CREATE TEMP TABLE target_workspaces AS
SELECT DISTINCT w.id
FROM workspaces w
WHERE w.owner_user_id IN (SELECT id FROM target_users);

CREATE TEMP TABLE target_projects AS
SELECT DISTINCT p.id
FROM projects p
WHERE p.workspace_id IN (SELECT id FROM target_workspaces)
   OR p.owner_user_id IN (SELECT id FROM target_users)
   OR p.created_by_user_id IN (SELECT id FROM target_users);

CREATE TEMP TABLE target_media_files AS
SELECT DISTINCT m.id
FROM media_files m
WHERE m.project_id IN (SELECT id FROM target_projects)
   OR m.workspace_id IN (SELECT id FROM target_workspaces)
   OR m.user_id IN (SELECT id FROM target_users);

CREATE TEMP TABLE target_transcripts AS
SELECT DISTINCT t.id
FROM transcripts t
WHERE t.project_id IN (SELECT id FROM target_projects)
   OR t.workspace_id IN (SELECT id FROM target_workspaces)
   OR t.media_file_id IN (SELECT id FROM target_media_files);

CREATE TEMP TABLE target_segments AS
SELECT ts.id
FROM transcript_segments ts
WHERE ts.transcript_id IN (SELECT id FROM target_transcripts);

CREATE TEMP TABLE target_translations AS
SELECT DISTINCT tr.id
FROM translations tr
WHERE tr.project_id IN (SELECT id FROM target_projects)
   OR tr.workspace_id IN (SELECT id FROM target_workspaces)
   OR tr.transcript_segment_id IN (SELECT id FROM target_segments);

CREATE TEMP TABLE target_lipsync_jobs AS
SELECT DISTINCT lj.id
FROM lipsync_jobs lj
WHERE lj.project_id IN (SELECT id FROM target_projects)
   OR lj.workspace_id IN (SELECT id FROM target_workspaces)
   OR lj.media_file_id IN (SELECT id FROM target_media_files)
   OR lj.transcript_id IN (SELECT id FROM target_transcripts);

CREATE TEMP TABLE target_export_jobs AS
SELECT DISTINCT ej.id
FROM export_jobs ej
WHERE ej.project_id IN (SELECT id FROM target_projects)
   OR ej.workspace_id IN (SELECT id FROM target_workspaces)
   OR ej.media_file_id IN (SELECT id FROM target_media_files)
   OR ej.transcript_id IN (SELECT id FROM target_transcripts);

CREATE TEMP TABLE target_pipeline_operations AS
SELECT DISTINCT po.id
FROM pipeline_operations po
WHERE po.project_id IN (SELECT id FROM target_projects)
   OR po.workspace_id IN (SELECT id FROM target_workspaces)
   OR po.media_file_id IN (SELECT id FROM target_media_files)
   OR po.transcript_id IN (SELECT id FROM target_transcripts);

CREATE TEMP TABLE target_upload_sessions AS
SELECT DISTINCT us.id
FROM upload_sessions us
WHERE us.workspace_id IN (SELECT id FROM target_workspaces)
   OR us.user_id IN (SELECT id FROM target_users)
   OR us.media_file_id IN (SELECT id FROM target_media_files);

SELECT 'target_users' AS scope, count(*) AS row_count FROM target_users
UNION ALL
SELECT 'target_workspaces', count(*) FROM target_workspaces
UNION ALL
SELECT 'target_projects', count(*) FROM target_projects
UNION ALL
SELECT 'target_media_files', count(*) FROM target_media_files
UNION ALL
SELECT 'target_transcripts', count(*) FROM target_transcripts
UNION ALL
SELECT 'target_segments', count(*) FROM target_segments
UNION ALL
SELECT 'target_translations', count(*) FROM target_translations
UNION ALL
SELECT 'target_lipsync_jobs', count(*) FROM target_lipsync_jobs
UNION ALL
SELECT 'target_export_jobs', count(*) FROM target_export_jobs
UNION ALL
SELECT 'target_pipeline_operations', count(*) FROM target_pipeline_operations
UNION ALL
SELECT 'target_upload_sessions', count(*) FROM target_upload_sessions
ORDER BY scope;

DO $$
DECLARE
  v_apply boolean;
  v_email_1 text;
  v_email_2 text;
BEGIN
  SELECT apply, email_1, nullif(btrim(email_2), '')
  INTO v_apply, v_email_1, v_email_2
  FROM purge_params;

  IF NOT EXISTS (SELECT 1 FROM target_users) THEN
    RAISE EXCEPTION 'No matching users found for %, %', v_email_1, coalesce(v_email_2, '');
  END IF;

  IF v_apply THEN
    RAISE NOTICE 'APPLY=true confirmed. Proceeding with hard delete.';
  ELSE
    RAISE NOTICE 'Preview only. No rows will be deleted. Set purge_params.apply = TRUE to execute.';
  END IF;
END $$;

DELETE FROM generated_audios
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND translation_id IN (SELECT id FROM target_translations);

DELETE FROM frame_metadata
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND (
    lipsync_job_id IN (SELECT id FROM target_lipsync_jobs)
    OR transcript_segment_id IN (SELECT id FROM target_segments)
    OR translation_id IN (SELECT id FROM target_translations)
  );

DELETE FROM upload_chunks
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND session_id IN (SELECT id FROM target_upload_sessions);

DELETE FROM voice_profiles
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND project_id IN (SELECT id FROM target_projects);

DELETE FROM translations
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_translations);

DELETE FROM transcript_segments
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_segments);

DELETE FROM project_versions
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND project_id IN (SELECT id FROM target_projects);

DELETE FROM project_drafts
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND project_id IN (SELECT id FROM target_projects);

DELETE FROM pipeline_operations
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_pipeline_operations);

DELETE FROM export_jobs
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_export_jobs);

DELETE FROM lipsync_jobs
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_lipsync_jobs);

DELETE FROM upload_sessions
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_upload_sessions);

DELETE FROM transcripts
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_transcripts);

DELETE FROM media_files
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_media_files);

DELETE FROM projects
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_projects);

DELETE FROM workspace_members
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND (
    workspace_id IN (SELECT id FROM target_workspaces)
    OR user_id IN (SELECT id FROM target_users)
  );

DELETE FROM workspaces
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_workspaces);

DELETE FROM users
WHERE EXISTS (SELECT 1 FROM purge_params WHERE apply)
  AND id IN (SELECT id FROM target_users);

COMMIT;
