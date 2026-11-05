-- Server-owned school records. No browser role can query these private tables.
BEGIN;

CREATE TABLE IF NOT EXISTS education.adult_accounts (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK(role IN ('teacher','family')),
  provenance text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE education.adult_accounts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.adult_accounts FROM PUBLIC,anon,authenticated,peluqo_backend;
INSERT INTO education.adult_accounts(user_id,role,provenance)
SELECT t.id,'teacher','existing_teacher_registry' FROM education.teachers t JOIN auth.users u ON u.id=t.id
ON CONFLICT DO NOTHING;
-- Existing family links came through a teacher-issued, single-use invitation.
-- Editable profile.account_type alone never grants an adult role.
INSERT INTO education.adult_accounts(user_id,role,provenance)
SELECT DISTINCT f.guardian_id,'family','existing_verified_family_link'
FROM education.family_links f JOIN public.profiles p ON p.id=f.guardian_id
JOIN auth.users u ON u.id=f.guardian_id WHERE p.account_type='family' AND p.age_band='18+'
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION education.adult_role(p_adult uuid)
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT coalesce((SELECT a.role FROM education.adult_accounts a WHERE a.user_id=p_adult),
   (SELECT CASE WHEN u.raw_app_meta_data->>'mochi_adult_role' IN ('teacher','family')
     THEN u.raw_app_meta_data->>'mochi_adult_role' END FROM auth.users u WHERE u.id=p_adult));
$$;
REVOKE ALL ON FUNCTION education.adult_role(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION education.adult_role(uuid) TO peluqo_backend;

CREATE TABLE IF NOT EXISTS education.school_learning_profiles (
  learner_id uuid PRIMARY KEY REFERENCES education.learners(id) ON DELETE CASCADE,
  age_band text NOT NULL DEFAULT '9–12' CHECK(age_band IN ('6–8','9–12','13–15','16–18')),
  grade_label text NOT NULL DEFAULT '' CHECK(char_length(grade_label)<=80),
  updated_by uuid NOT NULL REFERENCES education.teachers(id),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS education.school_device_settings (
  learner_id uuid PRIMARY KEY REFERENCES education.learners(id) ON DELETE CASCADE,
  daily_minutes smallint NOT NULL CHECK(daily_minutes BETWEEN 5 AND 120),
  start_time time NOT NULL, end_time time NOT NULL CHECK(end_time<>start_time),
  timezone text NOT NULL DEFAULT 'Europe/Madrid' CHECK(char_length(timezone)<=64),
  language text NOT NULL CHECK(language IN ('es','en','pt')),
  voice_enabled boolean NOT NULL DEFAULT true,
  captions_enabled boolean NOT NULL DEFAULT true,
  text_first boolean NOT NULL DEFAULT false,
  share_practice boolean NOT NULL DEFAULT true,
  revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
  updated_by uuid NOT NULL REFERENCES auth.users(id),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS education.school_lesson_reviews (
  assignment_id uuid PRIMARY KEY REFERENCES education.device_lessons(id) ON DELETE CASCADE,
  teacher_id uuid NOT NULL REFERENCES education.teachers(id),
  status text NOT NULL CHECK(status IN ('reviewed','needs_support')),
  observation text NOT NULL CHECK(char_length(observation) BETWEEN 1 AND 2000),
  reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  published_at timestamptz
);
CREATE TABLE IF NOT EXISTS education.school_grades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  teacher_id uuid NOT NULL REFERENCES education.teachers(id),
  assignment_id uuid REFERENCES education.device_lessons(id) ON DELETE SET NULL,
  subject text NOT NULL CHECK(char_length(subject) BETWEEN 2 AND 80),
  title text NOT NULL CHECK(char_length(title) BETWEEN 3 AND 120),
  value numeric(4,2) NOT NULL CHECK(value BETWEEN 0 AND 10),
  feedback text NOT NULL DEFAULT '' CHECK(char_length(feedback)<=2000),
  published_at timestamptz,
  revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS school_grades_learner ON education.school_grades(learner_id,created_at);
CREATE TABLE IF NOT EXISTS education.school_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES education.teachers(id),
  title text NOT NULL CHECK(char_length(title) BETWEEN 3 AND 160),
  body text NOT NULL CHECK(char_length(body) BETWEEN 1 AND 6000),
  allow_replies boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  withdrawn_at timestamptz
);
CREATE TABLE IF NOT EXISTS education.school_message_recipients (
  message_id uuid NOT NULL REFERENCES education.school_messages(id) ON DELETE CASCADE,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  PRIMARY KEY(message_id,learner_id)
);
CREATE INDEX IF NOT EXISTS school_message_recipients_learner ON education.school_message_recipients(learner_id);
CREATE TABLE IF NOT EXISTS education.school_message_replies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES education.school_messages(id) ON DELETE CASCADE,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  adult_id uuid NOT NULL REFERENCES auth.users(id),
  body text NOT NULL CHECK(char_length(body) BETWEEN 1 AND 3000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS school_message_replies_message ON education.school_message_replies(message_id,created_at);
CREATE TABLE IF NOT EXISTS education.school_message_reads (
  message_id uuid NOT NULL REFERENCES education.school_messages(id) ON DELETE CASCADE,
  adult_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  read_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(message_id,adult_id)
);
CREATE TABLE IF NOT EXISTS education.school_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES education.teachers(id),
  class_id uuid REFERENCES education.classes(id) ON DELETE CASCADE,
  title text NOT NULL CHECK(char_length(title) BETWEEN 3 AND 160),
  description text NOT NULL DEFAULT '' CHECK(char_length(description)<=3000),
  kind text NOT NULL CHECK(kind IN ('meeting','exam','outing','school')),
  starts_at timestamptz NOT NULL,
  ends_at timestamptz CHECK(ends_at>starts_at),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  cancelled_at timestamptz
);
CREATE INDEX IF NOT EXISTS school_events_teacher_time ON education.school_events(teacher_id,starts_at);
CREATE TABLE IF NOT EXISTS education.school_event_recipients (
  event_id uuid NOT NULL REFERENCES education.school_events(id) ON DELETE CASCADE,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  PRIMARY KEY(event_id,learner_id)
);
CREATE INDEX IF NOT EXISTS school_event_recipients_learner ON education.school_event_recipients(learner_id);
CREATE TABLE IF NOT EXISTS education.school_command_receipts (
  adult_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  request_id uuid NOT NULL,
  request_hash text NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(adult_id,request_id)
);
CREATE INDEX IF NOT EXISTS school_command_receipts_time ON education.school_command_receipts(created_at);
CREATE TABLE IF NOT EXISTS education.school_audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  adult_id uuid NOT NULL REFERENCES auth.users(id),
  action text NOT NULL,
  entity_id uuid,
  learner_id uuid REFERENCES education.learners(id) ON DELETE SET NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS school_audit_actor ON education.school_audit(adult_id,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS school_audit_proposal_request ON education.school_audit(adult_id,entity_id) WHERE action='suggest-assignment';
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['school_learning_profiles','school_device_settings','school_lesson_reviews',
 'school_grades','school_messages','school_message_recipients','school_message_replies','school_message_reads',
 'school_events','school_event_recipients','school_command_receipts','school_audit'] LOOP
  EXECUTE format('ALTER TABLE education.%I ENABLE ROW LEVEL SECURITY',name);
  EXECUTE format('REVOKE ALL ON education.%I FROM PUBLIC,anon,authenticated,peluqo_backend',name);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION education.school_can_view(p_adult uuid,p_learner uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT EXISTS(SELECT FROM education.learners l JOIN education.classes c ON c.id=l.class_id
 WHERE l.id=p_learner AND ((education.adult_role(p_adult)='teacher' AND c.teacher_id=p_adult)
 OR (education.adult_role(p_adult)='family' AND EXISTS(SELECT FROM education.family_links f
 WHERE f.learner_id=l.id AND f.guardian_id=p_adult))));
$$;
CREATE OR REPLACE FUNCTION education.school_owns(p_adult uuid,p_learner uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT education.adult_role(p_adult)='teacher' AND EXISTS(SELECT FROM education.learners l
 JOIN education.classes c ON c.id=l.class_id WHERE l.id=p_learner AND c.teacher_id=p_adult);
$$;
CREATE OR REPLACE FUNCTION education.school_targets(p_adult uuid,p_body jsonb)
RETURNS uuid[] LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=''
AS $$
DECLARE selected uuid[]; wanted uuid[]; class_target uuid := nullif(p_body->>'classId','')::uuid;
BEGIN
 IF education.adult_role(p_adult) IS DISTINCT FROM 'teacher' THEN RAISE insufficient_privilege; END IF;
 IF class_target IS NOT NULL AND NOT EXISTS(SELECT FROM education.classes WHERE id=class_target AND teacher_id=p_adult)
 THEN RAISE no_data_found; END IF;
 IF jsonb_typeof(p_body->'learnerIds')='array' THEN
  SELECT array_agg(DISTINCT value::uuid ORDER BY value::uuid) INTO wanted FROM jsonb_array_elements_text(p_body->'learnerIds');
  IF coalesce(cardinality(wanted),0)=0 OR cardinality(wanted)>200 THEN RAISE invalid_parameter_value; END IF;
  SELECT array_agg(l.id ORDER BY l.id) INTO selected FROM education.learners l JOIN education.classes c ON c.id=l.class_id
  WHERE l.id=ANY(wanted) AND c.teacher_id=p_adult AND (class_target IS NULL OR c.id=class_target);
  IF selected IS DISTINCT FROM wanted THEN RAISE no_data_found; END IF;
 ELSIF class_target IS NOT NULL THEN
  SELECT array_agg(id ORDER BY id) INTO selected FROM education.learners WHERE class_id=class_target;
 ELSE RAISE invalid_parameter_value; END IF;
 IF coalesce(cardinality(selected),0)=0 OR cardinality(selected)>200 THEN RAISE invalid_parameter_value; END IF;
 RETURN selected;
END;
$$;

CREATE OR REPLACE FUNCTION education.school_snapshot(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 WITH viewer AS (SELECT education.adult_role(p_adult) AS role), visible AS (
  SELECT l.id,l.name,l.class_id,l.created_at,c.teacher_id,c.name AS class_name,
    coalesce(p.age_band,CASE WHEN l.web_preferences->>'ageBand' IN ('6–8','9–12','13–15','16–18') THEN l.web_preferences->>'ageBand' END,'9–12') AS age_band,coalesce(p.grade_label,'') AS grade_label
  FROM education.learners l JOIN education.classes c ON c.id=l.class_id
  LEFT JOIN education.school_learning_profiles p ON p.learner_id=l.id
  WHERE education.school_can_view(p_adult,l.id)
 ), lessons AS (
  SELECT a.*,v.class_id,v.name AS learner_name FROM education.device_lessons a JOIN visible v ON v.id=a.learner_id
 ), messages AS (
  SELECT m.* FROM education.school_messages m WHERE EXISTS(SELECT FROM education.school_message_recipients r
  JOIN visible v ON v.id=r.learner_id WHERE r.message_id=m.id)
 ), calendar AS (
  SELECT e.* FROM education.school_events e WHERE EXISTS(SELECT FROM education.school_event_recipients r
  JOIN visible v ON v.id=r.learner_id WHERE r.event_id=e.id)
 )
 SELECT CASE WHEN v.role IN ('teacher','family') THEN jsonb_build_object(
  'role',v.role,'adult',jsonb_build_object('id',p_adult,'name',coalesce((SELECT display_name FROM public.profiles WHERE id=p_adult),'Adulto autorizado')),
  'classes',coalesce((SELECT jsonb_agg(q ORDER BY q.name) FROM (SELECT DISTINCT class_id AS id,class_name AS name FROM visible
    UNION SELECT id,name FROM education.classes WHERE teacher_id=p_adult AND v.role='teacher')q),'[]'::jsonb),
  'learners',coalesce((SELECT jsonb_agg(jsonb_build_object('id',id,'name',name,'classId',class_id,'ageBand',age_band,'gradeLabel',grade_label) ORDER BY name) FROM visible),'[]'::jsonb),
  'lessons',coalesce((SELECT jsonb_agg(jsonb_build_object('id',a.id,'lessonId',a.lesson_id,'learnerId',a.learner_id,'classId',a.class_id,
    'learnerName',a.learner_name,'title',a.title,'subject',a.subject,'goal',a.goal,'instructions',a.instructions,'dueAt',a.due_at,
    'factors',a.factors,'createdAt',a.created_at,
    'result',CASE WHEN r.result_id IS NULL THEN NULL ELSE jsonb_build_object('resultId',r.result_id,'attempts',r.payload->'attempts',
      'hints',r.payload->'hints','elapsedSeconds',r.payload->'elapsedSeconds','answers',r.payload->'answers','correctCount',r.correct_count,'receivedAt',r.received_at,
      'completedCount',coalesce((r.payload->>'completedCount')::integer,jsonb_array_length(a.factors)),
      'detailsShared',coalesce((r.payload->>'detailsShared')::boolean,true),'clientReported',coalesce((r.payload->>'clientReported')::boolean,false)) END,
    'review',CASE WHEN w.assignment_id IS NULL OR (v.role='family' AND w.published_at IS NULL) THEN NULL ELSE jsonb_build_object(
      'status',w.status,'observation',w.observation,'reviewedAt',w.reviewed_at,'publishedAt',w.published_at,
      'authorName',coalesce((SELECT display_name FROM public.profiles WHERE id=w.teacher_id),'Docente')) END
    ) ORDER BY a.created_at DESC) FROM lessons a LEFT JOIN education.device_lesson_results r ON r.assignment_id=a.id
    LEFT JOIN education.school_lesson_reviews w ON w.assignment_id=a.id),'[]'::jsonb),
  'grades',coalesce((SELECT jsonb_agg(jsonb_build_object('id',g.id,'learnerId',g.learner_id,'assignmentId',g.assignment_id,'subject',g.subject,
    'title',g.title,'value',g.value,'scale',10,'feedback',g.feedback,'authorName',coalesce((SELECT display_name FROM public.profiles WHERE id=g.teacher_id),'Docente'),
    'publishedAt',g.published_at,'createdAt',g.created_at,'updatedAt',g.updated_at,'revision',g.revision) ORDER BY g.created_at DESC)
    FROM education.school_grades g JOIN visible l ON l.id=g.learner_id WHERE v.role='teacher' OR g.published_at IS NOT NULL),'[]'::jsonb),
  'messages',coalesce((SELECT jsonb_agg(jsonb_build_object('id',m.id,'title',m.title,'body',CASE WHEN m.withdrawn_at IS NULL THEN m.body ELSE 'Comunicado retirado por el docente.' END,
    'authorName',coalesce((SELECT display_name FROM public.profiles WHERE id=m.teacher_id),'Docente'),'createdAt',m.created_at,'allowReplies',m.allow_replies AND m.withdrawn_at IS NULL,
    'withdrawnAt',m.withdrawn_at,'learnerIds',coalesce((SELECT jsonb_agg(r.learner_id) FROM education.school_message_recipients r JOIN visible l ON l.id=r.learner_id WHERE r.message_id=m.id),'[]'::jsonb),
    'readAt',(SELECT read_at FROM education.school_message_reads WHERE message_id=m.id AND adult_id=p_adult),
    'readCount',CASE WHEN v.role='teacher' THEN (SELECT count(*) FROM education.school_message_reads WHERE message_id=m.id) ELSE 0 END,
    'replies',coalesce((SELECT jsonb_agg(jsonb_build_object('id',r.id,'learnerId',r.learner_id,'body',r.body,
      'authorName',coalesce((SELECT display_name FROM public.profiles WHERE id=r.adult_id),'Adulto autorizado'),'own',r.adult_id=p_adult,'createdAt',r.created_at) ORDER BY r.created_at)
      FROM education.school_message_replies r WHERE r.message_id=m.id AND (v.role='teacher' OR (education.school_can_view(p_adult,r.learner_id)
      AND (r.adult_id=p_adult OR r.adult_id=m.teacher_id)))),'[]'::jsonb)) ORDER BY m.created_at DESC) FROM messages m),'[]'::jsonb),
  'events',coalesce((SELECT jsonb_agg(jsonb_build_object('id',e.id,'classId',e.class_id,'title',e.title,'description',e.description,'kind',e.kind,
    'startsAt',e.starts_at,'endsAt',e.ends_at,'createdAt',e.created_at,'cancelledAt',e.cancelled_at,
    'authorName',coalesce((SELECT display_name FROM public.profiles WHERE id=e.teacher_id),'Docente'),
    'learnerIds',coalesce((SELECT jsonb_agg(r.learner_id) FROM education.school_event_recipients r JOIN visible l ON l.id=r.learner_id WHERE r.event_id=e.id),'[]'::jsonb))
    ORDER BY e.starts_at) FROM calendar e),'[]'::jsonb),
  'devices',coalesce((SELECT jsonb_agg(jsonb_build_object('id',d.id,'learnerId',d.learner_id,'revoked',d.revoked,'lastSeenAt',d.last_seen_at))
    FROM education.devices d WHERE (v.role='teacher' AND d.teacher_id=p_adult) OR EXISTS(SELECT FROM visible l WHERE l.id=d.learner_id)),'[]'::jsonb),
  'settings',coalesce((SELECT jsonb_agg(jsonb_build_object('learnerId',l.id,'dailyMinutes',coalesce(s.daily_minutes,30),
    'startTime',left(coalesce(s.start_time::text,'08:00:00'),5),'endTime',left(coalesce(s.end_time::text,'20:00:00'),5),
    'timezone',coalesce(s.timezone,'Europe/Madrid'),'language',coalesce(s.language,'es'),'voiceEnabled',coalesce(s.voice_enabled,true),
    'captionsEnabled',CASE WHEN s.voice_enabled=false THEN true ELSE coalesce(s.captions_enabled,true) END,
    'textFirst',CASE WHEN s.voice_enabled=false THEN true ELSE coalesce(s.text_first,false) END,
    'sharePractice',coalesce(s.share_practice,true),'revision',coalesce(s.revision,0),'updatedAt',s.updated_at,'updatedBy',s.updated_by))
    FROM visible l LEFT JOIN education.school_device_settings s ON s.learner_id=l.id),'[]'::jsonb),
  'materials',CASE WHEN v.role='teacher' THEN coalesce((SELECT jsonb_agg(jsonb_build_object('id',d.id,'classId',d.class_id,'name',d.name,'createdAt',d.created_at))
    FROM education.documents d JOIN education.classes c ON c.id=d.class_id WHERE c.teacher_id=p_adult),'[]'::jsonb) ELSE '[]'::jsonb END
 ) END FROM viewer v;
$$;

CREATE OR REPLACE FUNCTION education.school_command(p_adult uuid,p_body jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE
 actor text := education.adult_role(p_adult);
 action_name text := p_body->>'action';
 command_request uuid := (p_body->>'requestId')::uuid;
 command_hash text := encode(sha256(convert_to(p_body::text,'UTF8')),'hex');
 receipt education.school_command_receipts%ROWTYPE;
 selected uuid[]; target uuid; entity uuid; result jsonb; assignments jsonb;
 pupil uuid := nullif(p_body->>'learnerId','')::uuid;
 saved_revision integer; expected_revision integer := coalesce((p_body->>'expectedRevision')::integer,0);
 published timestamptz := CASE WHEN coalesce((p_body->>'publish')::boolean,false) THEN clock_timestamp() END;
 message_row education.school_messages%ROWTYPE;
 grade_row education.school_grades%ROWTYPE;
BEGIN
 IF actor IS NULL OR command_request IS NULL THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_adult::text||':'||command_request::text,1843));
 SELECT * INTO receipt FROM education.school_command_receipts WHERE adult_id=p_adult AND request_id=command_request;
 IF FOUND THEN
  IF receipt.request_hash<>command_hash THEN RAISE EXCEPTION USING ERRCODE='23505',MESSAGE='school_request_conflict'; END IF;
  RETURN receipt.result;
 END IF;
 IF (SELECT count(*) FROM education.school_command_receipts WHERE adult_id=p_adult AND created_at>clock_timestamp()-interval '1 hour')>=1000
 THEN RAISE EXCEPTION USING ERRCODE='54000',MESSAGE='school_rate_limit'; END IF;

 CASE action_name
 WHEN 'batch-assign' THEN
  selected := education.school_targets(p_adult,p_body);
  IF p_body->>'subject' IS DISTINCT FROM 'matematicas' OR jsonb_typeof(p_body->'factors') IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_body->'factors') NOT BETWEEN 1 AND 5 THEN RAISE invalid_parameter_value; END IF;
  IF EXISTS(SELECT FROM jsonb_array_elements(p_body->'factors') a WHERE jsonb_typeof(a) IS DISTINCT FROM 'array'
    OR jsonb_array_length(a)<>2 OR (a->>0)::integer NOT BETWEEN 1 AND 12 OR (a->>1)::integer NOT BETWEEN 1 AND 12)
  THEN RAISE invalid_parameter_value; END IF;
  WITH inserted AS (
   INSERT INTO education.device_lessons(teacher_id,learner_id,title,subject,goal,instructions,due_at,factors)
   SELECT p_adult,l,p_body->>'title','matematicas',p_body->>'goal',p_body->>'instructions',(p_body->>'dueAt')::date,p_body->'factors'
   FROM unnest(selected)l RETURNING id,lesson_id,learner_id
  ) SELECT jsonb_agg(jsonb_build_object('id',id,'lessonId',lesson_id,'learnerId',learner_id)) INTO assignments FROM inserted;
  result := jsonb_build_object('assigned',cardinality(selected),'assignments',assignments);

 WHEN 'review-lesson' THEN
  entity := (p_body->>'assignmentId')::uuid;
  SELECT a.learner_id INTO pupil FROM education.device_lessons a JOIN education.device_lesson_results r ON r.assignment_id=a.id
  WHERE a.id=entity AND a.teacher_id=p_adult AND education.school_owns(p_adult,a.learner_id) FOR SHARE OF a;
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  INSERT INTO education.school_lesson_reviews(assignment_id,teacher_id,status,observation,published_at)
  VALUES(entity,p_adult,p_body->>'status',p_body->>'observation',published)
  ON CONFLICT(assignment_id) DO UPDATE SET status=excluded.status,observation=excluded.observation,
   reviewed_at=clock_timestamp(),published_at=excluded.published_at;
  result := jsonb_build_object('assignmentId',entity,'published',published IS NOT NULL);

 WHEN 'save-grade' THEN
  IF NOT education.school_owns(p_adult,pupil) THEN RAISE no_data_found; END IF;
  target := nullif(p_body->>'assignmentId','')::uuid;
  IF target IS NOT NULL AND NOT EXISTS(SELECT FROM education.device_lessons WHERE id=target AND learner_id=pupil AND teacher_id=p_adult)
  THEN RAISE no_data_found; END IF;
  entity := nullif(p_body->>'gradeId','')::uuid;
  IF entity IS NULL THEN
   INSERT INTO education.school_grades(learner_id,teacher_id,assignment_id,subject,title,value,feedback,published_at)
   VALUES(pupil,p_adult,target,p_body->>'subject',p_body->>'title',(p_body->>'value')::numeric,coalesce(p_body->>'feedback',''),published)
   RETURNING id,revision INTO entity,saved_revision;
  ELSE
   SELECT * INTO grade_row FROM education.school_grades WHERE id=entity AND teacher_id=p_adult AND learner_id=pupil FOR UPDATE;
   IF NOT FOUND THEN RAISE no_data_found; END IF;
   IF grade_row.revision<>expected_revision THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='school_revision_conflict'; END IF;
   UPDATE education.school_grades SET assignment_id=target,subject=p_body->>'subject',title=p_body->>'title',
    value=(p_body->>'value')::numeric,feedback=coalesce(p_body->>'feedback',''),published_at=published,
    revision=revision+1,updated_at=clock_timestamp() WHERE id=entity RETURNING revision INTO saved_revision;
  END IF;
  result := jsonb_build_object('id',entity,'revision',saved_revision,'published',published IS NOT NULL);

 WHEN 'withdraw-grade' THEN
  entity := (p_body->>'gradeId')::uuid;
  UPDATE education.school_grades SET published_at=NULL,revision=revision+1,updated_at=clock_timestamp()
   WHERE id=entity AND teacher_id=p_adult AND education.school_owns(p_adult,learner_id) RETURNING learner_id INTO pupil;
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  result := jsonb_build_object('id',entity,'withdrawn',true);

 WHEN 'send-message' THEN
  selected := education.school_targets(p_adult,p_body);
  INSERT INTO education.school_messages(teacher_id,title,body,allow_replies)
  VALUES(p_adult,p_body->>'title',p_body->>'body',(p_body->>'allowReplies')::boolean) RETURNING id INTO entity;
  INSERT INTO education.school_message_recipients(message_id,learner_id) SELECT entity,l FROM unnest(selected)l;
  result := jsonb_build_object('id',entity,'recipientCount',cardinality(selected));

 WHEN 'reply-message' THEN
  target := (p_body->>'messageId')::uuid;
  SELECT * INTO message_row FROM education.school_messages WHERE id=target AND withdrawn_at IS NULL FOR SHARE;
  IF NOT FOUND OR NOT EXISTS(SELECT FROM education.school_message_recipients WHERE message_id=target AND learner_id=pupil)
   OR NOT education.school_can_view(p_adult,pupil) THEN RAISE no_data_found; END IF;
  IF (actor='teacher' AND message_row.teacher_id<>p_adult) OR (actor='family' AND NOT message_row.allow_replies)
  THEN RAISE insufficient_privilege; END IF;
  INSERT INTO education.school_message_replies(message_id,learner_id,adult_id,body)
  VALUES(target,pupil,p_adult,p_body->>'body') RETURNING id INTO entity;
  result := jsonb_build_object('id',entity);

 WHEN 'mark-message-read' THEN
  entity := (p_body->>'messageId')::uuid;
  IF NOT EXISTS(SELECT FROM education.school_message_recipients r WHERE r.message_id=entity AND education.school_can_view(p_adult,r.learner_id))
  THEN RAISE no_data_found; END IF;
  INSERT INTO education.school_message_reads(message_id,adult_id) VALUES(entity,p_adult) ON CONFLICT DO NOTHING;
  result := jsonb_build_object('id',entity,'read',true);

 WHEN 'withdraw-message' THEN
  entity := (p_body->>'messageId')::uuid;
  UPDATE education.school_messages SET withdrawn_at=coalesce(withdrawn_at,clock_timestamp()) WHERE id=entity AND teacher_id=p_adult AND actor='teacher';
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  result := jsonb_build_object('id',entity,'withdrawn',true);

 WHEN 'save-event' THEN
  selected := education.school_targets(p_adult,p_body);
  entity := nullif(p_body->>'eventId','')::uuid;
  IF entity IS NULL THEN
   INSERT INTO education.school_events(teacher_id,class_id,title,description,kind,starts_at,ends_at)
   VALUES(p_adult,nullif(p_body->>'classId','')::uuid,p_body->>'title',coalesce(p_body->>'description',''),p_body->>'kind',
    (p_body->>'startsAt')::timestamptz,nullif(p_body->>'endsAt','')::timestamptz) RETURNING id INTO entity;
  ELSE
   UPDATE education.school_events SET class_id=nullif(p_body->>'classId','')::uuid,title=p_body->>'title',
    description=coalesce(p_body->>'description',''),kind=p_body->>'kind',starts_at=(p_body->>'startsAt')::timestamptz,
    ends_at=nullif(p_body->>'endsAt','')::timestamptz,cancelled_at=NULL WHERE id=entity AND teacher_id=p_adult;
   IF NOT FOUND THEN RAISE no_data_found; END IF;
   DELETE FROM education.school_event_recipients WHERE event_id=entity;
  END IF;
  INSERT INTO education.school_event_recipients(event_id,learner_id) SELECT entity,l FROM unnest(selected)l;
  result := jsonb_build_object('id',entity,'recipientCount',cardinality(selected));

 WHEN 'delete-event' THEN
  entity := (p_body->>'eventId')::uuid;
  UPDATE education.school_events SET cancelled_at=coalesce(cancelled_at,clock_timestamp()) WHERE id=entity AND teacher_id=p_adult AND actor='teacher';
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  result := jsonb_build_object('id',entity,'cancelled',true);

 WHEN 'save-settings' THEN
  IF NOT education.school_can_view(p_adult,pupil) THEN RAISE no_data_found; END IF;
  IF actor='teacher' AND EXISTS(SELECT FROM education.family_links WHERE learner_id=pupil)
  THEN RAISE insufficient_privilege; END IF;
  IF NOT EXISTS(SELECT FROM pg_timezone_names WHERE name=p_body->>'timezone') THEN RAISE invalid_parameter_value; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(pupil::text,1844));
  SELECT revision INTO saved_revision FROM education.school_device_settings WHERE learner_id=pupil FOR UPDATE;
  IF coalesce(saved_revision,0)<>expected_revision THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='school_revision_conflict'; END IF;
  INSERT INTO education.school_device_settings(learner_id,daily_minutes,start_time,end_time,timezone,language,voice_enabled,share_practice,captions_enabled,text_first,updated_by)
  VALUES(pupil,(p_body->>'dailyMinutes')::smallint,(p_body->>'startTime')::time,(p_body->>'endTime')::time,
   p_body->>'timezone',p_body->>'language',(p_body->>'voiceEnabled')::boolean,(p_body->>'sharePractice')::boolean,
   CASE WHEN NOT (p_body->>'voiceEnabled')::boolean THEN true ELSE coalesce((p_body->>'captionsEnabled')::boolean,true) END,
   CASE WHEN NOT (p_body->>'voiceEnabled')::boolean THEN true ELSE coalesce((p_body->>'textFirst')::boolean,false) END,p_adult)
  ON CONFLICT(learner_id) DO UPDATE SET daily_minutes=excluded.daily_minutes,start_time=excluded.start_time,end_time=excluded.end_time,
   timezone=excluded.timezone,language=excluded.language,voice_enabled=excluded.voice_enabled,share_practice=excluded.share_practice,
   captions_enabled=excluded.captions_enabled,text_first=excluded.text_first,
   revision=school_device_settings.revision+1,updated_by=excluded.updated_by,updated_at=clock_timestamp()
  RETURNING revision INTO saved_revision;
  IF NOT (p_body->>'sharePractice')::boolean THEN
   UPDATE education.device_lesson_results r SET payload=jsonb_set(jsonb_set(r.payload,'{answers}','[]'::jsonb),'{detailsShared}','false'::jsonb)
   FROM education.device_lessons a WHERE a.id=r.assignment_id AND a.learner_id=pupil;
  END IF;
  result := jsonb_build_object('learnerId',pupil,'revision',saved_revision);

 WHEN 'save-profile' THEN
  IF NOT education.school_owns(p_adult,pupil) THEN RAISE no_data_found; END IF;
  INSERT INTO education.school_learning_profiles(learner_id,age_band,grade_label,updated_by)
  VALUES(pupil,p_body->>'ageBand',coalesce(p_body->>'gradeLabel',''),p_adult)
  ON CONFLICT(learner_id) DO UPDATE SET age_band=excluded.age_band,grade_label=excluded.grade_label,
   updated_by=excluded.updated_by,updated_at=clock_timestamp();
  result := jsonb_build_object('learnerId',pupil,'saved',true);
 ELSE RAISE invalid_parameter_value;
 END CASE;

 INSERT INTO education.school_audit(adult_id,action,entity_id,learner_id,details)
 VALUES(p_adult,action_name,entity,pupil,jsonb_build_object('published',published IS NOT NULL,'recipientCount',coalesce(cardinality(selected),0)));
 INSERT INTO education.school_command_receipts(adult_id,request_id,request_hash,result)
 VALUES(p_adult,command_request,command_hash,result);
 RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION education.school_read(p_adult uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE snapshot jsonb;
BEGIN
 snapshot := education.school_snapshot(p_adult);
 IF snapshot IS NOT NULL THEN
  INSERT INTO education.school_audit(adult_id,action,details)
  VALUES(p_adult,'school-read',jsonb_build_object('scope','authorized_school_records'));
 END IF;
 RETURN snapshot;
END;
$$;

CREATE OR REPLACE FUNCTION education.device_school_context(p_learner uuid,p_teacher uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT jsonb_build_object(
  'serverTime',floor(extract(epoch FROM clock_timestamp())),
  'deviceSettings',jsonb_build_object('dailyMinutes',coalesce(s.daily_minutes,30),
   'startTime',left(coalesce(s.start_time::text,'08:00:00'),5),'endTime',left(coalesce(s.end_time::text,'20:00:00'),5),
   'timezone',coalesce(s.timezone,'Europe/Madrid'),'language',coalesce(s.language,'es'),
   'utcOffsetMinutes',extract(epoch FROM ((clock_timestamp() AT TIME ZONE coalesce(s.timezone,'Europe/Madrid'))-(clock_timestamp() AT TIME ZONE 'UTC')))::integer/60,
   'voiceEnabled',coalesce(s.voice_enabled,true),'sharePractice',coalesce(s.share_practice,true),'revision',coalesce(s.revision,0),
   'captionsEnabled',CASE WHEN s.voice_enabled=false THEN true ELSE coalesce(s.captions_enabled,true) END,
   'textFirst',CASE WHEN s.voice_enabled=false THEN true ELSE coalesce(s.text_first,false) END),
  'educationalProfile',jsonb_build_object('ageBand',coalesce(p.age_band,CASE WHEN l.web_preferences->>'ageBand' IN ('6–8','9–12','13–15','16–18') THEN l.web_preferences->>'ageBand' END,'9–12'),
   'gradeLabel',coalesce(p.grade_label,''),'language',coalesce(s.language,'es'),'alias',left(split_part(trim(l.name),' ',1),24)),
  'learningSummary',jsonb_build_object(
   'completedLessons',(SELECT count(*) FROM education.device_lesson_results r JOIN education.device_lessons a ON a.id=r.assignment_id WHERE a.learner_id=l.id AND a.teacher_id=p_teacher),
   'lastConcepts',coalesce((SELECT jsonb_agg(title) FROM (SELECT a.title,max(r.received_at) AS at FROM education.device_lessons a
    JOIN education.device_lesson_results r ON r.assignment_id=a.id WHERE a.learner_id=l.id AND a.teacher_id=p_teacher GROUP BY a.title ORDER BY at DESC LIMIT 8)q),'[]'::jsonb),
   'practiceDays',(SELECT count(DISTINCT (r.received_at AT TIME ZONE 'UTC')::date) FROM education.device_lesson_results r
    JOIN education.device_lessons a ON a.id=r.assignment_id WHERE a.learner_id=l.id AND a.teacher_id=p_teacher),
   'practiceDaysBasis','synchronization_days'))
 FROM education.learners l JOIN education.classes c ON c.id=l.class_id
 LEFT JOIN education.school_device_settings s ON s.learner_id=l.id
 LEFT JOIN education.school_learning_profiles p ON p.learner_id=l.id
 WHERE l.id=p_learner AND c.teacher_id=p_teacher;
$$;

CREATE OR REPLACE FUNCTION education.onboard_family(p_adult uuid,p_age_confirmed boolean)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE prior text;
BEGIN
 IF p_age_confirmed IS DISTINCT FROM true OR NOT EXISTS(SELECT FROM auth.users WHERE id=p_adult)
 THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_adult::text,1845));
 prior := education.adult_role(p_adult);
 IF prior IS NOT NULL THEN RETURN prior; END IF;
 INSERT INTO education.adult_accounts(user_id,role,provenance) VALUES(p_adult,'family','family_adult_self_declaration');
 -- Compatibility mirror only after the separate server-owned role was granted.
 -- A caller editing these profile fields cannot grant any role to itself.
 INSERT INTO public.profiles(id,account_type,age_band,display_name)
 SELECT id,'family','18+',left(coalesce(nullif(raw_user_meta_data->>'display_name',''),nullif(raw_user_meta_data->>'full_name',''),'Familiar'),120)
 FROM auth.users WHERE id=p_adult
 ON CONFLICT(id) DO UPDATE SET account_type='family',age_band='18+',
  display_name=CASE WHEN trim(profiles.display_name)='' THEN excluded.display_name ELSE profiles.display_name END,
  updated_at=clock_timestamp();
 INSERT INTO education.school_audit(adult_id,action,details) VALUES(p_adult,'family_onboarding',jsonb_build_object('ageSelfDeclared',true));
 RETURN 'family';
END;
$$;

CREATE OR REPLACE FUNCTION education.school_proposal_context(p_adult uuid,p_class uuid,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE sources jsonb;
BEGIN
 IF education.adult_role(p_adult) IS DISTINCT FROM 'teacher' OR NOT EXISTS(SELECT FROM education.classes WHERE id=p_class AND teacher_id=p_adult)
 THEN RAISE no_data_found; END IF;
 IF p_request IS NULL THEN RAISE invalid_parameter_value; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_adult::text,1846));
 IF (SELECT count(*) FROM education.school_audit WHERE adult_id=p_adult AND action='suggest-assignment' AND created_at>clock_timestamp()-interval '24 hours')>=20
 THEN RAISE EXCEPTION USING ERRCODE='54000',MESSAGE='school_proposal_limit'; END IF;
 INSERT INTO education.school_audit(adult_id,action,entity_id) VALUES(p_adult,'suggest-assignment',p_request);
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'page',page,'content',content)),'[]'::jsonb) INTO sources
 FROM (SELECT ch.id,ch.page,left(ch.content,1800) AS content FROM education.chunks ch
 JOIN education.documents d ON d.id=ch.document_id WHERE d.class_id=p_class ORDER BY d.created_at DESC,ch.page NULLS FIRST,ch.id LIMIT 6)q;
 RETURN jsonb_build_object('sources',sources);
END;
$$;

-- Extend the existing export without changing its public contract or deleting school records.
CREATE OR REPLACE FUNCTION education.minimize_device_receipt(p_device uuid,p_assignment uuid,p_result uuid,p_hash text,p_payload jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE receipt education.device_lesson_results%ROWTYPE; factor_count integer;
BEGIN
 IF p_payload->'detailsShared' IS DISTINCT FROM 'false'::jsonb OR p_payload->'answers' IS DISTINCT FROM '[]'::jsonb
  OR p_payload->>'resultId' IS DISTINCT FROM p_result::text OR p_payload->>'assignmentId' IS DISTINCT FROM p_assignment::text
 THEN RETURN false; END IF;
 SELECT r.* INTO receipt FROM education.device_lesson_results r JOIN education.device_lessons a ON a.id=r.assignment_id
 JOIN education.devices d ON d.id=r.device_id JOIN education.learners l ON l.id=a.learner_id JOIN education.classes c ON c.id=l.class_id
 WHERE r.device_id=p_device AND r.assignment_id=p_assignment AND r.result_id=p_result AND NOT d.revoked
  AND d.learner_id=a.learner_id AND d.teacher_id=a.teacher_id AND c.teacher_id=d.teacher_id
  AND a.lesson_id::text=p_payload->>'lessonId' FOR UPDATE OF r;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT jsonb_array_length(factors) INTO factor_count FROM education.device_lessons WHERE id=p_assignment;
 IF (p_payload->>'completedCount')::integer IS DISTINCT FROM factor_count
  OR p_payload->'attempts' IS DISTINCT FROM receipt.payload->'attempts'
  OR p_payload->'hints' IS DISTINCT FROM receipt.payload->'hints'
  OR p_payload->'elapsedSeconds' IS DISTINCT FROM receipt.payload->'elapsedSeconds'
 THEN RETURN false; END IF;
 UPDATE education.device_lesson_results SET payload=p_payload,request_hash=p_hash WHERE result_id=p_result;
 RETURN true;
END;
$$;

-- Extend the existing export without changing its public contract or deleting school records.
DO $$ BEGIN
 IF to_regprocedure('education.export_learning_data_base(uuid)') IS NULL THEN
  ALTER FUNCTION education.export_learning_data(uuid) RENAME TO export_learning_data_base;
 END IF;
END $$;
CREATE OR REPLACE FUNCTION education.export_learning_data(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT CASE WHEN education.adult_role(p_adult) IS NOT NULL THEN
  coalesce(education.export_learning_data_base(p_adult),'{}'::jsonb)
  || jsonb_build_object('school',education.school_snapshot(p_adult)) END;
$$;
REVOKE ALL ON FUNCTION education.export_learning_data_base(uuid) FROM PUBLIC,anon,authenticated,peluqo_backend;

-- Existing device reports now use the same server-controlled role registry.
CREATE OR REPLACE FUNCTION education.device_lesson_snapshot(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT CASE WHEN education.adult_role(p_adult) IS NOT NULL THEN
 jsonb_build_object('role',education.adult_role(p_adult),'lessons',coalesce((
 SELECT jsonb_agg(jsonb_build_object('id',a.id,'learnerId',a.learner_id,'learnerName',l.name,'classId',l.class_id,
  'title',a.title,'goal',a.goal,'instructions',a.instructions,'dueAt',a.due_at,'createdAt',a.created_at,'exerciseCount',jsonb_array_length(a.factors),
  'result',CASE WHEN r.result_id IS NULL THEN NULL ELSE jsonb_build_object('resultId',r.result_id,'attempts',r.payload->'attempts','hints',r.payload->'hints',
   'elapsedSeconds',r.payload->'elapsedSeconds','answers',r.payload->'answers','correctCount',r.correct_count,'receivedAt',r.received_at) END) ORDER BY a.created_at DESC)
 FROM education.device_lessons a JOIN education.learners l ON l.id=a.learner_id
 LEFT JOIN education.device_lesson_results r ON r.assignment_id=a.id WHERE education.school_can_view(p_adult,a.learner_id)), '[]'::jsonb)) END;
$$;

ALTER TABLE education.inference_jobs DROP CONSTRAINT IF EXISTS inference_jobs_kind_check;
ALTER TABLE education.inference_jobs ADD CONSTRAINT inference_jobs_kind_check CHECK(kind IN ('generate','tutor','curiosity','proposal'));

REVOKE ALL ON FUNCTION education.school_can_view(uuid,uuid),education.school_owns(uuid,uuid),education.school_targets(uuid,jsonb),
 education.school_snapshot(uuid),education.school_read(uuid),education.school_command(uuid,jsonb),education.device_school_context(uuid,uuid),
 education.onboard_family(uuid,boolean),education.school_proposal_context(uuid,uuid,uuid),
 education.minimize_device_receipt(uuid,uuid,uuid,text,jsonb),
 education.export_learning_data(uuid),education.device_lesson_snapshot(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION education.school_can_view(uuid,uuid),education.school_owns(uuid,uuid),education.school_targets(uuid,jsonb),
 education.school_snapshot(uuid),education.school_read(uuid),education.school_command(uuid,jsonb),education.device_school_context(uuid,uuid),
 education.onboard_family(uuid,boolean),education.school_proposal_context(uuid,uuid,uuid),
 education.minimize_device_receipt(uuid,uuid,uuid,text,jsonb),
 education.export_learning_data(uuid),education.device_lesson_snapshot(uuid) TO peluqo_backend;
COMMIT;
