-- Minimal app telemetry. Answers and help already have an authoritative source.
CREATE TABLE education.telemetry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  session_id uuid REFERENCES education.sessions(id) ON DELETE CASCADE,
  activity_id text,
  phase text,
  kind text NOT NULL CHECK (kind IN ('access_open','access_close','area_enter','game_start','game_exit','game_variant','sample','client_error')),
  surface text,
  format text CHECK (format IN ('board','cards')),
  visible_seconds smallint NOT NULL DEFAULT 0 CHECK (visible_seconds BETWEEN 0 AND 40),
  active_seconds smallint NOT NULL DEFAULT 0 CHECK (active_seconds BETWEEN 0 AND visible_seconds),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX telemetry_learner_time ON education.telemetry (learner_id, occurred_at);
CREATE INDEX telemetry_time ON education.telemetry (occurred_at);
CREATE INDEX telemetry_session ON education.telemetry (session_id) WHERE session_id IS NOT NULL;

CREATE TABLE education.telemetry_presence (
  learner_id uuid PRIMARY KEY REFERENCES education.learners(id) ON DELETE CASCADE,
  visit_id uuid NOT NULL,
  surface text NOT NULL,
  session_id uuid REFERENCES education.sessions(id) ON DELETE CASCADE,
  activity_id text,
  phase text,
  format text,
  active boolean NOT NULL,
  seen_at timestamptz NOT NULL
);
CREATE INDEX telemetry_presence_session ON education.telemetry_presence (session_id) WHERE session_id IS NOT NULL;
ALTER TABLE education.telemetry ENABLE ROW LEVEL SECURITY;
ALTER TABLE education.telemetry_presence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.telemetry, education.telemetry_presence FROM PUBLIC, anon, authenticated, peluqo_backend;

CREATE FUNCTION education.track_access_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO education.telemetry (learner_id, kind) VALUES (NEW.learner_id, 'access_open');
  ELSIF NEW.revoked AND NOT OLD.revoked THEN
    INSERT INTO education.telemetry (learner_id, kind) VALUES (NEW.learner_id, 'access_close');
    DELETE FROM education.telemetry_presence WHERE learner_id = NEW.learner_id;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER track_student_access AFTER INSERT OR UPDATE OF revoked ON education.logins
FOR EACH ROW EXECUTE FUNCTION education.track_access_change();

CREATE FUNCTION education.record_telemetry(
  p_login text, p_visit uuid, p_event text, p_surface text, p_session uuid, p_activity text,
  p_active boolean, p_format text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  pupil uuid;
  phase_now text;
  now_at timestamptz := clock_timestamp();
  prior education.telemetry_presence%ROWTYPE;
  has_prior boolean;
  changed_game boolean;
  seconds int;
BEGIN
  IF p_event NOT IN ('enter','sample','leave','failure')
    OR p_surface NOT IN ('aventura','mundos','preguntas','peluqo')
    OR (p_format IS NOT NULL AND p_format NOT IN ('board','cards'))
  THEN RETURN false; END IF;
  SELECT g.learner_id INTO pupil FROM education.logins g
  WHERE g.hash = p_login AND NOT g.revoked AND g.expires_at > now_at;
  IF pupil IS NULL THEN RETURN false; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(pupil::text, 1842));
  PERFORM 1 FROM education.logins WHERE hash = p_login AND NOT revoked AND expires_at > now_at FOR SHARE;
  IF NOT FOUND THEN RETURN false; END IF;
  SELECT * INTO prior FROM education.telemetry_presence WHERE learner_id = pupil;
  has_prior := FOUND;

  IF p_event = 'failure' THEN
    INSERT INTO education.telemetry (learner_id, kind, surface)
    SELECT pupil, 'client_error', p_surface WHERE NOT EXISTS (
      SELECT FROM education.telemetry WHERE learner_id = pupil AND kind = 'client_error'
        AND occurred_at >= now_at - interval '1 minute'
    );
    RETURN true;
  END IF;
  IF p_event = 'leave' AND (NOT has_prior OR prior.visit_id <> p_visit) THEN RETURN true; END IF;
  IF has_prior AND p_event = 'sample' AND prior.seen_at >= now_at - interval '8 seconds'
  THEN RETURN true; END IF;

  IF p_session IS NOT NULL AND p_event <> 'leave' THEN
    SELECT s.phase INTO phase_now FROM education.sessions s
    JOIN education.versions v ON v.id = s.version_id
    WHERE s.id = p_session AND s.learner_id = pupil AND s.login_hash = p_login
      AND (p_activity IS NULL OR EXISTS (
        SELECT FROM jsonb_array_elements(coalesce(v.mission->s.phase, '[]'::jsonb)) a
        WHERE a->>'id' = p_activity
      ));
    IF phase_now IS NULL THEN RETURN false; END IF;
  ELSIF p_session IS NULL AND p_activity IS NOT NULL THEN
    RETURN false;
  END IF;

  changed_game := NOT has_prior OR p_event = 'leave'
    OR (prior.session_id, prior.activity_id, prior.phase)
      IS DISTINCT FROM (p_session, p_activity, phase_now);
  IF has_prior AND prior.visit_id = p_visit THEN
    seconds := floor(extract(epoch FROM now_at - prior.seen_at));
    IF seconds BETWEEN 1 AND 40 THEN
      INSERT INTO education.telemetry (
        learner_id, session_id, activity_id, phase, kind, surface, format, visible_seconds, active_seconds
      ) VALUES (
        pupil, prior.session_id, prior.activity_id, prior.phase, 'sample', prior.surface, prior.format,
        seconds, CASE WHEN prior.active AND p_active THEN seconds ELSE 0 END
      );
    END IF;
    IF changed_game AND prior.activity_id IS NOT NULL THEN
      INSERT INTO education.telemetry (learner_id, session_id, activity_id, phase, kind, surface, format)
      VALUES (pupil, prior.session_id, prior.activity_id, prior.phase, 'game_exit', prior.surface, prior.format);
    END IF;
  END IF;

  IF p_event = 'leave' THEN
    DELETE FROM education.telemetry_presence WHERE learner_id = pupil;
    RETURN true;
  END IF;
  IF NOT has_prior OR prior.surface <> p_surface THEN
    INSERT INTO education.telemetry (learner_id, session_id, phase, kind, surface)
    VALUES (pupil, p_session, phase_now, 'area_enter', p_surface);
  END IF;
  IF p_activity IS NOT NULL AND (changed_game OR prior.format IS DISTINCT FROM p_format) THEN
    INSERT INTO education.telemetry (learner_id, session_id, activity_id, phase, kind, surface, format)
    VALUES (pupil, p_session, p_activity, phase_now,
      CASE WHEN changed_game THEN 'game_start' ELSE 'game_variant' END, p_surface, p_format);
  END IF;
  INSERT INTO education.telemetry_presence (learner_id, visit_id, surface, session_id, activity_id, phase, format, active, seen_at)
  VALUES (pupil, p_visit, p_surface, p_session, p_activity, phase_now, p_format, p_active, now_at)
  ON CONFLICT (learner_id) DO UPDATE SET
    visit_id = excluded.visit_id, surface = excluded.surface, session_id = excluded.session_id,
    activity_id = excluded.activity_id, phase = excluded.phase, format = excluded.format,
    active = excluded.active, seen_at = excluded.seen_at;
  RETURN true;
END;
$$;

-- Role checks run here as well as at the HTTP boundary. Admin gets anonymous totals.
CREATE FUNCTION education.analytics_snapshot(
  p_adult uuid, p_admin boolean, p_class uuid, p_learner uuid, p_version uuid,
  p_activity text, p_subject text, p_from date, p_to date, p_zone text
) RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  WITH viewer AS (
    SELECT CASE
      WHEN p_admin AND public.has_role(p_adult, 'admin'::public.app_role) THEN 'admin'
      WHEN NOT p_admin AND EXISTS (SELECT FROM education.teachers WHERE id = p_adult) THEN 'teacher'
      WHEN NOT p_admin AND EXISTS (
        SELECT FROM public.profiles WHERE id = p_adult AND account_type = 'family' AND age_band = '18+'
      ) THEN 'family'
    END AS role
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

REVOKE EXECUTE ON FUNCTION education.track_access_change(),
  education.record_telemetry(text, uuid, text, text, uuid, text, boolean, text),
  education.analytics_snapshot(uuid, boolean, uuid, uuid, uuid, text, text, date, date, text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.record_telemetry(text, uuid, text, text, uuid, text, boolean, text),
  education.analytics_snapshot(uuid, boolean, uuid, uuid, uuid, text, text, date, date, text)
TO peluqo_backend;

CREATE EXTENSION IF NOT EXISTS pg_cron;
SELECT cron.schedule('peluqo-telemetry-retention', '43 3 * * *', $job$
  DELETE FROM education.telemetry WHERE occurred_at < now() - interval '90 days';
  DELETE FROM education.telemetry_presence WHERE seen_at < now() - interval '1 day';
$job$);
