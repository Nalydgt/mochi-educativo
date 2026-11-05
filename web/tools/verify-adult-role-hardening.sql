-- Run as the database owner only against fictional fixtures. Every change rolls back.
BEGIN;
DO $test$
DECLARE
 teacher_id uuid;
 guardian_id uuid;
 no_role_id uuid := '7c2ae227-62bb-4905-8ef4-51250fb285f9';
 class_id uuid;
 shadow_class uuid;
 pupil uuid;
 sibling uuid;
 shadow_pupil uuid;
 home_teacher uuid;
 home_class uuid;
 home_pupil uuid;
 family_hash text := encode(extensions.digest(gen_random_uuid()::text,'sha256'),'hex');
 rejected_hash text := encode(extensions.digest(gen_random_uuid()::text,'sha256'),'hex');
 data jsonb;
 routine regprocedure;
 profile_blocked boolean := false;
BEGIN
 SELECT t.id INTO teacher_id FROM education.teachers t
 JOIN auth.users u ON u.id=t.id WHERE education.adult_role(t.id)='teacher' LIMIT 1;
 SELECT p.id INTO guardian_id FROM public.profiles p
 JOIN auth.users u ON u.id=p.id WHERE education.adult_role(p.id)='family' AND p.account_type='family'
 AND NOT public.has_role(p.id,'admin'::public.app_role) LIMIT 1;
 IF teacher_id IS NULL OR guardian_id IS NULL THEN RAISE EXCEPTION 'Missing fictional adult fixtures'; END IF;
 IF NOT EXISTS(SELECT FROM auth.users WHERE id=no_role_id) OR education.adult_role(no_role_id) IS NOT NULL
 THEN RAISE EXCEPTION 'Missing role-less fictional fixture'; END IF;

 FOREACH routine IN ARRAY ARRAY[
  'education.trusted_teacher_principal(uuid)'::regprocedure,
  'education.progress_snapshot(uuid,uuid)'::regprocedure,
  'education.analytics_snapshot(uuid,boolean,uuid,uuid,uuid,text,text,date,date,text)'::regprocedure,
  'education.issue_family_code(uuid,uuid,text)'::regprocedure,
  'education.revoke_family_links(uuid,uuid)'::regprocedure,
  'education.redeem_family_code(uuid,text)'::regprocedure,
  'education.manage_student_access(uuid,uuid,text,text,timestamptz)'::regprocedure,
  'education.manage_study_priority(uuid,uuid,text,text)'::regprocedure,
  'education.enable_home_studio(uuid)'::regprocedure,
  'education.resolve_home_studio(uuid)'::regprocedure
 ] LOOP
  IF has_function_privilege('anon',routine,'EXECUTE') OR has_function_privilege('authenticated',routine,'EXECUTE')
  THEN RAISE EXCEPTION 'Browser can execute private adult routine'; END IF;
 END LOOP;

 -- The older profile guard also blocks edits. Still simulate a legacy shadow row.
 BEGIN
  UPDATE public.profiles SET account_type='teacher',age_band='18+' WHERE id=guardian_id;
 EXCEPTION WHEN SQLSTATE 'P0001' THEN profile_blocked := true;
 END;
 IF NOT profile_blocked THEN RAISE EXCEPTION 'Profile identity mutation was not blocked'; END IF;
 UPDATE auth.users SET raw_user_meta_data=coalesce(raw_user_meta_data,'{}'::jsonb)||'{"account_type":"teacher","age_band":"18+"}'::jsonb WHERE id=guardian_id;
 INSERT INTO education.teachers(id) VALUES(guardian_id) ON CONFLICT DO NOTHING;
 IF education.adult_role(guardian_id) IS DISTINCT FROM 'family'
 OR coalesce(education.trusted_teacher_principal(guardian_id),false)
 THEN RAISE EXCEPTION 'Profile or shadow teacher row granted teacher authority'; END IF;
 INSERT INTO education.classes(teacher_id,name) VALUES(teacher_id,'Rollback role verification') RETURNING id INTO class_id;
 INSERT INTO education.classes(teacher_id,name) VALUES(guardian_id,'Rollback shadow teacher class') RETURNING id INTO shadow_class;
 INSERT INTO education.learners(class_id,name) VALUES(class_id,'Rollback linked child') RETURNING id INTO pupil;
 INSERT INTO education.learners(class_id,name) VALUES(class_id,'Rollback unlinked child') RETURNING id INTO sibling;
 INSERT INTO education.learners(class_id,name) VALUES(shadow_class,'Rollback shadow child') RETURNING id INTO shadow_pupil;

 IF education.issue_family_code(guardian_id,shadow_pupil,rejected_hash)
 OR education.revoke_family_links(guardian_id,shadow_pupil)
 THEN RAISE EXCEPTION 'Family impersonated teacher in family-code management'; END IF;
 IF NOT education.issue_family_code(teacher_id,pupil,family_hash)
 OR NOT education.redeem_family_code(guardian_id,family_hash)
 THEN RAISE EXCEPTION 'Canonical teacher/family linking failed after profile mutation'; END IF;
 IF NOT education.issue_family_code(teacher_id,sibling,rejected_hash)
 OR education.redeem_family_code(no_role_id,rejected_hash)
 THEN RAISE EXCEPTION 'Role-less profile redeemed family invitation'; END IF;

 data := education.progress_snapshot(guardian_id,class_id);
 IF data->>'role' IS DISTINCT FROM 'family' OR jsonb_array_length(data->'pupils')<>1
 OR data->'pupils'->0->>'id' IS DISTINCT FROM pupil::text
 THEN RAISE EXCEPTION 'Progress lost canonical family role or sibling isolation'; END IF;
 data := education.progress_snapshot(guardian_id,shadow_class);
 IF jsonb_array_length(data->'pupils')<>0 THEN RAISE EXCEPTION 'Shadow teacher class leaked through progress'; END IF;
 data := education.analytics_snapshot(guardian_id,false,shadow_class,NULL,NULL,NULL,NULL,current_date-7,current_date,'Europe/Madrid');
 IF data->>'role' IS DISTINCT FROM 'family' OR jsonb_array_length(data->'rows')<>0
 THEN RAISE EXCEPTION 'Analytics trusted shadow teacher row'; END IF;
 data := education.analytics_snapshot(guardian_id,true,NULL,NULL,NULL,NULL,NULL,current_date-7,current_date,'Europe/Madrid');
 IF data->>'role' IS NOT NULL OR jsonb_array_length(data->'rows')<>0
 THEN RAISE EXCEPTION 'Family escalated to admin analytics'; END IF;
 IF education.manage_study_priority(guardian_id,pupil,'matematicas','support') IS NULL
 OR education.manage_study_priority(guardian_id,sibling,'matematicas','support') IS NOT NULL
 OR education.manage_study_priority(guardian_id,shadow_pupil,'matematicas','support') IS NOT NULL
 THEN RAISE EXCEPTION 'Study priority role or child isolation failed'; END IF;
 IF education.manage_student_access(guardian_id,pupil,'status') IS NULL
 OR education.manage_student_access(guardian_id,shadow_pupil,'status') IS NOT NULL
 OR education.manage_student_access(guardian_id,pupil,'issue-legacy',rejected_hash,now()+interval '1 hour') IS NOT NULL
 OR education.manage_student_access(no_role_id,pupil,'status') IS NOT NULL
 THEN RAISE EXCEPTION 'Student access accepted shadow authority or unlinked adult'; END IF;

 -- Family home spaces retain their non-authenticating internal principal.
 IF NOT education.enable_home_studio(guardian_id) OR education.enable_home_studio(teacher_id)
 OR education.enable_home_studio(no_role_id)
 THEN RAISE EXCEPTION 'Home studio did not enforce canonical family role'; END IF;
 home_teacher := education.resolve_home_studio(guardian_id);
 IF home_teacher IS NULL OR NOT education.trusted_teacher_principal(home_teacher)
 OR education.resolve_home_studio(no_role_id) IS NOT NULL
 THEN RAISE EXCEPTION 'Home principal mapping invalid'; END IF;
 SELECT c.id INTO home_class FROM education.classes c WHERE c.teacher_id=home_teacher LIMIT 1;
 INSERT INTO education.learners(class_id,name) VALUES(home_class,'Rollback home child') RETURNING id INTO home_pupil;
 IF NOT education.school_can_view(guardian_id,home_pupil)
 OR NOT education.issue_family_code(home_teacher,home_pupil,encode(extensions.digest(gen_random_uuid()::text,'sha256'),'hex'))
 OR education.manage_student_access(home_teacher,home_pupil,'status') IS NULL
 THEN RAISE EXCEPTION 'Authorized family home workflow regressed'; END IF;

 -- An editable profile can never grant the trusted role; trusted Auth metadata can.
 UPDATE auth.users SET raw_user_meta_data=coalesce(raw_user_meta_data,'{}'::jsonb)||'{"account_type":"teacher","age_band":"18+"}'::jsonb WHERE id=no_role_id;
 IF education.adult_role(no_role_id) IS NOT NULL THEN RAISE EXCEPTION 'Editable profile granted role'; END IF;
 UPDATE auth.users SET raw_app_meta_data=coalesce(raw_app_meta_data,'{}'::jsonb)||'{"mochi_adult_role":"teacher"}'::jsonb WHERE id=no_role_id;
 IF education.adult_role(no_role_id) IS DISTINCT FROM 'teacher'
 OR NOT EXISTS(SELECT FROM education.teachers WHERE id=no_role_id)
 THEN RAISE EXCEPTION 'Trusted Auth metadata did not register teacher principal'; END IF;
END;
$test$;
ROLLBACK;
SELECT true AS passed, 'Canonical roles, spoofed teacher profile/row, cross-child access, home principal, trusted Auth trigger and private routine ACLs; every fixture change rolled back' AS verification;
