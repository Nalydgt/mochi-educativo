ALTER TABLE education.learners
  ADD COLUMN web_preferences jsonb NOT NULL DEFAULT '{}'::jsonb
  CHECK (jsonb_typeof(web_preferences) = 'object');
