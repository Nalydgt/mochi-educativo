CREATE TABLE education.account_invitations (
  code_hash text PRIMARY KEY CHECK (code_hash ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz NOT NULL,
  used_at timestamptz
);

ALTER TABLE education.account_invitations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.account_invitations FROM PUBLIC, anon, authenticated;

CREATE FUNCTION public.peluqo_account_invitation_available(p_hash text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT FROM education.account_invitations
    WHERE code_hash = p_hash AND used_at IS NULL AND expires_at > now()
  );
$$;

REVOKE EXECUTE ON FUNCTION public.peluqo_account_invitation_available(text)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.peluqo_account_invitation_available(text) TO service_role;

-- Consume the invitation in the Auth transaction that creates the user.
CREATE FUNCTION education.consume_account_invitation()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  UPDATE education.account_invitations
  SET used_at = clock_timestamp()
  WHERE code_hash = NEW.raw_app_meta_data->>'peluqo_invitation_hash'
    AND used_at IS NULL AND expires_at > clock_timestamp();
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Invalid or expired Peluqo account invitation';
  END IF;
  NEW.raw_app_meta_data = NEW.raw_app_meta_data - 'peluqo_invitation_hash';
  RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION education.consume_account_invitation() FROM PUBLIC, anon, authenticated;

CREATE TRIGGER consume_peluqo_account_invitation
BEFORE INSERT ON auth.users
FOR EACH ROW
WHEN (NEW.raw_app_meta_data ? 'peluqo_invitation_hash')
EXECUTE FUNCTION education.consume_account_invitation();
