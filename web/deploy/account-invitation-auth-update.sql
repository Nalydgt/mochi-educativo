-- Supabase Auth adds app metadata in an update inside the user creation transaction.
CREATE OR REPLACE TRIGGER consume_peluqo_account_invitation
BEFORE INSERT OR UPDATE OF raw_app_meta_data ON auth.users
FOR EACH ROW
WHEN (NEW.raw_app_meta_data ? 'peluqo_invitation_hash')
EXECUTE FUNCTION education.consume_account_invitation();
