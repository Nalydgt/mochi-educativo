import fs from "node:fs/promises";
import path from "node:path";
const root = "deploy/supabase";
await fs.mkdir(root, { recursive: true });
const commit = await (
  await fetch(
    "https://api.github.com/repos/supabase/supabase/commits?path=docker/docker-compose.yml&per_page=1",
    { headers: { "User-Agent": "Peluqo-local-development" } },
  )
).json();
const sha = commit[0]?.sha;
if (!sha) throw new Error("Could not pin upstream revision");
const tree = await (
  await fetch(`https://api.github.com/repos/supabase/supabase/git/trees/${sha}?recursive=1`, {
    headers: { "User-Agent": "Peluqo-local-development" },
  })
).json();
const selected = tree.tree.filter(
  (f) =>
    f.type === "blob" &&
    [
      "docker/docker-compose.yml",
      "docker/.env.example",
      "docker/volumes/db/roles.sql",
      "docker/volumes/db/jwt.sql",
      "docker/volumes/db/webhooks.sql",
      "docker/volumes/db/_supabase.sql",
      "docker/volumes/api/kong.yml",
      "LICENSE",
    ].includes(f.path),
);
for (const f of selected) {
  const target = path.join(root, f.path.replace(/^docker\//, ""));
  await fs.mkdir(path.dirname(target), { recursive: true });
  const r = await fetch(`https://raw.githubusercontent.com/supabase/supabase/${sha}/${f.path}`);
  if (!r.ok) throw Error(f.path);
  await fs.writeFile(target, await r.text());
}
await fs.writeFile(
  path.join(root, "UPSTREAM.json"),
  JSON.stringify(
    { repository: "https://github.com/supabase/supabase", sha, files: selected.map((f) => f.path) },
    null,
    2,
  ),
);
console.log({ revision: sha, files: selected.length });
