-- Additive extension: adult-assigned work runs on the paired device without a web learner session.
BEGIN;
CREATE TABLE IF NOT EXISTS education.device_lessons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lesson_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES education.teachers(id),
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  title text NOT NULL CHECK (char_length(title) BETWEEN 3 AND 80),
  subject text NOT NULL DEFAULT 'matematicas' CHECK(subject = 'matematicas'),
  goal text NOT NULL CHECK (char_length(goal) BETWEEN 8 AND 300),
  instructions text NOT NULL CHECK (char_length(instructions) BETWEEN 8 AND 200),
  due_at date NOT NULL,
  factors jsonb NOT NULL CHECK(jsonb_typeof(factors)='array' AND jsonb_array_length(factors) BETWEEN 1 AND 5),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS device_lessons_learner ON education.device_lessons(learner_id,created_at);
CREATE TABLE IF NOT EXISTS education.device_lesson_results (
  result_id uuid PRIMARY KEY,
  assignment_id uuid NOT NULL UNIQUE REFERENCES education.device_lessons(id) ON DELETE CASCADE,
  device_id uuid NOT NULL REFERENCES education.devices(id),
  payload jsonb NOT NULL,
  request_hash text NOT NULL,
  correct_count smallint NOT NULL CHECK(correct_count BETWEEN 1 AND 5),
  received_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS device_lesson_results_device ON education.device_lesson_results(device_id);
ALTER TABLE education.device_lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE education.device_lesson_results ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.device_lessons,education.device_lesson_results FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON education.device_lessons,education.device_lesson_results TO peluqo_backend;
DROP POLICY IF EXISTS device_lesson_access ON education.device_lessons;
CREATE POLICY device_lesson_access ON education.device_lessons TO peluqo_backend
  USING (teacher_id::text=education.request_value('teacher') OR education.request_value('service')='true')
  WITH CHECK (teacher_id::text=education.request_value('teacher') OR education.request_value('service')='true');
DROP POLICY IF EXISTS device_lesson_result_access ON education.device_lesson_results;
CREATE POLICY device_lesson_result_access ON education.device_lesson_results TO peluqo_backend
  USING (assignment_id IN (SELECT id FROM education.device_lessons))
  WITH CHECK (education.request_value('service')='true' AND assignment_id IN (SELECT id FROM education.device_lessons));

-- This read-only bridge exposes only school data owned by the verified teacher or linked guardian.
-- Private schema, fixed search_path, no PUBLIC execution. The HTTP layer validates p_adult with Auth.
CREATE OR REPLACE FUNCTION education.device_lesson_snapshot(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
  WITH viewer AS (
    SELECT CASE
      WHEN EXISTS(SELECT FROM education.teachers WHERE id=p_adult) THEN 'teacher'
      WHEN EXISTS(SELECT FROM public.profiles WHERE id=p_adult AND account_type='family' AND age_band='18+') THEN 'family'
    END AS role
  ), visible AS (
    SELECT d.*,l.name AS learner_name,l.class_id FROM education.device_lessons d
    JOIN education.learners l ON l.id=d.learner_id
    JOIN education.classes c ON c.id=l.class_id CROSS JOIN viewer v
    WHERE (v.role='teacher' AND d.teacher_id=p_adult AND c.teacher_id=p_adult)
      OR (v.role='family' AND EXISTS(SELECT FROM education.family_links f WHERE f.guardian_id=p_adult AND f.learner_id=l.id))
  )
  SELECT jsonb_build_object('role',v.role,'lessons',coalesce((
    SELECT jsonb_agg(jsonb_build_object(
      'id',d.id,'learnerId',d.learner_id,'learnerName',d.learner_name,'classId',d.class_id,
      'title',d.title,'goal',d.goal,'instructions',d.instructions,'dueAt',d.due_at,
      'createdAt',d.created_at,'exerciseCount',jsonb_array_length(d.factors),
      'result',CASE WHEN r.result_id IS NULL THEN NULL ELSE jsonb_build_object(
        'resultId',r.result_id,'attempts',r.payload->'attempts','hints',r.payload->'hints',
        'elapsedSeconds',r.payload->'elapsedSeconds','answers',r.payload->'answers',
        'correctCount',r.correct_count,'receivedAt',r.received_at) END
    ) ORDER BY d.created_at DESC)
    FROM visible d LEFT JOIN education.device_lesson_results r ON r.assignment_id=d.id
  ),'[]'::jsonb)) FROM viewer v;
$$;
REVOKE ALL ON FUNCTION education.device_lesson_snapshot(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION education.device_lesson_snapshot(uuid) TO peluqo_backend;
COMMIT;
