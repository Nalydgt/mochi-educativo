// Live rejection-only proof. No valid signup invitation or existing account credential is submitted.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
const cloud = JSON.parse(await readFile(".runtime/cloud-public.json", "utf8"));
const origin = "https://peluqo-mundos.vercel.app";
const endpoint = cloud.url + "/functions/v1/peluqo-pilot-signup";
const base = {
  email: "fictional-edge-proof@school.invalid",
  password: "Fictitious-proof-password",
  display_name: "Adulto ficticio",
  account_type: "teacher",
  age_band: "18+",
};
const cases = [
  { name: "teacher_requires_invitation", body: base, status: 400 },
  {
    name: "minor_denied_before_invitation_lookup",
    body: { ...base, age_band: "9–12", invitation: "A".repeat(24) },
    status: 400,
  },
  {
    name: "client_role_not_accepted",
    body: { ...base, account_type: "admin", invitation: "A".repeat(24) },
    status: 400,
  },
  { name: "foreign_origin_denied", body: base, origin: "https://foreign.invalid", status: 403 },
];
const checks = [];
for (const item of cases) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      apikey: cloud.key,
      Origin: item.origin ?? origin,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(item.body),
    signal: AbortSignal.timeout(15000),
  });
  assert.equal(response.status, item.status, item.name);
  const result = await response.json();
  assert.equal(typeof result.error, "string");
  checks.push({ name: item.name, status: response.status });
}
const output = {
  passed: true,
  at: new Date().toISOString(),
  deployedFunction: "peluqo-pilot-signup",
  verifyJwt: false,
  validInvitationsSubmitted: 0,
  accountsCreated: 0,
  emailsOrNotificationsSent: 0,
  checks,
};
await writeFile(
  "../tamagochi 2/docs/mediciones/20261105-mochi-signup-edge.json",
  JSON.stringify(output, null, 2) + "\n",
);
console.log(JSON.stringify(output));
