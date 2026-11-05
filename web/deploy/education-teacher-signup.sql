CREATE FUNCTION education.register_teacher_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO education.teachers (id)
  VALUES (NEW.id)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION education.register_teacher_profile() FROM PUBLIC, anon, authenticated;

CREATE TRIGGER register_peluqo_teacher
AFTER INSERT ON public.profiles
FOR EACH ROW
WHEN (NEW.account_type = 'teacher' AND NEW.age_band = '18+')
EXECUTE FUNCTION education.register_teacher_profile();

INSERT INTO education.teachers (id)
SELECT id FROM public.profiles WHERE account_type = 'teacher' AND age_band = '18+'
ON CONFLICT (id) DO NOTHING;
