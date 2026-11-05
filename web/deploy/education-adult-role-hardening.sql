-- Incremental role hardening. Reviewed guards replace profile-derived authority.
-- No account role or user data is changed. Admin roles continue to use public.has_role.
BEGIN;
CREATE OR REPLACE FUNCTION education.trusted_teacher_principal(p_teacher uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT education.adult_role(p_teacher)='teacher' OR EXISTS(
 SELECT FROM education.home_accounts h WHERE h.teacher_id=p_teacher AND education.adult_role(h.family_id)='family'); $$;


CREATE OR REPLACE FUNCTION education.issue_family_code(p_teacher uuid, p_learner uuid, p_hash text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  IF NOT coalesce(education.trusted_teacher_principal(p_teacher),false) THEN RETURN false; END IF;
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

CREATE OR REPLACE FUNCTION education.revoke_family_links(p_teacher uuid, p_learner uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  IF NOT coalesce(education.trusted_teacher_principal(p_teacher),false) THEN RETURN false; END IF;
  PERFORM l.id FROM education.learners l JOIN education.classes c ON c.id = l.class_id
  WHERE l.id = p_learner AND c.teacher_id = p_teacher FOR UPDATE OF l;
  IF NOT FOUND THEN RETURN false; END IF;
  UPDATE education.family_codes SET expires_at = now()
  WHERE learner_id = p_learner AND expires_at > now();
  DELETE FROM education.family_links WHERE learner_id = p_learner;
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION education.redeem_family_code(p_guardian uuid, p_hash text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  target uuid;
BEGIN
  IF education.adult_role(p_guardian) IS DISTINCT FROM 'family' THEN RETURN false; END IF;
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

CREATE OR REPLACE FUNCTION education.progress_snapshot(p_adult uuid, p_class uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  WITH viewer AS (
    SELECT education.adult_role(p_adult) AS role
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

CREATE OR REPLACE FUNCTION education.analytics_snapshot(
  p_adult uuid, p_admin boolean, p_class uuid, p_learner uuid, p_version uuid,
  p_activity text, p_subject text, p_from date, p_to date, p_zone text
) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  WITH viewer AS (
    SELECT CASE WHEN p_admin AND public.has_role(p_adult,'admin'::public.app_role) THEN 'admin' WHEN NOT p_admin THEN education.adult_role(p_adult) END AS role
  ), learners AS (
    SELECT l.id, l.class_id FROM education.learners l
    JOIN education.classes c ON c.id = l.class_id CROSS JOIN viewer
    WHERE p_to >= p_from AND p_to - p_from <= 89
      AND (
        viewer.role = 'admin'
        OR ((p_learner IS NULL OR p_learner = l.id) AND (p_class IS NULL OR p_class = l.class_id)
          AND (
            (viewer.role = 'teacher' AND c.teacher_id = p_adult)
            OR (viewer.role = 'family' AND EXISTS (
              SELECT FROM education.family_links f WHERE f.learner_id = l.id AND f.guardian_id = p_adult
            ))
          ))
      )
  ), versions AS (
    SELECT v.id, coalesce(v.mission->>'subject', 'sin_clasificar') AS subject, v.mission
    FROM education.versions v
    WHERE v.class_id IN (SELECT class_id FROM learners)
      AND (p_admin OR p_version IS NULL OR v.id = p_version)
  ), catalog AS (
    SELECT v.id AS version_id, v.subject, a->>'id' AS id, a->>'title' AS title,
      a->>'type' AS game, a->>'difficulty' AS difficulty
    FROM versions v CROSS JOIN (VALUES ('practice'),('diagnostic'),('final'),('retention')) phases(phase)
    CROSS JOIN LATERAL jsonb_array_elements(v.mission->phases.phase) a
  ), sessions AS (
    SELECT s.id, s.version_id, s.phase, s.completed_at, s.retention_completed_at
    FROM education.sessions s JOIN learners l ON l.id = s.learner_id JOIN versions v ON v.id = s.version_id
  ), span AS (
    SELECT p_from::timestamp AT TIME ZONE p_zone AS lo,
      (p_to + 1)::timestamp AT TIME ZONE p_zone AS hi
  ), evidence AS (
    SELECT t.occurred_at AS at, s.version_id, t.activity_id, t.kind,
      t.visible_seconds::int AS visible, t.active_seconds::int AS active,
      NULL::boolean AS correct, false AS completed
    FROM education.telemetry t JOIN learners l ON l.id = t.learner_id
    LEFT JOIN sessions s ON s.id = t.session_id CROSS JOIN span
    WHERE t.occurred_at >= greatest(lo, now() - interval '90 days') AND t.occurred_at < hi
      AND (t.session_id IS NULL OR s.id IS NOT NULL)
      AND (t.kind <> 'game_exit' OR NOT EXISTS (
        SELECT FROM education.attempts a WHERE a.session_id = t.session_id AND a.activity_id = t.activity_id
          AND (a.correct OR a.phase <> 'practice') AND a.created_at <= t.occurred_at
      ))
    UNION ALL
    SELECT a.created_at, s.version_id, a.activity_id, 'answer', 0, 0,
      CASE WHEN a.phase = 'practice' OR (a.phase = 'diagnostic' AND s.phase <> 'diagnostic')
        OR (a.phase = 'final' AND s.completed_at IS NOT NULL)
        OR (a.phase = 'retention' AND s.retention_completed_at IS NOT NULL) THEN a.correct END,
      a.phase <> 'practice' OR a.correct
    FROM education.attempts a JOIN sessions s ON s.id = a.session_id CROSS JOIN span
    WHERE a.created_at >= lo AND a.created_at < hi
    UNION ALL
    SELECT h.created_at, s.version_id, h.activity_id, 'hint', 0, 0, NULL, false
    FROM education.hints h JOIN sessions s ON s.id = h.session_id CROSS JOIN span
    WHERE h.created_at >= lo AND h.created_at < hi AND h.kind <> 'tutor'
    UNION ALL
    SELECT t.created_at, s.version_id, t.activity_id, 'tutor', 0, 0, NULL, false
    FROM education.turns t JOIN sessions s ON s.id = t.session_id CROSS JOIN span
    WHERE t.created_at >= lo AND t.created_at < hi
    UNION ALL
    SELECT t.created_at, NULL, NULL, 'tutor', 0, 0, NULL, false
    FROM education.curiosity_turns t JOIN learners l ON l.id = t.learner_id CROSS JOIN span
    WHERE t.created_at >= lo AND t.created_at < hi
  ), filtered AS (
    SELECT e.at, e.kind, e.visible, e.active, e.correct, e.completed,
      CASE WHEN NOT p_admin THEN e.version_id END AS version_id,
      CASE WHEN NOT p_admin THEN e.activity_id END AS activity_id,
      coalesce(v.subject, 'sin_clasificar') AS subject, c.game, c.difficulty,
      CASE WHEN NOT p_admin THEN c.title END AS title
    FROM evidence e LEFT JOIN versions v ON v.id = e.version_id
    LEFT JOIN catalog c ON c.version_id = e.version_id AND c.id = e.activity_id
    WHERE p_admin OR (
      (p_subject IS NULL OR p_subject = coalesce(v.subject, 'sin_clasificar'))
      AND (p_activity IS NULL OR p_activity = e.activity_id)
      AND (p_version IS NULL OR p_version = e.version_id)
    )
  ), metrics AS (
    SELECT (at AT TIME ZONE p_zone)::date AS day, extract(hour FROM at AT TIME ZONE p_zone)::int AS hour,
      subject, version_id, activity_id, game, difficulty, title,
      sum(visible)::int AS visible_seconds, sum(active)::int AS active_seconds,
      count(*) FILTER (WHERE kind = 'game_start')::int AS started,
      count(*) FILTER (WHERE completed)::int AS completed,
      count(*) FILTER (WHERE kind = 'answer')::int AS attempts,
      count(correct)::int AS graded, count(*) FILTER (WHERE correct)::int AS correct,
      count(*) FILTER (WHERE kind = 'game_exit')::int AS exits,
      count(*) FILTER (WHERE kind = 'hint')::int AS hints,
      count(*) FILTER (WHERE kind = 'tutor')::int AS tutor,
      count(*) FILTER (WHERE kind = 'access_open')::int AS logins,
      count(*) FILTER (WHERE kind = 'access_close')::int AS logouts,
      count(*) FILTER (WHERE kind = 'game_variant')::int AS variants,
      count(*) FILTER (WHERE kind = 'area_enter')::int AS visits,
      count(*) FILTER (WHERE kind = 'client_error')::int AS errors
    FROM filtered
    GROUP BY 1,2,3,4,5,6,7,8
  )
  SELECT jsonb_build_object(
    'role', (SELECT role FROM viewer),
    'rows', coalesce((SELECT jsonb_agg(to_jsonb(m) - CASE WHEN p_admin THEN
      ARRAY['version_id','activity_id','title'] ELSE ARRAY[]::text[] END)
      FROM (SELECT * FROM metrics) m), '[]'::jsonb),
    'catalog', CASE WHEN p_admin THEN '[]'::jsonb
      ELSE coalesce((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.title, c.id) FROM catalog c), '[]'::jsonb) END
  );
$$;

CREATE OR REPLACE FUNCTION education.can_set_study_priority(p_adult uuid,p_learner uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=''
AS $$ SELECT education.school_can_view(p_adult,p_learner); $$;

CREATE OR REPLACE FUNCTION education.manage_student_access(
  p_adult uuid, p_learner uuid, p_action text, p_hash text DEFAULT NULL,
  p_expires_at timestamptz DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  access_hash text;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('status', 'issue', 'issue-legacy', 'pause', 'enable', 'revoke') THEN
    RETURN NULL;
  END IF;

  -- Family-link changes lock the same learner row before editing the relationship.
  PERFORM l.id FROM education.learners l WHERE l.id = p_learner FOR UPDATE;
  IF NOT FOUND OR NOT EXISTS (
    SELECT FROM education.learners l JOIN education.classes c ON c.id = l.class_id
    WHERE l.id = p_learner AND (
      (c.teacher_id = p_adult AND coalesce(education.trusted_teacher_principal(p_adult),false))
      OR (p_action <> 'issue-legacy' AND education.adult_role(p_adult)='family' AND EXISTS (
        SELECT FROM education.family_links link
        WHERE link.learner_id=l.id AND link.guardian_id=p_adult
      ))
    )
  ) THEN RETURN NULL; END IF;

  IF p_action = 'status' THEN RETURN education.student_access_state(p_learner); END IF;

  IF p_action IN ('issue', 'issue-legacy') THEN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR (p_expires_at IS NOT NULL AND (NOT isfinite(p_expires_at) OR p_expires_at <= clock_timestamp()))
       OR (p_action = 'issue-legacy' AND p_expires_at IS NULL) THEN RETURN NULL; END IF;
    UPDATE education.access_codes SET state = 'revoked'
    WHERE learner_id = p_learner AND state <> 'revoked';
    INSERT INTO education.access_codes (hash, learner_id, expires_at, reusable, created_at, issued_by)
    VALUES (p_hash, p_learner, p_expires_at, p_action = 'issue', clock_timestamp(), p_adult);
  ELSE
    SELECT c.hash INTO access_hash FROM education.access_codes c WHERE c.learner_id = p_learner
    ORDER BY c.created_at DESC, c.hash LIMIT 1;

    IF p_action = 'enable' THEN
      UPDATE education.access_codes SET state = 'active'
      WHERE hash = access_hash AND state = 'paused' AND (reusable OR consumed_at IS NULL)
        AND (expires_at IS NULL OR expires_at > clock_timestamp());
      RETURN education.student_access_state(p_learner);
    END IF;

    IF p_action = 'pause' THEN
      UPDATE education.access_codes SET state = 'paused' WHERE hash = access_hash AND state = 'active';
    ELSE
      UPDATE education.access_codes SET state = 'revoked' WHERE hash = access_hash AND state <> 'revoked';
    END IF;
  END IF;

  UPDATE education.logins SET revoked = true WHERE learner_id = p_learner AND NOT revoked;
  UPDATE education.devices SET session_id = NULL, ack = 0
  WHERE learner_id = p_learner AND session_id IS NOT NULL;
  RETURN education.student_access_state(p_learner);
END;
$$;

CREATE OR REPLACE FUNCTION education.enable_home_studio(p_adult uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  owner_id uuid;
BEGIN
  IF education.adult_role(p_adult) IS DISTINCT FROM 'family' THEN RETURN false; END IF;
  PERFORM id FROM public.profiles WHERE id=p_adult FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF EXISTS (SELECT FROM education.home_accounts WHERE family_id = p_adult) THEN RETURN true; END IF;

  INSERT INTO education.teachers (id) VALUES (gen_random_uuid()) RETURNING id INTO owner_id;
  INSERT INTO education.home_accounts (family_id, teacher_id) VALUES (p_adult, owner_id);
  INSERT INTO education.classes (teacher_id, name) VALUES (owner_id, 'Estudio en casa');
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION education.resolve_home_studio(p_adult uuid)
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT h.teacher_id FROM education.home_accounts h
 WHERE h.family_id=p_adult AND education.adult_role(p_adult)='family'; $$;

-- A client-editable profile can no longer create a school teacher principal.
CREATE OR REPLACE FUNCTION education.register_teacher_profile()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ BEGIN
 IF EXISTS(SELECT FROM auth.users WHERE id=NEW.id AND raw_app_meta_data->>'mochi_adult_role'='teacher') THEN
  INSERT INTO education.teachers(id) VALUES(NEW.id) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END; $$;

-- GoTrue may set app metadata in an update after the profile insert.
CREATE OR REPLACE FUNCTION education.register_teacher_from_auth_role()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ BEGIN
 IF NEW.raw_app_meta_data->>'mochi_adult_role'='teacher' THEN
  INSERT INTO education.teachers(id) VALUES(NEW.id) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS register_mochi_trusted_teacher ON auth.users;
CREATE TRIGGER register_mochi_trusted_teacher AFTER INSERT OR UPDATE OF raw_app_meta_data ON auth.users
FOR EACH ROW WHEN (NEW.raw_app_meta_data->>'mochi_adult_role'='teacher')
EXECUTE FUNCTION education.register_teacher_from_auth_role();

REVOKE ALL ON FUNCTION education.trusted_teacher_principal(uuid),education.register_teacher_profile(),
 education.register_teacher_from_auth_role(),education.can_set_study_priority(uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION education.trusted_teacher_principal(uuid) TO peluqo_backend;
COMMIT;
