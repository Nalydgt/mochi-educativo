-- Text follows the same consent, family recipients and retention as voice.
BEGIN;
ALTER TABLE education.school_care_signals DROP CONSTRAINT school_care_signals_source_check;
ALTER TABLE education.school_care_signals ADD CONSTRAINT school_care_signals_source_check
 CHECK (source IN ('daily_voice','lesson_voice','daily_text','lesson_text'));
CREATE OR REPLACE FUNCTION education.ingest_support_signal(p_device uuid,p_signal uuid,p_category text,p_source text,p_school_peers boolean,p_child_confirmed boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
AS $$
DECLARE pupil uuid; prior education.school_care_signals%ROWTYPE;
BEGIN
 IF p_signal IS NULL OR p_category IS DISTINCT FROM 'possible_peer_bullying'
 OR p_source NOT IN ('daily_voice','lesson_voice','daily_text','lesson_text') OR p_source IS NULL OR p_school_peers IS DISTINCT FROM true
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


COMMIT;
