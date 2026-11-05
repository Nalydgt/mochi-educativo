import { readFile } from "node:fs/promises";
const d = JSON.parse(await readFile(".runtime/demo-device.json", "utf8"));
const state = await fetch("http://localhost:3000/api/education/", {
  headers: { Cookie: d.cookie },
}).then((r) => r.json());
const r = await fetch("http://localhost:3000/api/education/", {
  method: "POST",
  headers: { Cookie: d.cookie, "Content-Type": "application/json" },
  body: JSON.stringify({
    action: "hint",
    sessionId: d.sessionId,
    activityId: state.learning.activities[0].id,
  }),
});
console.log(JSON.stringify({ hintRequested: r.status === 200, sessionId: d.sessionId }));
