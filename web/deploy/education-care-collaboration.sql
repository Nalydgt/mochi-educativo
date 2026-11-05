-- Private family accompaniment, family reminders and teacher-supervised collaboration.
-- Additive migration. No historical awards or modifications to existing demonstration records.
BEGIN;

ALTER TABLE education.school_device_settings ADD COLUMN reminder_minutes smallint DEFAULT 10
 CHECK(reminder_minutes IS NULL OR reminder_minutes BETWEEN 5 AND 60),
 ADD COLUMN family_support_alerts_enabled boolean NOT NULL DEFAULT false,
 ADD COLUMN family_support_alerts_by uuid REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE TABLE education.school_care_signals (
 id uuid PRIMARY KEY,
 device_id uuid REFERENCES education.devices(id) ON DELETE SET NULL,
 learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
 category text NOT NULL CHECK(category='possible_peer_bullying'),
 source text NOT NULL CHECK(source IN ('daily_voice','lesson_voice')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX school_care_learner_time ON education.school_care_signals(learner_id,created_at);
CREATE TABLE education.school_care_recipients (
 signal_id uuid NOT NULL REFERENCES education.school_care_signals(id) ON DELETE CASCADE,
 adult_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 PRIMARY KEY(signal_id,adult_id)
);
CREATE INDEX school_care_recipients_adult ON education.school_care_recipients(adult_id,signal_id);
CREATE TABLE education.school_care_reviews (
 signal_id uuid NOT NULL,
 adult_id uuid NOT NULL,
 status text NOT NULL CHECK(status IN ('reviewed','dismissed')),
 reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(signal_id,adult_id),
 FOREIGN KEY(signal_id,adult_id) REFERENCES education.school_care_recipients(signal_id,adult_id) ON DELETE CASCADE
);
CREATE TABLE education.school_groups (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 class_id uuid NOT NULL REFERENCES education.classes(id) ON DELETE CASCADE,
 teacher_id uuid NOT NULL REFERENCES education.teachers(id),
 name text NOT NULL CHECK(char_length(name) BETWEEN 2 AND 60),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 archived_at timestamptz
);
CREATE INDEX school_groups_class ON education.school_groups(class_id);
CREATE TABLE education.school_group_members (
 group_id uuid NOT NULL REFERENCES education.school_groups(id) ON DELETE CASCADE,
 learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
 peer_role text NOT NULL CHECK(peer_role IN ('member','helper')),
 voluntary boolean NOT NULL,
 buddy_alias text CHECK(char_length(buddy_alias) BETWEEN 1 AND 16),
 PRIMARY KEY(group_id,learner_id),
 CHECK(peer_role<>'helper' OR voluntary)
);
CREATE TABLE education.school_group_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 group_id uuid NOT NULL REFERENCES education.school_groups(id) ON DELETE CASCADE,
 teacher_id uuid NOT NULL REFERENCES education.teachers(id),
 member_count smallint NOT NULL CHECK(member_count BETWEEN 2 AND 8),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE education.device_lessons
 ADD COLUMN group_id uuid REFERENCES education.school_groups(id) ON DELETE SET NULL,
 ADD COLUMN group_batch_id uuid REFERENCES education.school_group_batches(id) ON DELETE SET NULL,
 ADD COLUMN peer_role text CHECK(peer_role IN ('member','helper')),
 ADD COLUMN helper_voluntary boolean NOT NULL DEFAULT false,
 ADD COLUMN child_buddy_alias text CHECK(char_length(child_buddy_alias) BETWEEN 1 AND 16);
CREATE INDEX device_lessons_group_batch ON education.device_lessons(group_batch_id) WHERE group_batch_id IS NOT NULL;
CREATE TABLE education.school_help_confirmations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 assignment_id uuid NOT NULL REFERENCES education.device_lessons(id) ON DELETE CASCADE,
 helped_learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
 teacher_id uuid NOT NULL REFERENCES education.teachers(id),
 confirmed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(assignment_id,helped_learner_id)
);
CREATE TABLE education.school_point_ledger (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
 teacher_id uuid NOT NULL REFERENCES education.teachers(id),
 reason text NOT NULL CHECK(reason IN ('review','group','help')),
 points smallint NOT NULL,
 source_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((reason='review' AND points=10) OR (reason='group' AND points=20) OR (reason='help' AND points=5)),
 UNIQUE(learner_id,reason,source_id)
);
CREATE INDEX school_point_learner_time ON education.school_point_ledger(learner_id,created_at);
DO $$ DECLARE relation text; BEGIN
 FOREACH relation IN ARRAY ARRAY['school_care_signals','school_care_recipients','school_care_reviews','school_groups','school_group_members',
  'school_group_batches','school_help_confirmations','school_point_ledger'] LOOP
  EXECUTE format('ALTER TABLE education.%I ENABLE ROW LEVEL SECURITY',relation);
  EXECUTE format('REVOKE ALL ON education.%I FROM PUBLIC,anon,authenticated,peluqo_backend',relation);
 END LOOP;
END $$;

CREATE FUNCTION education.remove_orphan_care_signal()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ BEGIN
 DELETE FROM education.school_care_signals s WHERE s.id=OLD.signal_id
 AND NOT EXISTS(SELECT FROM education.school_care_recipients r WHERE r.signal_id=s.id);
 RETURN OLD;
END; $$;
CREATE TRIGGER remove_orphan_care_signal AFTER DELETE ON education.school_care_recipients
FOR EACH ROW EXECUTE FUNCTION education.remove_orphan_care_signal();

-- Ninety days allow family follow-up without keeping a permanent incident history.
-- Called by authorized school reads; the database owner may also run it for maintenance.
-- No incident counts or cleanup metadata are returned to teachers or general school audit.
CREATE FUNCTION education.cleanup_care_signals()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ BEGIN
 DELETE FROM education.school_care_signals WHERE created_at<clock_timestamp()-interval '90 days';
 DELETE FROM education.school_care_recipients r USING education.school_care_signals s
 WHERE r.signal_id=s.id AND (education.adult_role(r.adult_id) IS DISTINCT FROM 'family'
 OR NOT EXISTS(SELECT FROM education.family_links f WHERE f.guardian_id=r.adult_id AND f.learner_id=s.learner_id));
 DELETE FROM education.school_care_signals s WHERE NOT EXISTS(SELECT FROM education.school_care_recipients r WHERE r.signal_id=s.id);
END; $$;

CREATE FUNCTION education.family_support_enabled(p_learner uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT EXISTS(SELECT FROM education.school_device_settings s JOIN education.family_links f
 ON f.learner_id=s.learner_id AND f.guardian_id=s.family_support_alerts_by
 WHERE s.learner_id=p_learner AND s.family_support_alerts_enabled AND education.adult_role(f.guardian_id)='family'); $$;

-- Only the validated integration route can call this. Actor, learner and date never come from the body.
CREATE FUNCTION education.ingest_support_signal(p_device uuid,p_signal uuid,p_category text,p_source text,p_school_peers boolean,p_child_confirmed boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE pupil uuid; prior education.school_care_signals%ROWTYPE;
BEGIN
 IF p_signal IS NULL OR p_category IS DISTINCT FROM 'possible_peer_bullying'
 OR p_source NOT IN ('daily_voice','lesson_voice') OR p_source IS NULL OR p_school_peers IS DISTINCT FROM true
 OR p_child_confirmed IS DISTINCT FROM true THEN RAISE invalid_parameter_value; END IF;
 SELECT d.learner_id INTO pupil FROM education.devices d
 JOIN education.learners l ON l.id=d.learner_id JOIN education.classes c ON c.id=l.class_id
 WHERE d.id=p_device AND NOT d.revoked AND c.teacher_id=d.teacher_id;
 IF NOT FOUND THEN RAISE insufficient_privilege; END IF;
 -- Family-link changes already lock the learner before touching device/session rows.
 PERFORM id FROM education.learners WHERE id=pupil FOR SHARE;
 PERFORM d.id FROM education.devices d JOIN education.learners l ON l.id=d.learner_id JOIN education.classes c ON c.id=l.class_id
 WHERE d.id=p_device AND d.learner_id=pupil AND NOT d.revoked AND c.teacher_id=d.teacher_id FOR SHARE OF d;
 IF NOT FOUND THEN RAISE insufficient_privilege; END IF;
 PERFORM learner_id FROM education.school_device_settings WHERE learner_id=pupil FOR SHARE;
 IF NOT FOUND THEN RAISE insufficient_privilege; END IF;
 IF NOT education.family_support_enabled(pupil)
 THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_signal::text,5142));
 SELECT * INTO prior FROM education.school_care_signals WHERE id=p_signal;
 IF FOUND THEN
  IF prior.device_id IS DISTINCT FROM p_device OR prior.learner_id<>pupil OR prior.source<>p_source
  THEN RAISE unique_violation; END IF;
  RETURN jsonb_build_object('accepted',true,'signalId',p_signal,'visibleToFamily',EXISTS(
   SELECT FROM education.school_care_recipients r JOIN education.family_links f ON f.guardian_id=r.adult_id AND f.learner_id=pupil
   WHERE r.signal_id=p_signal AND education.adult_role(r.adult_id)='family'
    AND prior.created_at>=clock_timestamp()-interval '90 days'));
 END IF;
 INSERT INTO education.school_care_signals(id,device_id,learner_id,category,source)
 VALUES(p_signal,p_device,pupil,p_category,p_source);
 INSERT INTO education.school_care_recipients(signal_id,adult_id)
 SELECT p_signal,f.guardian_id FROM education.family_links f WHERE f.learner_id=pupil AND education.adult_role(f.guardian_id)='family';
 IF NOT FOUND THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('accepted',true,'signalId',p_signal,'visibleToFamily',true);
END;
$$;

-- Wrappers preserve existing commands, result receipts and multiplication-v1 payloads.
ALTER FUNCTION education.school_snapshot(uuid) RENAME TO school_snapshot_before_care;
ALTER FUNCTION education.school_command(uuid,jsonb) RENAME TO school_command_before_care;
ALTER FUNCTION education.device_school_context(uuid,uuid) RENAME TO device_school_context_before_care;

CREATE FUNCTION education.school_snapshot(p_adult uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=''
AS $$
DECLARE snapshot jsonb; actor text := education.adult_role(p_adult);
BEGIN
 snapshot := education.school_snapshot_before_care(p_adult);
 IF snapshot IS NULL THEN RETURN NULL; END IF;
 snapshot := jsonb_set(snapshot,'{settings}',coalesce((SELECT jsonb_agg(item||jsonb_build_object('reminderMinutes',
  CASE WHEN s.learner_id IS NULL THEN 10 ELSE s.reminder_minutes END)
  ||CASE WHEN actor='family' THEN jsonb_build_object('familySupportAlertsEnabled',education.family_support_enabled((item->>'learnerId')::uuid)) ELSE '{}'::jsonb END)
  FROM jsonb_array_elements(snapshot->'settings') item
  LEFT JOIN education.school_device_settings s ON s.learner_id=(item->>'learnerId')::uuid),'[]'::jsonb));
 snapshot := jsonb_set(snapshot,'{lessons}',coalesce((SELECT jsonb_agg(item||jsonb_build_object(
  'groupId',a.group_id,'groupBatchId',a.group_batch_id,'peerRole',a.peer_role,'childBuddyAlias',a.child_buddy_alias))
  FROM jsonb_array_elements(snapshot->'lessons') item JOIN education.device_lessons a ON a.id=(item->>'id')::uuid),'[]'::jsonb));
 snapshot := snapshot||jsonb_build_object(
  'groups',CASE WHEN actor='teacher' THEN coalesce((SELECT jsonb_agg(jsonb_build_object('id',g.id,'classId',g.class_id,
   'name',g.name,'revision',g.revision,'archivedAt',g.archived_at,'members',coalesce((SELECT jsonb_agg(jsonb_build_object(
    'learnerId',m.learner_id,'peerRole',m.peer_role,'voluntary',m.voluntary,'buddyAlias',m.buddy_alias) ORDER BY m.learner_id)
    FROM education.school_group_members m WHERE m.group_id=g.id),'[]'::jsonb)) ORDER BY g.created_at)
   FROM education.school_groups g JOIN education.classes c ON c.id=g.class_id WHERE g.teacher_id=p_adult AND c.teacher_id=p_adult),'[]'::jsonb) ELSE '[]'::jsonb END,
  'points',coalesce((SELECT jsonb_agg(jsonb_build_object('id',p.id,'learnerId',p.learner_id,'points',p.points,
   'reason',p.reason,'sourceId',p.source_id,'createdAt',p.created_at) ORDER BY p.created_at)
   FROM education.school_point_ledger p WHERE education.school_can_view(p_adult,p.learner_id)),'[]'::jsonb));
 -- No care field, category, count, review or incident exists in a teacher response.
 IF actor='family' THEN
  snapshot := snapshot||jsonb_build_object('careAlerts',coalesce((SELECT jsonb_agg(jsonb_build_object('id',s.id,
   'learnerId',s.learner_id,'category',s.category,'createdAt',s.created_at,
   'status',coalesce(r.status,'pending_review'),'reviewedAt',r.reviewed_at) ORDER BY s.created_at DESC)
   FROM education.school_care_signals s LEFT JOIN education.school_care_reviews r ON r.signal_id=s.id AND r.adult_id=p_adult
   WHERE s.created_at>=statement_timestamp()-interval '90 days' AND education.school_can_view(p_adult,s.learner_id) AND EXISTS(SELECT FROM education.school_care_recipients recipient
    WHERE recipient.signal_id=s.id AND recipient.adult_id=p_adult)),'[]'::jsonb));
 END IF;
 RETURN snapshot;
END;
$$;

CREATE FUNCTION education.award_review_points(p_teacher uuid,p_assignment uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE pupil uuid; batch uuid;
BEGIN
 SELECT a.learner_id,a.group_batch_id INTO pupil,batch FROM education.device_lessons a
 JOIN education.school_lesson_reviews r ON r.assignment_id=a.id AND r.published_at IS NOT NULL
 WHERE a.id=p_assignment AND a.teacher_id=p_teacher AND education.school_owns(p_teacher,a.learner_id);
 IF NOT FOUND THEN RETURN; END IF;
 INSERT INTO education.school_point_ledger(learner_id,teacher_id,reason,points,source_id)
 VALUES(pupil,p_teacher,'review',10,p_assignment) ON CONFLICT DO NOTHING;
 IF batch IS NOT NULL THEN
  -- Serialize final reviews so simultaneous publications cannot miss the group bonus.
  PERFORM pg_advisory_xact_lock(hashtextextended(batch::text,5143));
  IF (SELECT count(*) FROM education.device_lessons WHERE group_batch_id=batch)=(SELECT member_count FROM education.school_group_batches WHERE id=batch)
  AND NOT EXISTS(SELECT FROM education.device_lessons a LEFT JOIN education.school_lesson_reviews r ON r.assignment_id=a.id
   WHERE a.group_batch_id=batch AND (r.published_at IS NULL OR a.teacher_id<>p_teacher))
  THEN
   INSERT INTO education.school_point_ledger(learner_id,teacher_id,reason,points,source_id)
   SELECT a.learner_id,p_teacher,'group',20,batch FROM education.device_lessons a WHERE a.group_batch_id=batch
   ON CONFLICT DO NOTHING;
  END IF;
 END IF;
END;
$$;

CREATE FUNCTION education.school_command(p_adult uuid,p_body jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE
 actor text := education.adult_role(p_adult); action_name text := p_body->>'action';
 command_request uuid := (p_body->>'requestId')::uuid;
 fingerprint text := encode(sha256(convert_to(p_body::text,'UTF8')),'hex');
 receipt education.school_command_receipts%ROWTYPE;
 result jsonb; entity uuid; pupil uuid := nullif(p_body->>'learnerId','')::uuid;
 group_row education.school_groups%ROWTYPE;
 helper education.device_lessons%ROWTYPE;
 members uuid[]; member jsonb; batch uuid; assigned jsonb;
 expected integer := coalesce((p_body->>'expectedRevision')::integer,0);
 reminder integer;
BEGIN
 IF actor NOT IN ('teacher','family') OR actor IS NULL THEN RAISE insufficient_privilege; END IF;
 IF command_request IS NULL THEN RAISE invalid_parameter_value; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_adult::text||':'||command_request::text,1843));
 SELECT * INTO receipt FROM education.school_command_receipts WHERE adult_id=p_adult AND request_id=command_request;
 IF FOUND THEN
  IF receipt.request_hash<>fingerprint THEN RAISE unique_violation; END IF;
  RETURN receipt.result;
 END IF;
 IF (SELECT count(*) FROM education.school_command_receipts WHERE adult_id=p_adult AND created_at>clock_timestamp()-interval '1 hour')>=1000
 THEN RAISE EXCEPTION USING ERRCODE='54000',MESSAGE='school_rate_limit'; END IF;

 IF action_name NOT IN ('review-care-alert','save-group','archive-group','assign-group','confirm-help') THEN
  IF action_name='save-settings' AND (p_body ? 'reminderMinutes' OR p_body ? 'familySupportAlertsEnabled') THEN
   IF actor<>'family' THEN RAISE insufficient_privilege; END IF;
  END IF;
  IF action_name='save-settings' AND p_body ? 'reminderMinutes' THEN
   reminder := (p_body->>'reminderMinutes')::integer;
   IF reminder IS NOT NULL AND reminder NOT BETWEEN 5 AND 60 THEN RAISE invalid_parameter_value; END IF;
  END IF;
  result := education.school_command_before_care(p_adult,p_body);
  IF action_name='save-settings' AND p_body ? 'reminderMinutes' THEN
   UPDATE education.school_device_settings SET reminder_minutes=reminder WHERE learner_id=pupil;
  END IF;
  IF action_name='save-settings' AND p_body ? 'familySupportAlertsEnabled' THEN
   UPDATE education.school_device_settings SET family_support_alerts_enabled=(p_body->>'familySupportAlertsEnabled')::boolean,
    family_support_alerts_by=p_adult WHERE learner_id=pupil;
  ELSIF action_name='review-lesson' AND (p_body->>'publish')::boolean THEN
   PERFORM education.award_review_points(p_adult,(p_body->>'assignmentId')::uuid);
  END IF;
  RETURN result;
 END IF;

 CASE action_name
 WHEN 'review-care-alert' THEN
  entity := (p_body->>'alertId')::uuid;
  IF actor<>'family' THEN RAISE insufficient_privilege; END IF;
  SELECT s.learner_id INTO pupil FROM education.school_care_signals s JOIN education.school_care_recipients r ON r.signal_id=s.id
   WHERE s.id=entity AND r.adult_id=p_adult AND education.school_can_view(p_adult,s.learner_id);
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  PERFORM id FROM education.learners WHERE id=pupil FOR SHARE;
  SELECT s.learner_id INTO pupil FROM education.school_care_signals s
  WHERE s.id=entity AND s.created_at>=clock_timestamp()-interval '90 days' AND education.school_can_view(p_adult,s.learner_id) AND EXISTS(SELECT FROM education.school_care_recipients r
   WHERE r.signal_id=s.id AND r.adult_id=p_adult) FOR SHARE;
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  INSERT INTO education.school_care_reviews(signal_id,adult_id,status)
  VALUES(entity,p_adult,p_body->>'status') ON CONFLICT(signal_id,adult_id)
  DO UPDATE SET status=excluded.status,reviewed_at=clock_timestamp();
  result := jsonb_build_object('id',entity,'status',p_body->>'status');

 WHEN 'save-group' THEN
  IF actor<>'teacher' OR NOT EXISTS(SELECT FROM education.classes WHERE id=(p_body->>'classId')::uuid AND teacher_id=p_adult)
  THEN RAISE insufficient_privilege; END IF;
  IF jsonb_typeof(p_body->'members') IS DISTINCT FROM 'array' OR jsonb_array_length(p_body->'members') NOT BETWEEN 2 AND 8
  THEN RAISE invalid_parameter_value; END IF;
  SELECT array_agg(DISTINCT (m->>'learnerId')::uuid) INTO members FROM jsonb_array_elements(p_body->'members')m;
  IF cardinality(members)<>jsonb_array_length(p_body->'members') OR EXISTS(
   SELECT FROM unnest(members)id WHERE NOT EXISTS(SELECT FROM education.learners l
   WHERE l.id=id AND l.class_id=(p_body->>'classId')::uuid)) THEN RAISE no_data_found; END IF;
  entity := nullif(p_body->>'groupId','')::uuid;
  IF entity IS NULL THEN
   INSERT INTO education.school_groups(class_id,teacher_id,name) VALUES((p_body->>'classId')::uuid,p_adult,p_body->>'name')
   RETURNING id,revision INTO entity,expected;
  ELSE
   SELECT * INTO group_row FROM education.school_groups WHERE id=entity AND teacher_id=p_adult AND class_id=(p_body->>'classId')::uuid FOR UPDATE;
   IF NOT FOUND THEN RAISE no_data_found; END IF;
   IF group_row.revision<>expected THEN RAISE serialization_failure; END IF;
   UPDATE education.school_groups SET name=p_body->>'name',revision=revision+1,archived_at=NULL WHERE id=entity RETURNING revision INTO expected;
   DELETE FROM education.school_group_members WHERE group_id=entity;
  END IF;
  FOR member IN SELECT * FROM jsonb_array_elements(p_body->'members') LOOP
   IF member->>'peerRole'='helper' AND coalesce((member->>'voluntary')::boolean,false)=false THEN RAISE invalid_parameter_value; END IF;
   IF member->>'buddyAlias' IS NOT NULL AND member->>'buddyAlias' !~ '^[[:alnum:] _-]{1,16}$' THEN RAISE invalid_parameter_value; END IF;
   INSERT INTO education.school_group_members(group_id,learner_id,peer_role,voluntary,buddy_alias)
   VALUES(entity,(member->>'learnerId')::uuid,member->>'peerRole',(member->>'voluntary')::boolean,nullif(member->>'buddyAlias',''));
  END LOOP;
  result := jsonb_build_object('id',entity,'revision',expected);

 WHEN 'archive-group' THEN
  entity := (p_body->>'groupId')::uuid;
  SELECT g.* INTO group_row FROM education.school_groups g JOIN education.classes c ON c.id=g.class_id
   WHERE g.id=entity AND g.teacher_id=p_adult AND c.teacher_id=p_adult AND actor='teacher' FOR UPDATE OF g;
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  IF group_row.revision<>expected THEN RAISE serialization_failure; END IF;
  UPDATE education.school_groups SET archived_at=clock_timestamp(),revision=revision+1 WHERE id=entity RETURNING revision INTO expected;
  result := jsonb_build_object('id',entity,'revision',expected,'archived',true);

 WHEN 'assign-group' THEN
  entity := (p_body->>'groupId')::uuid;
  SELECT g.* INTO group_row FROM education.school_groups g JOIN education.classes c ON c.id=g.class_id
   WHERE g.id=entity AND g.teacher_id=p_adult AND c.teacher_id=p_adult AND actor='teacher' AND g.archived_at IS NULL FOR SHARE OF g;
  IF NOT FOUND THEN RAISE no_data_found; END IF;
  IF (SELECT count(*) FROM education.school_group_members WHERE group_id=entity) NOT BETWEEN 2 AND 8
  OR EXISTS(SELECT FROM education.school_group_members m JOIN education.learners l ON l.id=m.learner_id WHERE m.group_id=entity AND l.class_id<>group_row.class_id)
  THEN RAISE invalid_parameter_value; END IF;
  -- Reuse the existing validated activity contract without generating a second receipt.
  IF p_body->>'subject' IS DISTINCT FROM 'matematicas' OR jsonb_typeof(p_body->'factors') IS DISTINCT FROM 'array'
   OR jsonb_array_length(p_body->'factors') NOT BETWEEN 1 AND 5 OR EXISTS(SELECT FROM jsonb_array_elements(p_body->'factors')f
    WHERE jsonb_typeof(f) IS DISTINCT FROM 'array' OR jsonb_array_length(f)<>2 OR (f->>0)::integer NOT BETWEEN 1 AND 12 OR (f->>1)::integer NOT BETWEEN 1 AND 12)
  THEN RAISE invalid_parameter_value; END IF;
  INSERT INTO education.school_group_batches(group_id,teacher_id,member_count)
   SELECT entity,p_adult,count(*) FROM education.school_group_members WHERE group_id=entity RETURNING id INTO batch;
  WITH inserted AS (
   INSERT INTO education.device_lessons(teacher_id,learner_id,title,subject,goal,instructions,due_at,factors,
    group_id,group_batch_id,peer_role,helper_voluntary,child_buddy_alias)
   SELECT p_adult,m.learner_id,p_body->>'title','matematicas',p_body->>'goal',p_body->>'instructions',(p_body->>'dueAt')::date,p_body->'factors',
    entity,batch,m.peer_role,m.voluntary,(SELECT buddy_alias FROM education.school_group_members buddy
      WHERE buddy.group_id=entity AND buddy.learner_id<>m.learner_id AND buddy.peer_role='helper' AND buddy.voluntary AND buddy.buddy_alias IS NOT NULL ORDER BY buddy.learner_id LIMIT 1)
   FROM education.school_group_members m WHERE m.group_id=entity RETURNING id,lesson_id,learner_id
  ) SELECT jsonb_agg(jsonb_build_object('id',id,'lessonId',lesson_id,'learnerId',learner_id)) INTO assigned FROM inserted;
  result := jsonb_build_object('groupId',entity,'groupBatchId',batch,'assigned',jsonb_array_length(assigned),'assignments',assigned);

 WHEN 'confirm-help' THEN
  entity := (p_body->>'assignmentId')::uuid; pupil := (p_body->>'helpedLearnerId')::uuid;
  SELECT a.* INTO helper FROM education.device_lessons a JOIN education.school_lesson_reviews r ON r.assignment_id=a.id AND r.published_at IS NOT NULL
   WHERE a.id=entity AND a.teacher_id=p_adult AND actor='teacher' AND education.school_owns(p_adult,a.learner_id)
    AND a.peer_role='helper' AND a.helper_voluntary AND a.group_batch_id IS NOT NULL FOR SHARE OF a;
  IF NOT FOUND OR helper.learner_id=pupil OR NOT EXISTS(SELECT FROM education.device_lessons a
   JOIN education.school_lesson_reviews r ON r.assignment_id=a.id AND r.published_at IS NOT NULL
   WHERE a.group_batch_id=helper.group_batch_id AND a.learner_id=pupil AND a.teacher_id=p_adult AND education.school_owns(p_adult,a.learner_id))
  THEN RAISE no_data_found; END IF;
  INSERT INTO education.school_help_confirmations(assignment_id,helped_learner_id,teacher_id)
  VALUES(entity,pupil,p_adult) ON CONFLICT DO NOTHING;
  INSERT INTO education.school_point_ledger(learner_id,teacher_id,reason,points,source_id)
  VALUES(helper.learner_id,p_adult,'help',5,entity) ON CONFLICT DO NOTHING;
  result := jsonb_build_object('assignmentId',entity,'confirmed',true);
 ELSE RAISE invalid_parameter_value;
 END CASE;

 -- Care reviews deliberately avoid the general school audit and teacher-owned records.
 IF action_name<>'review-care-alert' THEN
  INSERT INTO education.school_audit(adult_id,action,entity_id,learner_id) VALUES(p_adult,action_name,entity,pupil);
 END IF;
 INSERT INTO education.school_command_receipts(adult_id,request_id,request_hash,result) VALUES(p_adult,command_request,fingerprint,result);
 RETURN result;
END;
$$;

CREATE FUNCTION education.device_school_context(p_learner uuid,p_teacher uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT jsonb_set(jsonb_set(education.device_school_context_before_care(p_learner,p_teacher),'{deviceSettings,reminderMinutes}',
  coalesce(to_jsonb(CASE WHEN s.learner_id IS NULL THEN 10 ELSE s.reminder_minutes END),'null'::jsonb)),
  '{deviceSettings,familySupportAlertsEnabled}',to_jsonb(education.family_support_enabled(l.id)))
  ||jsonb_build_object('collaborationPoints',coalesce((SELECT sum(points) FROM education.school_point_ledger WHERE learner_id=l.id),0))
 FROM education.learners l JOIN education.classes c ON c.id=l.class_id
 LEFT JOIN education.school_device_settings s ON s.learner_id=l.id WHERE l.id=p_learner AND c.teacher_id=p_teacher;
$$;
-- Group metadata remains optional and contains only the explicitly supplied buddy alias.
CREATE FUNCTION education.device_group_context(p_assignment uuid,p_learner uuid,p_teacher uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT CASE WHEN a.group_id IS NOT NULL THEN jsonb_strip_nulls(jsonb_build_object(
 'groupId',a.group_id,'groupBatchId',a.group_batch_id,'peerRole',a.peer_role,'childBuddyAlias',a.child_buddy_alias)) ELSE '{}'::jsonb END
 FROM education.device_lessons a JOIN education.learners l ON l.id=a.learner_id JOIN education.classes c ON c.id=l.class_id
 WHERE a.id=p_assignment AND a.learner_id=p_learner AND a.teacher_id=p_teacher AND c.teacher_id=p_teacher; $$;

CREATE OR REPLACE FUNCTION education.school_read(p_adult uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ DECLARE snapshot jsonb; BEGIN
 IF education.adult_role(p_adult) IS NULL THEN RETURN NULL; END IF;
 PERFORM education.cleanup_care_signals();
 snapshot := education.school_snapshot(p_adult);
 IF snapshot IS NOT NULL THEN INSERT INTO education.school_audit(adult_id,action,details)
 VALUES(p_adult,'school-read',jsonb_build_object('scope','authorized_school_records')); END IF;
 RETURN snapshot;
END; $$;
CREATE OR REPLACE FUNCTION education.export_learning_data(p_adult uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
AS $$ SELECT CASE WHEN education.adult_role(p_adult) IS NOT NULL THEN
 coalesce(education.export_learning_data_base(p_adult),'{}'::jsonb)||jsonb_build_object('school',education.school_snapshot(p_adult),
 'collaboration',jsonb_build_object('groupBatches',coalesce((SELECT jsonb_agg(jsonb_build_object('id',b.id,'groupId',b.group_id,
   'memberCount',b.member_count,'createdAt',b.created_at)) FROM education.school_group_batches b
   WHERE EXISTS(SELECT FROM education.device_lessons a WHERE a.group_batch_id=b.id AND education.school_can_view(p_adult,a.learner_id))),'[]'::jsonb),
  'confirmedHelp',coalesce((SELECT jsonb_agg(CASE WHEN education.adult_role(p_adult)='teacher' THEN
   jsonb_build_object('assignmentId',h.assignment_id,'helpedLearnerId',h.helped_learner_id,'confirmedAt',h.confirmed_at)
   ELSE jsonb_build_object('assignmentId',CASE WHEN education.school_can_view(p_adult,a.learner_id) THEN a.id END,
    'ownLearnerId',CASE WHEN education.school_can_view(p_adult,a.learner_id) THEN a.learner_id ELSE h.helped_learner_id END,
    'role',CASE WHEN education.school_can_view(p_adult,a.learner_id) THEN 'helper' ELSE 'helped' END,'confirmedAt',h.confirmed_at) END)
   FROM education.school_help_confirmations h JOIN education.device_lessons a ON a.id=h.assignment_id
   WHERE education.school_can_view(p_adult,a.learner_id) OR education.school_can_view(p_adult,h.helped_learner_id)),'[]'::jsonb))) END; $$;

ALTER FUNCTION education.reset_learning_data(uuid,text,uuid) RENAME TO reset_learning_data_before_care;
CREATE FUNCTION education.reset_learning_data(p_adult uuid,p_confirmation text,p_request uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$ DECLARE result jsonb; BEGIN
 IF education.adult_role(p_adult) IS NULL THEN RAISE insufficient_privilege; END IF;
 result := education.reset_learning_data_before_care(p_adult,p_confirmation,p_request);
 IF result IS NOT NULL THEN
  DELETE FROM education.school_care_recipients WHERE adult_id=p_adult;
  UPDATE education.school_device_settings SET family_support_alerts_enabled=false,family_support_alerts_by=NULL,
   revision=revision+1,updated_at=clock_timestamp() WHERE family_support_alerts_by=p_adult;
 END IF;
 RETURN result;
END; $$;

REVOKE ALL ON FUNCTION education.school_snapshot_before_care(uuid),education.school_command_before_care(uuid,jsonb),
 education.device_school_context_before_care(uuid,uuid),education.award_review_points(uuid,uuid),education.family_support_enabled(uuid),
 education.reset_learning_data_before_care(uuid,text,uuid),education.cleanup_care_signals(),education.remove_orphan_care_signal()
 FROM PUBLIC,anon,authenticated,peluqo_backend;
REVOKE ALL ON FUNCTION education.school_snapshot(uuid),education.school_command(uuid,jsonb),
 education.device_school_context(uuid,uuid),education.device_group_context(uuid,uuid,uuid),
 education.ingest_support_signal(uuid,uuid,text,text,boolean,boolean),education.reset_learning_data(uuid,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION education.school_snapshot(uuid),education.school_command(uuid,jsonb),
 education.device_school_context(uuid,uuid),education.device_group_context(uuid,uuid,uuid),
 education.ingest_support_signal(uuid,uuid,text,text,boolean,boolean),education.reset_learning_data(uuid,text,uuid) TO peluqo_backend;
COMMIT;
