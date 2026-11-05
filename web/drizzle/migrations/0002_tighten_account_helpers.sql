REVOKE EXECUTE ON FUNCTION public.create_account_profile() FROM PUBLIC,anon,authenticated;
REVOKE EXECUTE ON FUNCTION public.reserve_tutor_request(uuid) FROM anon,authenticated;
REVOKE EXECUTE ON FUNCTION public.evaluate_activity(uuid,uuid,jsonb) FROM anon;
REVOKE EXECUTE ON FUNCTION public.has_role(uuid,public.app_role) FROM anon;
REVOKE EXECUTE ON FUNCTION public.validate_active_learner() FROM PUBLIC,anon,authenticated;
CREATE FUNCTION public.guard_account_type() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ BEGIN IF NEW.account_type='family' AND NEW.id=auth.uid() AND NOT EXISTS(SELECT 1 FROM auth.users WHERE id=NEW.id AND raw_user_meta_data->>'age_band'='18+') THEN RAISE EXCEPTION 'Une compte familiale requiert un adulte'; END IF; RETURN NEW; END $$;
REVOKE EXECUTE ON FUNCTION public.guard_account_type() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER guard_account_type BEFORE UPDATE OF account_type ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.guard_account_type();