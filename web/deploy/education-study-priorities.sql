CREATE TABLE education.study_priorities (
  adult_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  subject text CHECK (subject IN ('ciencias','matematicas','lengua','historia','geografia','otros')),
  goal text NOT NULL CHECK (goal IN ('balanced','support','stretch')),
  PRIMARY KEY (adult_id, learner_id)
);
CREATE INDEX study_priorities_learner ON education.study_priorities (learner_id);
ALTER TABLE education.study_priorities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.study_priorities FROM PUBLIC, anon, authenticated, peluqo_backend;

CREATE FUNCTION education.can_set_study_priority(p_adult uuid, p_learner uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT FROM education.learners l JOIN education.classes c ON c.id = l.class_id
    JOIN public.profiles p ON p.id = p_adult AND p.age_band = '18+'
    WHERE l.id = p_learner AND (
      (p.account_type = 'teacher' AND c.teacher_id = p.id)
      OR (p.account_type = 'family' AND EXISTS (
        SELECT FROM education.family_links f WHERE f.guardian_id = p.id AND f.learner_id = l.id
      ))
    )
  );
$$;

CREATE FUNCTION education.manage_study_priority(p_adult uuid, p_learner uuid, p_subject text, p_goal text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  IF p_goal IS NOT NULL THEN
    PERFORM id FROM education.learners WHERE id = p_learner FOR UPDATE;
  END IF;
  IF NOT education.can_set_study_priority(p_adult, p_learner) THEN RETURN NULL; END IF;
  IF p_goal IS NOT NULL THEN
    INSERT INTO education.study_priorities (adult_id, learner_id, subject, goal)
    VALUES (p_adult, p_learner, p_subject, p_goal)
    ON CONFLICT (adult_id, learner_id) DO UPDATE SET subject = excluded.subject, goal = excluded.goal;
  END IF;
  RETURN coalesce((
    SELECT jsonb_build_object('subject', subject, 'goal', goal)
    FROM education.study_priorities WHERE adult_id = p_adult AND learner_id = p_learner
  ), '{"subject":null,"goal":"balanced"}'::jsonb);
END;
$$;

CREATE FUNCTION education.student_study_priorities(p_login text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  SELECT coalesce(jsonb_agg(jsonb_build_object('subject', p.subject, 'goal', p.goal)), '[]'::jsonb)
  FROM education.logins g JOIN education.study_priorities p ON p.learner_id = g.learner_id
  WHERE g.hash = p_login AND NOT g.revoked AND g.expires_at > now()
    AND education.can_set_study_priority(p.adult_id, p.learner_id);
$$;

CREATE FUNCTION education.remove_former_guardian_priority()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  DELETE FROM education.study_priorities WHERE adult_id = OLD.guardian_id AND learner_id = OLD.learner_id;
  RETURN OLD;
END;
$$;
CREATE TRIGGER remove_former_guardian_priority AFTER DELETE ON education.family_links
FOR EACH ROW EXECUTE FUNCTION education.remove_former_guardian_priority();

REVOKE EXECUTE ON FUNCTION education.can_set_study_priority(uuid, uuid),
  education.manage_study_priority(uuid, uuid, text, text), education.student_study_priorities(text),
  education.remove_former_guardian_priority() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.manage_study_priority(uuid, uuid, text, text),
  education.student_study_priorities(text) TO peluqo_backend;
