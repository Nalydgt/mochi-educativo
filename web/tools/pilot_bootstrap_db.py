"""Finish first-time initialization on the isolated pilot database only."""
import base64,shlex
from pilot import NAS,settings,credentials,APP
s=credentials();n=NAS(settings())
try:
 sql="""ALTER ROLE postgres PASSWORD '"""+s['database']+"""';
ALTER SCHEMA auth OWNER TO supabase_auth_admin;
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT oid::regprocedure AS f FROM pg_proc WHERE pronamespace='auth'::regnamespace LOOP EXECUTE format('ALTER FUNCTION %s OWNER TO supabase_auth_admin',r.f); END LOOP;
END $$;
"""
 encoded=base64.b64encode(sql.encode()).decode()
 print(n.container(APP,'db',"psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 -c "+shlex.quote("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='supabase_functions_admin') THEN CREATE ROLE supabase_functions_admin NOLOGIN; END IF; END $$;")+" && psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/init-scripts/99-roles.sql && printf '%s' "+shlex.quote(encoded)+" | base64 -d | psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1"))
 print(n.python("import urllib.request\nfor port,path in [(3010,'/expedicion'),(54321,'/health')]:\n try:\n  r=urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=15);print(port,r.status)\n except Exception as e:print(port,type(e).__name__,str(e)[:180])"))
finally:n.close()
