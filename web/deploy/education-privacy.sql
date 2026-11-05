CREATE TABLE education.privacy_file_removals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  adult_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  storage_path text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (adult_id, storage_path),
  CHECK (split_part(storage_path, '/', 1) = adult_id::text)
);
ALTER TABLE education.privacy_file_removals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.privacy_file_removals FROM PUBLIC, anon, authenticated, peluqo_backend;

CREATE TABLE education.privacy_resets (
  id uuid PRIMARY KEY,
  adult_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  home_learners integer NOT NULL,
  legacy_learners integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX privacy_resets_adult ON education.privacy_resets (adult_id, created_at);
ALTER TABLE education.privacy_resets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.privacy_resets FROM PUBLIC, anon, authenticated, peluqo_backend;

CREATE TABLE education.privacy_study_deletions (
  adult_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  target_id uuid NOT NULL,
  scope text NOT NULL CHECK (scope IN ('notebook','document')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (adult_id, target_id, scope)
);
ALTER TABLE education.privacy_study_deletions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.privacy_study_deletions FROM PUBLIC, anon, authenticated, peluqo_backend;

ALTER TABLE education.inference_jobs
  ADD COLUMN class_id uuid REFERENCES education.classes(id) ON DELETE SET NULL,
  ADD COLUMN learner_id uuid REFERENCES education.learners(id) ON DELETE SET NULL,
  ADD COLUMN cancelled_at timestamptz;
CREATE INDEX inference_jobs_class ON education.inference_jobs (class_id) WHERE class_id IS NOT NULL;
CREATE INDEX inference_jobs_learner ON education.inference_jobs (learner_id) WHERE learner_id IS NOT NULL;

-- A worker finishing an already cancelled request cannot restore its payload or result.
CREATE FUNCTION education.keep_inference_cancelled()
RETURNS trigger LANGUAGE plpgsql SET search_path = ''
AS $$
BEGIN
  IF OLD.cancelled_at IS NOT NULL OR NEW.cancelled_at IS NOT NULL THEN
    NEW.cancelled_at := COALESCE(OLD.cancelled_at, NEW.cancelled_at);
    NEW.status := 'failed';
    NEW.payload := NULL;
    NEW.result := NULL;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER keep_inference_cancelled BEFORE UPDATE ON education.inference_jobs
FOR EACH ROW EXECUTE FUNCTION education.keep_inference_cancelled();

CREATE FUNCTION education.learning_file_cleanup(p_adult uuid, p_done uuid[] DEFAULT ARRAY[]::uuid[])
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  IF NOT EXISTS (SELECT FROM public.profiles WHERE id = p_adult) THEN RETURN NULL; END IF;
  DELETE FROM education.privacy_file_removals WHERE adult_id = p_adult AND id = ANY(p_done);
  RETURN jsonb_build_object(
    'pendingFiles', (SELECT count(*) FROM education.privacy_file_removals WHERE adult_id = p_adult),
    'files', COALESCE((SELECT jsonb_agg(row) FROM (
      SELECT id, storage_path FROM education.privacy_file_removals WHERE adult_id = p_adult
      ORDER BY created_at, id LIMIT 100
    ) row), '[]'::jsonb)
  );
END;
$$;

CREATE FUNCTION education.reset_learning_data(p_adult uuid, p_confirmation text, p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  home_owner uuid;
  home_classes uuid[];
  own_pupils uuid[];
  class_count integer;
  learner_count integer;
  legacy_count integer;
  receipt education.privacy_resets%ROWTYPE;
BEGIN
  IF p_confirmation IS DISTINCT FROM 'ELIMINAR' OR p_request IS NULL THEN RETURN NULL; END IF;
  PERFORM id FROM public.profiles WHERE id = p_adult FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  SELECT * INTO receipt FROM education.privacy_resets WHERE id = p_request;
  IF FOUND THEN
    IF receipt.adult_id <> p_adult THEN RETURN NULL; END IF;
    RETURN jsonb_build_object(
      'homeLearners', receipt.home_learners, 'legacyLearners', receipt.legacy_learners,
      'pendingFiles', (SELECT count(*) FROM education.privacy_file_removals WHERE adult_id = p_adult)
    );
  END IF;

  SELECT teacher_id INTO home_owner FROM education.home_accounts WHERE family_id = p_adult FOR UPDATE;
  PERFORM id FROM education.classes WHERE teacher_id = home_owner ORDER BY id FOR UPDATE;
  SELECT COALESCE(array_agg(id), ARRAY[]::uuid[]) INTO home_classes
  FROM education.classes WHERE teacher_id = home_owner;

  -- Code revocation and telemetry use the same learner-before-login ordering.
  PERFORM id FROM education.learners WHERE class_id = ANY(home_classes) ORDER BY id FOR UPDATE;
  SELECT COALESCE(array_agg(id), ARRAY[]::uuid[]) INTO own_pupils
  FROM education.learners WHERE class_id = ANY(home_classes);
  PERFORM id FROM education.learners WHERE id IN (
    SELECT learner_id FROM education.family_links WHERE guardian_id = p_adult
  ) ORDER BY id FOR UPDATE;
  PERFORM id FROM public.learners WHERE owner_user_id = p_adult ORDER BY id FOR UPDATE;
  PERFORM id FROM public.notebooks WHERE owner_user_id = p_adult ORDER BY id FOR UPDATE;

  INSERT INTO education.privacy_file_removals (adult_id, storage_path)
  SELECT p_adult, storage_path FROM public.notebook_documents d
  JOIN public.notebooks n ON n.id = d.notebook_id
  WHERE n.owner_user_id = p_adult AND split_part(d.storage_path, '/', 1) = p_adult::text
  ON CONFLICT DO NOTHING;
  INSERT INTO education.privacy_file_removals (adult_id, storage_path)
  SELECT p_adult, name FROM storage.objects
  WHERE bucket_id = 'learner-documents' AND split_part(name, '/', 1) = p_adult::text
  ON CONFLICT DO NOTHING;

  UPDATE education.inference_jobs SET cancelled_at = clock_timestamp()
  WHERE class_id = ANY(home_classes) OR learner_id = ANY(own_pupils);
  UPDATE education.logins SET revoked = true WHERE learner_id = ANY(own_pupils) AND NOT revoked;
  UPDATE education.devices SET revoked = true, learner_id = NULL, session_id = NULL, ack = 0
  WHERE learner_id = ANY(own_pupils) OR teacher_id = home_owner;

  -- School records belong to their classroom. Only this adult's relationship is removed.
  DELETE FROM education.family_links WHERE guardian_id = p_adult;
  UPDATE education.family_codes SET redeemed_by = NULL WHERE redeemed_by = p_adult;
  UPDATE education.access_codes SET state = 'revoked', issued_by = NULL WHERE issued_by = p_adult;
  DELETE FROM education.study_priorities WHERE adult_id = p_adult;
  DELETE FROM education.learners WHERE id = ANY(own_pupils);
  GET DIAGNOSTICS learner_count = ROW_COUNT;
  DELETE FROM education.documents WHERE class_id = ANY(home_classes);
  DELETE FROM education.versions WHERE class_id = ANY(home_classes);
  DELETE FROM education.classes WHERE id = ANY(home_classes);
  GET DIAGNOSTICS class_count = ROW_COUNT;
  IF home_owner IS NOT NULL THEN
    INSERT INTO education.classes (teacher_id, name) VALUES (home_owner, 'Estudio en casa');
  END IF;

  UPDATE public.profiles SET active_learner_id = NULL WHERE id = p_adult;
  UPDATE public.devices SET learner_id = NULL WHERE learner_id IN (
    SELECT id FROM public.learners WHERE owner_user_id = p_adult
  );
  DELETE FROM public.device_events WHERE device_id IN (
    SELECT id FROM public.devices WHERE owner_user_id = p_adult
  );
  DELETE FROM public.device_pairing_requests WHERE owner_user_id = p_adult;
  DELETE FROM public.notebooks WHERE owner_user_id = p_adult;
  DELETE FROM public.learners WHERE owner_user_id = p_adult;
  GET DIAGNOSTICS legacy_count = ROW_COUNT;
  DELETE FROM public.ai_usage WHERE user_id = p_adult;
  INSERT INTO education.privacy_resets (id, adult_id, home_learners, legacy_learners)
  VALUES (p_request, p_adult, learner_count, legacy_count);
  RETURN jsonb_build_object(
    'homeLearners', learner_count, 'legacyLearners', legacy_count,
    'pendingFiles', (SELECT count(*) FROM education.privacy_file_removals WHERE adult_id = p_adult)
  );
END;
$$;

CREATE FUNCTION education.export_learning_data(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  WITH owner AS (
    SELECT id, display_name, account_type, age_band, created_at FROM public.profiles WHERE id = p_adult
  ), legacy AS (
    SELECT l.* FROM public.learners l JOIN owner o ON o.id = l.owner_user_id
  ), notebooks AS (
    SELECT n.id, n.learner_id, n.title, n.description, n.created_at FROM public.notebooks n
    JOIN owner o ON o.id = n.owner_user_id
  ), home AS (
    SELECT h.teacher_id FROM education.home_accounts h JOIN owner o ON o.id = h.family_id
  ), home_classes AS (
    SELECT c.id, c.name, c.created_at FROM education.classes c JOIN home h ON h.teacher_id = c.teacher_id
  ), home_learners AS (
    SELECT l.id, l.class_id, l.name, l.companion, l.web_preferences, l.created_at
    FROM education.learners l JOIN home_classes c ON c.id = l.class_id
  ), home_sessions AS (
    SELECT s.id, s.learner_id, s.version_id, s.phase, s.created_at, s.completed_at, s.retention_completed_at
    FROM education.sessions s JOIN home_learners l ON l.id = s.learner_id
  ), home_docs AS (
    SELECT d.id, d.class_id, d.name, d.mime, d.created_at FROM education.documents d
    JOIN home_classes c ON c.id = d.class_id
  )
  SELECT CASE WHEN EXISTS (SELECT FROM owner) THEN jsonb_build_object(
    'exportedAt', statement_timestamp(),
    'account', (SELECT to_jsonb(o) FROM owner o),
    'profiles', COALESCE((SELECT jsonb_agg(to_jsonb(l) - 'owner_user_id') FROM legacy l), '[]'::jsonb),
    'lessonProgress', COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM public.lesson_progress p JOIN legacy l ON l.id = p.learner_id), '[]'::jsonb),
    'lessonAttempts', COALESCE((SELECT jsonb_agg(to_jsonb(a) - ARRAY['submitted_answer','feedback']) FROM public.activity_attempts a JOIN legacy l ON l.id = a.learner_id), '[]'::jsonb),
    'achievements', COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM public.learner_achievements a JOIN legacy l ON l.id = a.learner_id), '[]'::jsonb),
    'notebooks', COALESCE((SELECT jsonb_agg(n) FROM notebooks n), '[]'::jsonb),
    'documents', COALESCE((SELECT jsonb_agg(jsonb_build_object('id', d.id, 'notebookId', d.notebook_id, 'name', d.file_name, 'mime', d.mime_type, 'bytes', d.file_size, 'uploadedAt', d.uploaded_at)) FROM public.notebook_documents d JOIN notebooks n ON n.id = d.notebook_id), '[]'::jsonb),
    'homeClasses', COALESCE((SELECT jsonb_agg(c) FROM home_classes c), '[]'::jsonb),
    'homeLearners', COALESCE((SELECT jsonb_agg(l) FROM home_learners l), '[]'::jsonb),
    'homeSessions', COALESCE((SELECT jsonb_agg(s) FROM home_sessions s), '[]'::jsonb),
    'homeDocuments', COALESCE((SELECT jsonb_agg(d) FROM home_docs d), '[]'::jsonb),
    'studyActivity', COALESCE((SELECT jsonb_agg(jsonb_build_object('learnerId', t.learner_id, 'sessionId', t.session_id, 'activityId', t.activity_id, 'kind', t.kind, 'at', t.occurred_at, 'visibleSeconds', t.visible_seconds, 'activeSeconds', t.active_seconds)) FROM education.telemetry t JOIN home_learners l ON l.id = t.learner_id), '[]'::jsonb),
    'progress', education.progress_snapshot(p_adult)
  ) END;
$$;

CREATE FUNCTION education.remove_legacy_study(p_adult uuid, p_notebook uuid, p_document uuid DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  target uuid := COALESCE(p_document, p_notebook);
  target_scope text := CASE WHEN p_document IS NULL THEN 'notebook' ELSE 'document' END;
BEGIN
  PERFORM id FROM public.profiles WHERE id = p_adult FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF EXISTS (SELECT FROM education.privacy_study_deletions
    WHERE adult_id = p_adult AND target_id = target AND scope = target_scope)
  THEN RETURN true; END IF;
  PERFORM id FROM public.notebooks WHERE id = p_notebook AND owner_user_id = p_adult FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF p_document IS NOT NULL THEN
    PERFORM id FROM public.notebook_documents WHERE id = p_document AND notebook_id = p_notebook FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
  END IF;

  INSERT INTO education.privacy_file_removals (adult_id, storage_path)
  SELECT p_adult, storage_path FROM public.notebook_documents
  WHERE notebook_id = p_notebook AND (p_document IS NULL OR id = p_document)
    AND split_part(storage_path, '/', 1) = p_adult::text
  ON CONFLICT DO NOTHING;
  IF p_document IS NULL THEN
    INSERT INTO education.privacy_file_removals (adult_id, storage_path)
    SELECT p_adult, name FROM storage.objects
    WHERE bucket_id = 'learner-documents' AND split_part(name, '/', 1) = p_adult::text
      AND split_part(name, '/', 2) = p_notebook::text
    ON CONFLICT DO NOTHING;
    DELETE FROM public.notebooks WHERE id = p_notebook AND owner_user_id = p_adult;
  ELSE
    DELETE FROM public.ai_messages WHERE notebook_id = p_notebook;
    DELETE FROM public.notebook_documents WHERE id = p_document AND notebook_id = p_notebook;
  END IF;
  INSERT INTO education.privacy_study_deletions (adult_id, target_id, scope)
  VALUES (p_adult, target, target_scope);
  RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION education.keep_inference_cancelled(),
  education.learning_file_cleanup(uuid, uuid[]), education.reset_learning_data(uuid, text, uuid),
  education.export_learning_data(uuid), education.remove_legacy_study(uuid, uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.learning_file_cleanup(uuid, uuid[]),
  education.reset_learning_data(uuid, text, uuid), education.export_learning_data(uuid),
  education.remove_legacy_study(uuid, uuid, uuid) TO peluqo_backend;

SELECT cron.schedule('peluqo-privacy-request-retention', '51 3 * * *', $job$
  DELETE FROM education.privacy_resets WHERE created_at < now() - interval '30 days';
  DELETE FROM education.privacy_study_deletions WHERE created_at < now() - interval '30 days';
$job$);
