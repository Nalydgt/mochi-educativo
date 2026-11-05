-- Use the existing private rate counters and single-use Auth invitations.
CREATE FUNCTION education.issue_signup_invite(p_hash text, p_client text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  bucket record;
  attempts integer;
BEGIN
  IF p_hash !~ '^[0-9a-f]{64}$' OR p_client !~ '^[0-9a-f]{64}$' THEN
    RETURN false;
  END IF;

  FOR bucket IN
    SELECT * FROM (VALUES
      ('signup:' || p_client, 8),
      ('signup-global', 60)
    ) AS limits(key, maximum)
  LOOP
    INSERT INTO education.throttle AS rate (key, count)
    VALUES (bucket.key, 1)
    ON CONFLICT (key) DO UPDATE
      SET count = CASE WHEN rate.window_start <= now() - interval '10 minutes'
                       THEN 1 ELSE least(rate.count + 1, bucket.maximum + 1) END,
          window_start = CASE WHEN rate.window_start <= now() - interval '10 minutes'
                              THEN now() ELSE rate.window_start END
    RETURNING count INTO attempts;
    IF attempts > bucket.maximum THEN
      RETURN false;
    END IF;
  END LOOP;

  INSERT INTO education.account_invitations (code_hash, expires_at)
  VALUES (p_hash, now() + interval '2 minutes');
  RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION education.issue_signup_invite(text, text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION education.issue_signup_invite(text, text) TO peluqo_backend;

CREATE FUNCTION public.peluqo_pending_account_id(p_email text)
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT u.id
  FROM auth.users AS u
  JOIN public.profiles AS profile ON profile.id = u.id
  WHERE lower(u.email) = lower(p_email)
    AND u.aud = 'authenticated'
    AND u.email_confirmed_at IS NULL
    AND u.deleted_at IS NULL
    AND NOT u.is_sso_user;
$$;

REVOKE EXECUTE ON FUNCTION public.peluqo_pending_account_id(text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.peluqo_pending_account_id(text) TO service_role;
