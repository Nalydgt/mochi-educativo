// Restricted-server-role acceptance test. Only fictional rows, enclosed in an unconditional rollback.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID, createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import postgres from "postgres";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = async (file) => JSON.parse(await readFile(path.join(root, file), "utf8"));
const database = await read(".runtime/cloud-database.json");
const cloud = await read(".runtime/cloud-public.json");
const teacher = await read(".runtime/teacher-demo.json");
const family = await read(".runtime/qa-integral-family.json");
const secondFamily = await read(".runtime/school-onboarding-fixture.json");
const futureFamily = await read(".runtime/school-future-guardian-fixture.json");
const secrets = await read(".runtime/pilot-secrets.json");
async function identity(account) {
  const response = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: cloud.key, "Content-Type": "application/json" },
    body: JSON.stringify(account),
    signal: AbortSignal.timeout(20000),
  });
  assert.equal(response.status, 200, "Fictional adult authentication failed");
  return (await response.json()).user.id;
}
const teacherId = await identity({ email: teacher.email, password: teacher.password });
const familyId = await identity(family);
const otherTeacher = await identity({
  email: "docente@peluqo.local",
  password: secrets.teacher_password,
});
const hash = () => createHash("sha256").update(randomUUID()).digest("hex");
const checks = [];
let stage = "connect";
const pg = postgres(database.url, { max: 1, prepare: false, connect_timeout: 10 });
const rollback = new Error("expected_care_collaboration_rollback");
try {
  try {
    await pg.begin(async (q) => {
      await q`select set_config('peluqo.teacher',${teacherId},true),set_config('peluqo.service','true',true)`;
      const call = async (actor, body) =>
        (
          await q`select education.school_command(${actor}::uuid,${JSON.stringify(body)}::text::jsonb) as result`
        )[0].result;
      const snapshot = async (actor) =>
        (await q`select education.school_snapshot(${actor}::uuid) as result`)[0].result;
      const expectCode = async (operation, code) => {
        let actual;
        await q
          .savepoint(async () => {
            await operation();
          })
          .catch((error) => {
            actual = error.code;
          });
        assert.equal(actual, code);
      };
      const ingest = async (device, signal, source = "daily_voice", confirmed = true) =>
        (
          await q`select education.ingest_support_signal(${device}::uuid,${signal}::uuid,'possible_peer_bullying',${source},true,${confirmed}) as result`
        )[0].result;
      const [{ id: classId }] =
        await q`insert into education.classes(teacher_id,name) values(${teacherId},'Rollback care collaboration') returning id`;
      const pupils =
        await q`insert into education.learners(class_id,name) values(${classId},'Prueba Colaboración Uno'),(${classId},'Prueba Colaboración Dos'),(${classId},'Prueba Sin Vínculo') returning id`;
      const [first, second, unrelated] = pupils.map((pupil) => pupil.id);
      const link = async (adult, pupil) => {
        const invitation = hash();
        assert.equal(
          (
            await q`select education.issue_family_code(${teacherId},${pupil},${invitation}) as ok`
          )[0].ok,
          true,
        );
        assert.equal(
          (await q`select education.redeem_family_code(${adult},${invitation}) as ok`)[0].ok,
          true,
        );
      };
      await link(familyId, first);
      await q`select education.onboard_family(${secondFamily.id},true)`;
      await q`select education.onboard_family(${futureFamily.id},true)`;
      await link(secondFamily.id, first);
      const [{ id: deviceId }] =
        await q`insert into education.devices(teacher_id,learner_id,token_hash) values(${teacherId},${first},${hash()}) returning id`;
      const [{ id: anotherDevice }] =
        await q`insert into education.devices(teacher_id,learner_id,token_hash) values(${teacherId},${first},${hash()}) returning id`;
      stage = "private_surface";
      const [{ browser, browserTable, serverTable, baseCommand }] = await q`select
        has_function_privilege('authenticated','education.ingest_support_signal(uuid,uuid,text,text,boolean,boolean)','EXECUTE') as browser,
        has_table_privilege('authenticated','education.school_care_signals','SELECT') as "browserTable",
        has_table_privilege(current_user,'education.school_point_ledger','INSERT') as "serverTable",
        has_function_privilege(current_user,'education.school_command_before_care(uuid,jsonb)','EXECUTE') as "baseCommand"`;
      assert.equal(browser, false);
      assert.equal(browserTable, false);
      assert.equal(serverTable, false);
      assert.equal(baseCommand, false);
      let state = (
        await q`select education.device_school_context(${first},${teacherId}) as result`
      )[0].result;
      assert.equal(state.deviceSettings.reminderMinutes, 10);
      assert.equal(state.deviceSettings.familySupportAlertsEnabled, false);
      const signalId = randomUUID();
      await expectCode(() => ingest(deviceId, signalId), "42501");
      const settings = {
        action: "save-settings",
        requestId: randomUUID(),
        learnerId: first,
        dailyMinutes: 30,
        startTime: "08:00",
        endTime: "20:00",
        timezone: "Europe/Madrid",
        language: "es",
        voiceEnabled: true,
        captionsEnabled: true,
        textFirst: false,
        sharePractice: false,
        reminderMinutes: 15,
        familySupportAlertsEnabled: true,
        expectedRevision: 0,
      };
      await expectCode(
        () => call(teacherId, { ...settings, requestId: randomUUID(), learnerId: unrelated }),
        "42501",
      );
      await call(familyId, settings);
      await expectCode(() => ingest(deviceId, signalId, "family_harm"), "22023");
      await expectCode(() => ingest(deviceId, signalId, "daily_voice", false), "22023");
      assert.deepEqual(await ingest(deviceId, signalId), {
        accepted: true,
        signalId,
        visibleToFamily: true,
      });
      assert.deepEqual(await ingest(deviceId, signalId), {
        accepted: true,
        signalId,
        visibleToFamily: true,
      });
      await expectCode(() => ingest(anotherDevice, signalId), "23505");
      state = (await q`select education.device_school_context(${first},${teacherId}) as result`)[0]
        .result;
      assert.equal(state.deviceSettings.reminderMinutes, 15);
      assert.equal(state.deviceSettings.dailyMinutes, 30);
      assert.equal(state.deviceSettings.familySupportAlertsEnabled, true);
      const teacherView = await snapshot(teacherId);
      assert.equal(Object.hasOwn(teacherView, "careAlerts"), false);
      assert.equal(
        Object.hasOwn(
          teacherView.settings.find((entry) => entry.learnerId === first),
          "familySupportAlertsEnabled",
        ),
        false,
      );
      assert.ok(
        (await snapshot(familyId)).careAlerts.some(
          (entry) => entry.id === signalId && entry.status === "pending_review",
        ),
      );
      assert.ok(
        (await snapshot(secondFamily.id)).careAlerts.some((entry) => entry.id === signalId),
      );
      assert.ok(
        !(await snapshot(futureFamily.id)).careAlerts.some((entry) => entry.id === signalId),
      );
      const review = {
        action: "review-care-alert",
        requestId: randomUUID(),
        alertId: signalId,
        status: "reviewed",
      };
      await expectCode(() => call(teacherId, review), "42501");
      await expectCode(() => call(futureFamily.id, review), "P0002");
      await call(familyId, review);
      await link(futureFamily.id, first);
      assert.ok(
        !(await snapshot(futureFamily.id)).careAlerts.some((entry) => entry.id === signalId),
      );
      await expectCode(
        () => call(futureFamily.id, { ...review, requestId: randomUUID() }),
        "P0002",
      );
      assert.equal(
        (await snapshot(secondFamily.id)).careAlerts.find((entry) => entry.id === signalId).status,
        "pending_review",
      );
      assert.equal(
        (await snapshot(familyId)).careAlerts.find((entry) => entry.id === signalId).status,
        "reviewed",
      );
      const teacherExport = (
        await q`select education.export_learning_data(${teacherId}) as result`
      )[0].result;
      assert.equal(JSON.stringify(teacherExport).includes("possible_peer_bullying"), false);
      assert.equal(Object.hasOwn(teacherExport.school, "careAlerts"), false);
      assert.ok(
        (
          await q`select education.export_learning_data(${familyId}) as result`
        )[0].result.school.careAlerts.some((entry) => entry.id === signalId),
      );
      checks.push(
        "Opt-in and child confirmation, idempotent visible receipts, family-only access/export, independent reviews and no historical sharing with future guardians",
      );

      stage = "reminder_retry";
      const updated = {
        ...settings,
        requestId: randomUUID(),
        expectedRevision: 1,
        reminderMinutes: null,
        familySupportAlertsEnabled: false,
      };
      await call(familyId, updated);
      await call(familyId, settings); // Lost acknowledgement must not reapply an older consent/reminder.
      state = (await q`select education.device_school_context(${first},${teacherId}) as result`)[0]
        .result;
      assert.equal(state.deviceSettings.reminderMinutes, null);
      assert.equal(state.deviceSettings.familySupportAlertsEnabled, false);
      await expectCode(() => ingest(deviceId, randomUUID()), "42501");
      checks.push(
        "Parents disable reminders/alerts without changing daily limit; old retries cannot restore previous consent",
      );

      stage = "groups";
      const group = {
        action: "save-group",
        requestId: randomUUID(),
        classId,
        name: "Equipo Cometa",
        members: [
          { learnerId: first, peerRole: "helper", voluntary: true, buddyAlias: "Cometa" },
          { learnerId: second, peerRole: "member", voluntary: true },
        ],
      };
      await expectCode(
        () =>
          call(teacherId, {
            ...group,
            requestId: randomUUID(),
            members: [{ ...group.members[0], voluntary: false }, group.members[1]],
          }),
        "22023",
      );
      await expectCode(() => call(otherTeacher, group), "42501");
      await expectCode(() => call(familyId, group), "42501");
      const saved = await call(teacherId, group);
      assert.deepEqual(await call(teacherId, group), saved);
      await expectCode(
        () =>
          call(teacherId, {
            ...group,
            requestId: randomUUID(),
            groupId: saved.id,
            expectedRevision: 99,
          }),
        "40001",
      );
      const assignment = {
        action: "assign-group",
        requestId: randomUUID(),
        groupId: saved.id,
        subject: "matematicas",
        title: "Contamos en equipo",
        goal: "Explicar agrupaciones de objetos",
        instructions: "Cuenta dos grupos de tres y comparte tu explicación",
        dueAt: "2026-11-12",
        factors: [[2, 3]],
      };
      const batch = await call(teacherId, assignment);
      assert.equal(batch.assigned, 2);
      assert.deepEqual(await call(teacherId, assignment), batch);
      assert.equal((await snapshot(familyId)).groups.length, 0);
      const helperAssignment = batch.assignments.find((entry) => entry.learnerId === first);
      const memberAssignment = batch.assignments.find((entry) => entry.learnerId === second);
      assert.equal(
        (
          await q`select education.device_group_context(${memberAssignment.id},${second},${teacherId}) as result`
        )[0].result.childBuddyAlias,
        "Cometa",
      );
      assert.equal(
        (await snapshot(teacherId)).points.filter((entry) =>
          [first, second].includes(entry.learnerId),
        ).length,
        0,
      );
      for (const assigned of batch.assignments) {
        const [{ id: device }] =
          await q`insert into education.devices(teacher_id,learner_id,token_hash) values(${teacherId},${assigned.learnerId},${hash()}) returning id`;
        const payload = {
          completed: true,
          completedCount: 1,
          detailsShared: false,
          clientReported: true,
          answers: [],
          attempts: 1,
          hints: 0,
          elapsedSeconds: 12,
        };
        await q`insert into education.device_lesson_results(result_id,assignment_id,device_id,payload,request_hash,correct_count)
          values(${randomUUID()},${assigned.id},${device},${JSON.stringify(payload)}::text::jsonb,${hash()},1)`;
      }
      const humanReview = {
        action: "review-lesson",
        requestId: randomUUID(),
        assignmentId: helperAssignment.id,
        status: "reviewed",
        observation: "Ha explicado sus agrupaciones",
        publish: false,
      };
      await call(teacherId, humanReview);
      const points = async () =>
        (await snapshot(teacherId)).points.filter((entry) =>
          [first, second].includes(entry.learnerId),
        );
      assert.equal((await points()).length, 0);
      const published = { ...humanReview, requestId: randomUUID(), publish: true };
      await call(teacherId, published);
      await call(teacherId, published);
      assert.deepEqual(
        (await points()).map((entry) => entry.points),
        [10],
      );
      const help = {
        action: "confirm-help",
        requestId: randomUUID(),
        assignmentId: helperAssignment.id,
        helpedLearnerId: second,
      };
      await expectCode(() => call(teacherId, help), "P0002");
      await call(teacherId, {
        ...published,
        requestId: randomUUID(),
        assignmentId: memberAssignment.id,
      });
      assert.equal((await points()).filter((entry) => entry.reason === "review").length, 2);
      assert.equal((await points()).filter((entry) => entry.reason === "group").length, 2);
      await call(teacherId, help);
      await call(teacherId, { ...help, requestId: randomUUID() });
      assert.equal((await points()).filter((entry) => entry.reason === "help").length, 1);
      await expectCode(() => call(familyId, { ...help, requestId: randomUUID() }), "P0002");
      await expectCode(
        () =>
          call(teacherId, {
            ...help,
            requestId: randomUUID(),
            assignmentId: memberAssignment.id,
            helpedLearnerId: first,
          }),
        "P0002",
      );
      await expectCode(
        () => call(teacherId, { ...help, requestId: randomUUID(), helpedLearnerId: unrelated }),
        "P0002",
      );
      assert.equal(
        (await q`select education.device_school_context(${first},${teacherId}) as result`)[0].result
          .collaborationPoints,
        35,
      );
      assert.equal(
        (await points())
          .filter((entry) => entry.learnerId === second)
          .reduce((sum, entry) => sum + entry.points, 0),
        30,
      );
      checks.push(
        "Voluntary same-class groups, atomic assignments, manual review awards, complete-team bonus and teacher-confirmed help exactly once",
      );
      stage = "archive";
      await call(teacherId, {
        action: "archive-group",
        requestId: randomUUID(),
        groupId: saved.id,
        expectedRevision: 1,
      });
      await expectCode(() => call(teacherId, { ...assignment, requestId: randomUUID() }), "P0002");
      checks.push(
        "Archived groups stop new assignments while existing results and earned points remain reviewable",
      );
      stage = "former_guardian_consent";
      await call(familyId, {
        ...updated,
        requestId: randomUUID(),
        expectedRevision: 2,
        familySupportAlertsEnabled: true,
      });
      await call(secondFamily.id, {
        action: "review-care-alert",
        requestId: randomUUID(),
        alertId: signalId,
        status: "dismissed",
      });
      assert.ok(
        (
          await q`select education.reset_learning_data(${secondFamily.id},'ELIMINAR',${randomUUID()}) as result`
        )[0].result,
      );
      assert.equal(
        (await snapshot(familyId)).careAlerts.find((entry) => entry.id === signalId).status,
        "reviewed",
      );
      await link(secondFamily.id, first);
      assert.ok(
        !(await snapshot(secondFamily.id)).careAlerts.some((entry) => entry.id === signalId),
      );
      assert.equal(
        (await q`select education.device_school_context(${first},${teacherId}) as result`)[0].result
          .deviceSettings.familySupportAlertsEnabled,
        true,
      );
      checks.push(
        "One guardian reset removes only their private recipient/review; relinking does not restore historical alerts or affect another guardian consent",
      );
      assert.equal(
        (await q`select education.revoke_family_links(${teacherId},${first}) as ok`)[0].ok,
        true,
      );
      assert.equal(
        (await q`select education.device_school_context(${first},${teacherId}) as result`)[0].result
          .deviceSettings.familySupportAlertsEnabled,
        false,
      );
      await expectCode(() => ingest(deviceId, randomUUID()), "42501");
      assert.ok(!(await snapshot(familyId)).careAlerts.some((entry) => entry.id === signalId));
      checks.push(
        "Removing the consenting guardian invalidates opt-in and immediately removes incident access",
      );
      throw rollback;
    });
  } catch (error) {
    if (error !== rollback) throw error;
  }
  const output = {
    passed: true,
    at: new Date().toISOString(),
    source: "real_postgres_server_role",
    fictionalRowsRolledBack: true,
    dataCommitted: false,
    externalNotificationsSent: false,
    checks,
  };
  await writeFile(
    path.join(
      root,
      "..",
      "tamagochi 2",
      "docs",
      "mediciones",
      "20261105-mochi-care-collaboration.json",
    ),
    JSON.stringify(output, null, 2) + "\n",
  );
  console.log(JSON.stringify(output));
} catch (error) {
  console.error(
    JSON.stringify({
      passed: false,
      stage,
      code: error.code ?? error.name,
      checkCount: checks.length,
      databaseMessage: ["42501", "42P01", "42703", "42702"].includes(error.code)
        ? String(error.message).slice(0, 180)
        : undefined,
      message:
        error instanceof assert.AssertionError
          ? error.message.slice(0, 220)
          : "Verification rolled back; no test data committed",
    }),
  );
  process.exitCode = 1;
} finally {
  await pg.end({ timeout: 5 });
}
