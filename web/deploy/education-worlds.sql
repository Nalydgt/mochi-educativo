ALTER TABLE education.sessions ADD COLUMN IF NOT EXISTS opened_at timestamptz;
UPDATE education.sessions SET opened_at = created_at WHERE opened_at IS NULL;
ALTER TABLE education.sessions
  ALTER COLUMN opened_at SET DEFAULT now(),
  ALTER COLUMN opened_at SET NOT NULL;
CREATE INDEX IF NOT EXISTS session_recent_world ON education.sessions(learner_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS education.curiosity_turns (
  id uuid PRIMARY KEY,
  learner_id uuid NOT NULL REFERENCES education.learners(id) ON DELETE CASCADE,
  question text NOT NULL CHECK (length(question) BETWEEN 1 AND 1600),
  text text NOT NULL CHECK (length(text) BETWEEN 1 AND 1800),
  kind text NOT NULL CHECK (kind IN ('material', 'general', 'guidance')),
  sources jsonb NOT NULL CHECK (jsonb_typeof(sources) = 'array'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS curiosity_learner_recent ON education.curiosity_turns(learner_id, created_at DESC);
ALTER TABLE education.curiosity_turns ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON education.curiosity_turns FROM PUBLIC, anon, authenticated, peluqo_backend;
GRANT SELECT, INSERT ON education.curiosity_turns TO peluqo_backend;
CREATE POLICY curiosity_owner ON education.curiosity_turns TO peluqo_backend
  USING (learner_id::text = education.request_value('learner'))
  WITH CHECK (learner_id::text = education.request_value('learner'));
