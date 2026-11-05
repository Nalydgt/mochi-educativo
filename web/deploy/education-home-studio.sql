CREATE TABLE education.home_accounts (
  family_id uuid PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
  teacher_id uuid NOT NULL UNIQUE REFERENCES education.teachers(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (family_id <> teacher_id)
);
ALTER TABLE education.home_accounts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.home_accounts FROM PUBLIC, anon, authenticated, peluqo_backend;

-- Home spaces reuse the class publisher under an internal, non-authenticating principal.
CREATE FUNCTION education.enable_home_studio(p_adult uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  owner_id uuid;
BEGIN
  PERFORM id FROM public.profiles
  WHERE id = p_adult AND account_type = 'family' AND age_band = '18+' FOR UPDATE;
  IF NOT FOUND THEN RETURN false; END IF;
  IF EXISTS (SELECT FROM education.home_accounts WHERE family_id = p_adult) THEN RETURN true; END IF;

  INSERT INTO education.teachers (id) VALUES (gen_random_uuid()) RETURNING id INTO owner_id;
  INSERT INTO education.home_accounts (family_id, teacher_id) VALUES (p_adult, owner_id);
  INSERT INTO education.classes (teacher_id, name) VALUES (owner_id, 'Estudio en casa');
  RETURN true;
END;
$$;

CREATE FUNCTION education.resolve_home_studio(p_adult uuid)
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
  SELECT h.teacher_id FROM education.home_accounts h JOIN public.profiles p ON p.id = h.family_id
  WHERE h.family_id = p_adult AND p.account_type = 'family' AND p.age_band = '18+';
$$;

CREATE FUNCTION education.link_home_learner()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  INSERT INTO education.family_links (guardian_id, learner_id)
  SELECT h.family_id, NEW.id
  FROM education.classes c JOIN education.home_accounts h ON h.teacher_id = c.teacher_id
  WHERE c.id = NEW.class_id;
  RETURN NEW;
END;
$$;

CREATE TRIGGER link_home_learner AFTER INSERT ON education.learners
FOR EACH ROW EXECUTE FUNCTION education.link_home_learner();

REVOKE EXECUTE ON FUNCTION education.enable_home_studio(uuid),
  education.resolve_home_studio(uuid), education.link_home_learner()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.enable_home_studio(uuid),
  education.resolve_home_studio(uuid) TO peluqo_backend;
