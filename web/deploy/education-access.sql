-- Only the server's scoped login can reach this private schema. Request
-- identity is set transaction-locally after Auth/cookie/integration validation.
GRANT USAGE ON SCHEMA education TO peluqo_backend;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA education TO peluqo_backend;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA education TO peluqo_backend;
REVOKE INSERT,UPDATE,DELETE ON education.teachers FROM peluqo_backend;

CREATE FUNCTION education.request_value(key text) RETURNS text
LANGUAGE sql STABLE SET search_path = '' AS $$
 SELECT nullif(current_setting('peluqo.' || key, true), '');
$$;
REVOKE ALL ON FUNCTION education.request_value(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION education.request_value(text) TO peluqo_backend;

CREATE POLICY teacher_identity ON education.teachers TO peluqo_backend
USING (id::text = education.request_value('teacher'));
CREATE POLICY class_access ON education.classes TO peluqo_backend
USING (teacher_id::text = education.request_value('teacher') OR id::text = education.request_value('class') OR education.request_value('service') = 'true')
WITH CHECK (teacher_id::text = education.request_value('teacher') OR education.request_value('service') = 'true');
CREATE POLICY learner_access ON education.learners TO peluqo_backend
USING (id::text = education.request_value('learner') OR class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher')) OR education.request_value('service') = 'true')
WITH CHECK (id::text = education.request_value('learner') OR class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher')) OR education.request_value('service') = 'true');
CREATE POLICY code_access ON education.access_codes TO peluqo_backend
USING (hash = education.request_value('code') OR learner_id IN (SELECT id FROM education.learners WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))))
WITH CHECK (hash = education.request_value('code') OR learner_id IN (SELECT id FROM education.learners WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))));
CREATE POLICY login_access ON education.logins TO peluqo_backend
USING (hash = education.request_value('login') OR learner_id IN (SELECT id FROM education.learners WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))) OR education.request_value('service') = 'true')
WITH CHECK (learner_id::text = education.request_value('learner') OR learner_id IN (SELECT id FROM education.learners WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))) OR education.request_value('service') = 'true');
CREATE POLICY document_access ON education.documents TO peluqo_backend
USING (class_id IN (SELECT id FROM education.classes))
WITH CHECK (class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher')));
CREATE POLICY chunk_access ON education.chunks TO peluqo_backend
USING (document_id IN (SELECT id FROM education.documents))
WITH CHECK (document_id IN (SELECT id FROM education.documents WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))));
CREATE POLICY version_access ON education.versions TO peluqo_backend
USING (class_id IN (SELECT id FROM education.classes))
WITH CHECK (class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher')));
CREATE POLICY session_access ON education.sessions TO peluqo_backend
USING ((learner_id::text = education.request_value('learner') AND (login_hash = education.request_value('login') OR education.request_value('code') IS NOT NULL)) OR learner_id IN (SELECT id FROM education.learners WHERE class_id IN (SELECT id FROM education.classes WHERE teacher_id::text = education.request_value('teacher'))) OR education.request_value('service') = 'true')
WITH CHECK ((learner_id::text = education.request_value('learner') AND login_hash = education.request_value('login')) OR education.request_value('service') = 'true');
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['attempts','hints','turns','events'] LOOP
  EXECUTE format('CREATE POLICY session_access ON education.%I TO peluqo_backend USING (session_id IN (SELECT id FROM education.sessions)) WITH CHECK (session_id IN (SELECT id FROM education.sessions))', t);
 END LOOP;
END $$;
CREATE POLICY device_access ON education.devices TO peluqo_backend
USING (teacher_id::text = education.request_value('teacher') OR learner_id::text = education.request_value('learner') OR education.request_value('service') = 'true')
WITH CHECK (teacher_id::text = education.request_value('teacher') OR (learner_id::text = education.request_value('learner') AND teacher_id IN (SELECT teacher_id FROM education.classes WHERE id::text = education.request_value('class'))) OR education.request_value('service') = 'true');
CREATE POLICY pairing_access ON education.pairings TO peluqo_backend
USING (education.request_value('teacher') IS NOT NULL OR education.request_value('service') = 'true')
WITH CHECK (education.request_value('teacher') IS NOT NULL OR education.request_value('service') = 'true');
CREATE POLICY rate_limit_access ON education.throttle TO peluqo_backend USING (true) WITH CHECK (true);

REVOKE UPDATE,DELETE ON education.versions,education.attempts,education.turns,education.events FROM peluqo_backend;
