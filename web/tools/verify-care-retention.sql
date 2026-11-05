-- Database-owner acceptance test. Fictional classroom/incident records exist only inside this rollback.
BEGIN;
DO $test$
DECLARE
 v_teacher uuid; v_family uuid; v_class uuid; v_pupil uuid; v_device uuid;
 v_signal uuid:=gen_random_uuid(); v_orphan uuid:=gen_random_uuid();
 v_hash text:=encode(sha256(convert_to(gen_random_uuid()::text,'UTF8')),'hex');
 v_data jsonb;
BEGIN
 SELECT t.id INTO v_teacher FROM education.teachers t JOIN auth.users u ON u.id=t.id
 WHERE education.adult_role(t.id)='teacher' LIMIT 1;
 SELECT p.id INTO v_family FROM public.profiles p JOIN auth.users u ON u.id=p.id
 WHERE education.adult_role(p.id)='family' AND p.account_type='family' LIMIT 1;
 IF v_teacher IS NULL OR v_family IS NULL THEN RAISE EXCEPTION 'Fictional adult fixtures unavailable'; END IF;
 INSERT INTO education.classes(teacher_id,name) VALUES(v_teacher,'Rollback care retention') RETURNING id INTO v_class;
 INSERT INTO education.learners(class_id,name) VALUES(v_class,'Prueba Retención') RETURNING id INTO v_pupil;
 INSERT INTO education.devices(teacher_id,learner_id,token_hash) VALUES(v_teacher,v_pupil,v_hash) RETURNING id INTO v_device;
 IF NOT education.issue_family_code(v_teacher,v_pupil,v_hash) OR NOT education.redeem_family_code(v_family,v_hash)
 THEN RAISE EXCEPTION 'Fixture family link failed'; END IF;
 PERFORM education.school_command(v_family,jsonb_build_object('action','save-settings','requestId',gen_random_uuid(),
  'learnerId',v_pupil,'dailyMinutes',30,'startTime','08:00','endTime','20:00','timezone','Europe/Madrid','language','es',
  'voiceEnabled',true,'captionsEnabled',true,'textFirst',false,'sharePractice',false,'reminderMinutes',10,
  'familySupportAlertsEnabled',true,'expectedRevision',0));
 v_data:=education.ingest_support_signal(v_device,v_signal,'possible_peer_bullying','daily_voice',true,true);
 IF v_data->>'visibleToFamily' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'No visible recipient acknowledgement'; END IF;
 UPDATE education.school_care_signals SET created_at=clock_timestamp()-interval '91 days' WHERE id=v_signal;
 v_data:=education.ingest_support_signal(v_device,v_signal,'possible_peer_bullying','daily_voice',true,true);
 IF v_data->>'visibleToFamily' IS DISTINCT FROM 'false' THEN RAISE EXCEPTION 'Expired alert falsely acknowledged as visible'; END IF;
 IF EXISTS(SELECT FROM jsonb_array_elements(education.school_snapshot(v_family)->'careAlerts') a WHERE a->>'id'=v_signal::text)
 THEN RAISE EXCEPTION 'Expired alert visible before maintenance'; END IF;
 v_data:=education.school_read(v_teacher);
 IF v_data ? 'careAlerts' THEN RAISE EXCEPTION 'Teacher read exposes care field'; END IF;
 IF EXISTS(SELECT FROM education.school_care_signals WHERE id=v_signal)
 OR EXISTS(SELECT FROM education.school_care_recipients WHERE signal_id=v_signal)
 THEN RAISE EXCEPTION 'Ninety-day cleanup did not remove alert and recipient'; END IF;
 PERFORM education.ingest_support_signal(v_device,v_orphan,'possible_peer_bullying','lesson_voice',true,true);
 DELETE FROM education.school_care_recipients WHERE signal_id=v_orphan AND adult_id=v_family;
 IF EXISTS(SELECT FROM education.school_care_signals WHERE id=v_orphan)
 THEN RAISE EXCEPTION 'Last recipient deletion retained orphan incident'; END IF;
 IF NOT EXISTS(SELECT FROM pg_constraint c WHERE c.conrelid='education.school_care_recipients'::regclass
 AND c.confrelid='auth.users'::regclass AND c.contype='f' AND c.confdeltype='c')
 THEN RAISE EXCEPTION 'Auth deletion does not cascade recipients'; END IF;
END;
$test$;
ROLLBACK;
SELECT true AS passed,'90-day visibility and retention, private teacher maintenance, orphan cleanup and Auth cascade; all fictional rows rolled back' AS verification;
