ALTER TABLE education.access_codes
  ALTER COLUMN expires_at DROP NOT NULL,
  ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN issued_by uuid,
  ADD COLUMN reusable boolean NOT NULL DEFAULT false,
  ADD COLUMN state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused', 'revoked'));

CREATE INDEX student_access_codes_recent ON education.access_codes (learner_id, created_at DESC, hash);

-- This private projection deliberately omits the credential hash.
CREATE FUNCTION education.student_access_state(p_learner uuid)
RETURNS jsonb
LANGUAGE sql STABLE SET search_path = ''
AS $$
  SELECT COALESCE((
    SELECT jsonb_build_object(
      'status', CASE
        WHEN c.state = 'revoked' THEN 'revoked'
        WHEN c.expires_at <= now() THEN 'expired'
        WHEN NOT c.reusable AND c.consumed_at IS NOT NULL THEN 'used'
        ELSE c.state
      END,
      'expiresAt', c.expires_at,
      'createdAt', c.created_at
    )
    FROM education.access_codes c WHERE c.learner_id = p_learner
    ORDER BY c.created_at DESC, c.hash LIMIT 1
  ), jsonb_build_object('status', 'none', 'expiresAt', NULL, 'createdAt', NULL));
$$;

-- Only the application backend passes a verified adult ID. Scope is checked again here.
CREATE FUNCTION education.manage_student_access(
  p_adult uuid, p_learner uuid, p_action text, p_hash text DEFAULT NULL,
  p_expires_at timestamptz DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  access_hash text;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('status', 'issue', 'issue-legacy', 'pause', 'enable', 'revoke') THEN
    RETURN NULL;
  END IF;

  -- Family-link changes lock the same learner row before editing the relationship.
  PERFORM l.id FROM education.learners l WHERE l.id = p_learner FOR UPDATE;
  IF NOT FOUND OR NOT EXISTS (
    SELECT FROM education.learners l JOIN education.classes c ON c.id = l.class_id
    WHERE l.id = p_learner AND (
      c.teacher_id = p_adult OR (p_action <> 'issue-legacy' AND EXISTS (
        SELECT FROM education.family_links link JOIN public.profiles profile ON profile.id = link.guardian_id
        WHERE link.learner_id = l.id AND link.guardian_id = p_adult
          AND profile.account_type = 'family' AND profile.age_band = '18+'
      ))
    )
  ) THEN RETURN NULL; END IF;

  IF p_action = 'status' THEN RETURN education.student_access_state(p_learner); END IF;

  IF p_action IN ('issue', 'issue-legacy') THEN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR (p_expires_at IS NOT NULL AND (NOT isfinite(p_expires_at) OR p_expires_at <= clock_timestamp()))
       OR (p_action = 'issue-legacy' AND p_expires_at IS NULL) THEN RETURN NULL; END IF;
    UPDATE education.access_codes SET state = 'revoked'
    WHERE learner_id = p_learner AND state <> 'revoked';
    INSERT INTO education.access_codes (hash, learner_id, expires_at, reusable, created_at, issued_by)
    VALUES (p_hash, p_learner, p_expires_at, p_action = 'issue', clock_timestamp(), p_adult);
  ELSE
    SELECT c.hash INTO access_hash FROM education.access_codes c WHERE c.learner_id = p_learner
    ORDER BY c.created_at DESC, c.hash LIMIT 1;

    IF p_action = 'enable' THEN
      UPDATE education.access_codes SET state = 'active'
      WHERE hash = access_hash AND state = 'paused' AND (reusable OR consumed_at IS NULL)
        AND (expires_at IS NULL OR expires_at > clock_timestamp());
      RETURN education.student_access_state(p_learner);
    END IF;

    IF p_action = 'pause' THEN
      UPDATE education.access_codes SET state = 'paused' WHERE hash = access_hash AND state = 'active';
    ELSE
      UPDATE education.access_codes SET state = 'revoked' WHERE hash = access_hash AND state <> 'revoked';
    END IF;
  END IF;

  UPDATE education.logins SET revoked = true WHERE learner_id = p_learner AND NOT revoked;
  UPDATE education.devices SET session_id = NULL, ack = 0
  WHERE learner_id = p_learner AND session_id IS NOT NULL;
  RETURN education.student_access_state(p_learner);
END;
$$;

CREATE FUNCTION education.open_student_login(p_hash text, p_login_hash text, p_remember boolean, p_expected_learner uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  target uuid;
  limit_at timestamptz;
  valid_until timestamptz;
BEGIN
  IF p_login_hash IS NULL OR p_login_hash !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
  SELECT c.learner_id INTO target FROM education.access_codes c WHERE c.hash = p_hash;
  IF target IS NULL OR (p_expected_learner IS NOT NULL AND p_expected_learner <> target) THEN
    RETURN NULL;
  END IF;
  PERFORM id FROM education.learners WHERE id = target FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;

  UPDATE education.access_codes SET consumed_at = COALESCE(consumed_at, clock_timestamp())
  WHERE hash = p_hash AND learner_id = target AND state = 'active'
    AND (reusable OR consumed_at IS NULL)
    AND (expires_at IS NULL OR expires_at > clock_timestamp())
  RETURNING expires_at INTO limit_at;
  IF NOT FOUND THEN RETURN NULL; END IF;

  -- Keep the existing ownership model: one live login per learner, with mission continuity.
  valid_until := LEAST(
    clock_timestamp() + CASE WHEN p_remember THEN interval '720 hours' ELSE interval '8 hours' END,
    CASE WHEN EXISTS (SELECT FROM education.access_codes WHERE hash = p_hash AND reusable) THEN limit_at END
  );
  UPDATE education.logins SET revoked = true WHERE learner_id = target AND NOT revoked;
  INSERT INTO education.logins (hash, learner_id, expires_at) VALUES (p_login_hash, target, valid_until);
  UPDATE education.devices SET session_id = NULL, ack = 0
  WHERE learner_id = target AND session_id IS NOT NULL;
  UPDATE education.sessions SET login_hash = p_login_hash WHERE learner_id = target;
  RETURN (
    SELECT jsonb_build_object(
      'profile', jsonb_build_object('id', l.id, 'name', split_part(btrim(l.name), ' ', 1), 'color', l.companion->>'color'),
      'expiresAt', valid_until
    ) FROM education.learners l WHERE l.id = target
  );
END;
$$;

-- A former guardian must not retain a code they created while linked.
CREATE FUNCTION education.close_former_guardian_access()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  UPDATE education.access_codes SET state = 'revoked'
  WHERE learner_id = OLD.learner_id AND issued_by = OLD.guardian_id AND state <> 'revoked';
  IF FOUND THEN
    UPDATE education.logins SET revoked = true WHERE learner_id = OLD.learner_id AND NOT revoked;
    UPDATE education.devices SET session_id = NULL, ack = 0
    WHERE learner_id = OLD.learner_id AND session_id IS NOT NULL;
  END IF;
  RETURN OLD;
END;
$$;

CREATE TRIGGER close_former_guardian_access AFTER DELETE ON education.family_links
FOR EACH ROW EXECUTE FUNCTION education.close_former_guardian_access();

REVOKE EXECUTE ON FUNCTION education.student_access_state(uuid),
  education.manage_student_access(uuid, uuid, text, text, timestamptz),
  education.open_student_login(text, text, boolean, uuid), education.close_former_guardian_access()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.manage_student_access(uuid, uuid, text, text, timestamptz),
  education.open_student_login(text, text, boolean, uuid) TO peluqo_backend;
