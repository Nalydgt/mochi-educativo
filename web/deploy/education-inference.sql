DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'peluqo_inference_worker') THEN
    CREATE ROLE peluqo_inference_worker LOGIN;
  END IF;
END $$;

CREATE TABLE education.inference_jobs (
  id uuid PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('generate', 'tutor', 'curiosity')),
  payload jsonb,
  result jsonb,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'ready', 'failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now() + interval '4 minutes'
);
CREATE INDEX inference_jobs_pending ON education.inference_jobs(created_at) WHERE status = 'queued';
CREATE INDEX inference_jobs_expiry ON education.inference_jobs(expires_at);
ALTER TABLE education.inference_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.inference_jobs FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON education.inference_jobs TO peluqo_backend;
GRANT USAGE ON SCHEMA education TO peluqo_inference_worker;
GRANT SELECT, UPDATE, DELETE ON education.inference_jobs TO peluqo_inference_worker;
CREATE POLICY inference_web ON education.inference_jobs TO peluqo_backend
  USING (education.request_value('service') = 'true')
  WITH CHECK (education.request_value('service') = 'true');
CREATE POLICY inference_worker ON education.inference_jobs TO peluqo_inference_worker
  USING (true) WITH CHECK (true);
