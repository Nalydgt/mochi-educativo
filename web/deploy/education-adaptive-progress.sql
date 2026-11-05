ALTER TABLE education.attempts
  ADD COLUMN study_format text NOT NULL DEFAULT 'board' CHECK (study_format IN ('board', 'cards'));

CREATE TABLE education.family_links (
  guardian_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (guardian_id, learner_id)
);

CREATE TABLE education.family_codes (
  hash text PRIMARY KEY CHECK (hash ~ '^[0-9a-f]{64}$'),
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  redeemed_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL
);

CREATE INDEX family_links_learner ON education.family_links (learner_id);
CREATE INDEX family_codes_learner ON education.family_codes (learner_id);
ALTER TABLE education.family_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE education.family_codes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.family_links, education.family_codes FROM PUBLIC, anon, authenticated;
GRANT SELECT ON education.family_links TO peluqo_backend;

CREATE POLICY teacher_family_link_count ON education.family_links FOR SELECT TO peluqo_backend
USING (EXISTS (
  SELECT FROM education.learners l JOIN education.classes c ON c.id = l.class_id
  WHERE l.id = learner_id AND c.teacher_id::text = education.request_value('teacher')
));

-- Serialize changes to a pupil's family access through the pupil row.
CREATE FUNCTION education.issue_family_code(p_teacher uuid, p_learner uuid, p_hash text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  PERFORM l.id FROM education.learners l JOIN education.classes c ON c.id = l.class_id
  WHERE l.id = p_learner AND c.teacher_id = p_teacher FOR UPDATE OF l;
  IF NOT FOUND THEN RETURN false; END IF;
  UPDATE education.family_codes SET expires_at = now()
  WHERE learner_id = p_learner AND consumed_at IS NULL AND expires_at > now();
  INSERT INTO education.family_codes (hash, learner_id, expires_at)
  VALUES (p_hash, p_learner, now() + interval '24 hours');
  RETURN true;
END;
$$;

CREATE FUNCTION education.revoke_family_links(p_teacher uuid, p_learner uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  PERFORM l.id FROM education.learners l JOIN education.classes c ON c.id = l.class_id
  WHERE l.id = p_learner AND c.teacher_id = p_teacher FOR UPDATE OF l;
  IF NOT FOUND THEN RETURN false; END IF;
  UPDATE education.family_codes SET expires_at = now()
  WHERE learner_id = p_learner AND expires_at > now();
  DELETE FROM education.family_links WHERE learner_id = p_learner;
  RETURN true;
END;
$$;

CREATE FUNCTION education.redeem_family_code(p_guardian uuid, p_hash text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  target uuid;
BEGIN
  IF NOT EXISTS (
    SELECT FROM public.profiles
    WHERE id = p_guardian AND account_type = 'family' AND age_band = '18+'
  ) THEN RETURN false; END IF;
  SELECT learner_id INTO target FROM education.family_codes WHERE hash = p_hash;
  IF target IS NULL THEN RETURN false; END IF;
  PERFORM id FROM education.learners WHERE id = target FOR UPDATE;
  UPDATE education.family_codes SET consumed_at = now(), redeemed_by = p_guardian
  WHERE hash = p_hash AND consumed_at IS NULL AND expires_at > now();
  IF NOT FOUND THEN
    RETURN EXISTS (
      SELECT FROM education.family_codes code
      JOIN education.family_links link ON link.learner_id = code.learner_id
      WHERE code.hash = p_hash AND code.redeemed_by = p_guardian
        AND link.guardian_id = p_guardian AND code.expires_at > now()
    );
  END IF;
  INSERT INTO education.family_links (guardian_id, learner_id)
  VALUES (p_guardian, target) ON CONFLICT DO NOTHING;
  RETURN true;
END;
$$;

-- The app passes the verified Auth ID. This projection only returns evidence and published titles.
CREATE FUNCTION education.progress_snapshot(p_adult uuid, p_class uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  WITH viewer AS (
    SELECT CASE
      WHEN EXISTS (SELECT FROM education.teachers WHERE id = p_adult) THEN 'teacher'
      WHEN EXISTS (
        SELECT FROM public.profiles WHERE id = p_adult AND account_type = 'family' AND age_band = '18+'
      ) THEN 'family'
    END AS role
  ), pupils AS (
    SELECT l.id, l.name, l.support, c.id AS class_id, c.name AS class_name
    FROM education.learners l JOIN education.classes c ON c.id = l.class_id
    CROSS JOIN viewer
    WHERE (p_class IS NULL OR c.id = p_class)
      AND (
        (viewer.role = 'teacher' AND c.teacher_id = p_adult)
        OR (viewer.role = 'family' AND EXISTS (
          SELECT FROM education.family_links link WHERE link.guardian_id = p_adult AND link.learner_id = l.id
        ))
      )
  ), worlds AS (
    SELECT v.id, v.class_id, v.mission->>'title' AS title, v.created_at AS published_at,
      jsonb_array_length(v.mission->'diagnostic') AS diagnostic_total,
      jsonb_array_length(v.mission->'practice') AS practice_total,
      jsonb_array_length(v.mission->'final') AS final_total,
      jsonb_array_length(v.mission->'retention') AS retention_total
    FROM education.versions v WHERE v.class_id IN (SELECT class_id FROM pupils)
  ), latest AS (
    SELECT DISTINCT ON (s.learner_id, s.version_id)
      s.id, s.learner_id, s.version_id, s.phase, s.created_at, s.completed_at, s.retention_completed_at
    FROM education.sessions s JOIN pupils l ON l.id = s.learner_id JOIN worlds v ON v.id = s.version_id AND v.class_id = l.class_id
    ORDER BY s.learner_id, s.version_id, s.opened_at DESC, s.id DESC
  ), sessions AS (
    SELECT s.*, (SELECT count(*)::int FROM education.hints h WHERE h.session_id = s.id) AS aids
    FROM latest s
  ), evidence AS (
    SELECT a.session_id, a.activity_id, a.competency, a.phase, a.hints, a.study_format, a.created_at,
      CASE WHEN a.phase = 'practice'
             OR (a.phase = 'diagnostic' AND s.phase <> 'diagnostic')
             OR (a.phase = 'final' AND s.completed_at IS NOT NULL)
             OR (a.phase = 'retention' AND s.retention_completed_at IS NOT NULL)
           THEN a.correct END AS correct
    FROM education.attempts a JOIN latest s ON s.id = a.session_id
  )
  SELECT jsonb_build_object(
    'role', (SELECT role FROM viewer),
    'pupils', COALESCE((SELECT jsonb_agg(p ORDER BY p.name, p.id) FROM pupils p), '[]'::jsonb),
    'worlds', COALESCE((SELECT jsonb_agg(w ORDER BY w.published_at DESC, w.id) FROM worlds w), '[]'::jsonb),
    'sessions', COALESCE((SELECT jsonb_agg(s) FROM sessions s), '[]'::jsonb),
    'evidence', COALESCE((SELECT jsonb_agg(e ORDER BY e.created_at) FROM evidence e), '[]'::jsonb)
  );
$$;

REVOKE EXECUTE ON FUNCTION education.issue_family_code(uuid, uuid, text),
  education.revoke_family_links(uuid, uuid), education.redeem_family_code(uuid, text),
  education.progress_snapshot(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.issue_family_code(uuid, uuid, text),
  education.revoke_family_links(uuid, uuid), education.redeem_family_code(uuid, text),
  education.progress_snapshot(uuid, uuid) TO peluqo_backend;
