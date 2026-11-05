// Real Postgres acceptance test. Every fictional row is rolled back, including messages and grades.
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
const secrets = await read(".runtime/pilot-secrets.json");
async function identity(account) {
  const response = await fetch(cloud.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: cloud.key, "Content-Type": "application/json" },
    body: JSON.stringify(account),
    signal: AbortSignal.timeout(20000),
  });
  assert.equal(response.status, 200, "Fictitious adult authentication failed");
  return (await response.json()).user.id;
}
const teacherId = await identity({ email: teacher.email, password: teacher.password });
const familyId = await identity(family);
const otherId = await identity({
  email: "docente@peluqo.local",
  password: secrets.teacher_password,
});
const checks = [];
let stage = "connect";
const pg = postgres(database.url, { max: 1, prepare: false, connect_timeout: 10 });
const rollback = new Error("expected_acceptance_rollback");
try {
  try {
    await pg.begin(async (q) => {
      await q`select set_config('peluqo.teacher',${teacherId},true),set_config('peluqo.service','true',true)`;
      stage = "browser_privileges";
      const [access] = await q`select
        has_function_privilege('anon','education.school_command(uuid,jsonb)','EXECUTE') as anon_command,
        has_function_privilege('authenticated','education.school_snapshot(uuid)','EXECUTE') as browser_snapshot,
        has_table_privilege('authenticated','education.adult_accounts','INSERT') as browser_role_write`;
      assert.equal(access.anon_command, false);
      assert.equal(access.browser_snapshot, false);
      assert.equal(access.browser_role_write, false);
      stage = "teacher_not_downgraded";
      assert.equal(
        (await q`select education.onboard_family(${teacherId},true) as role`)[0].role,
        "teacher",
      );
      let onboardingTested = false;
      for (const file of [
        ".runtime/school-onboarding-fixture.json",
        ".runtime/qa-self-signup-account.json",
        ".runtime/qa-new-family.json",
      ]) {
        stage = "legacy_onboarding_" + path.basename(file);
        const fixture = await read(file);
        const [{ role }] = await q`select education.adult_role(${fixture.id}) as role`;
        if (role !== null) continue;
        let denied;
        await q
          .savepoint(async () => {
            await q`select education.onboard_family(${fixture.id},false)`;
          })
          .catch((error) => {
            denied = error.code;
          });
        assert.equal(denied, "42501");
        let onboarded;
        await q
          .savepoint(async (candidate) => {
            onboarded = (
              await candidate`select education.onboard_family(${fixture.id},true) as role`
            )[0].role;
          })
          .catch((error) => {
            if (error.code !== "42501") throw error;
          });
        if (!onboarded) continue;
        assert.equal(onboarded, "family");
        assert.equal(
          (await q`select education.onboard_family(${fixture.id},true) as role`)[0].role,
          "family",
        );
        assert.equal(
          (await q`select education.school_snapshot(${fixture.id}) as result`)[0].result.role,
          "family",
        );
        onboardingTested = true;
        break;
      }
      assert.equal(
        onboardingTested,
        true,
        "No role-less fictional account was available to verify legacy adult onboarding",
      );
      checks.push(
        "Server-owned adult roles, browser privilege denial and explicit legacy family onboarding",
      );
      const [{ id: classId }] =
        await q`insert into education.classes(teacher_id,name) values(${teacherId},'Verificación transaccional Mochi') returning id`;
      const pupils =
        await q`insert into education.learners(class_id,name) values(${classId},'Prueba Uno'),(${classId},'Prueba Dos') returning id`;
      const pupil = pupils[0].id,
        second = pupils[1].id;
      const codeHash = createHash("sha256").update(randomUUID()).digest("hex");
      assert.equal(
        (await q`select education.issue_family_code(${teacherId},${pupil},${codeHash}) as ok`)[0]
          .ok,
        true,
      );
      assert.equal(
        (await q`select education.redeem_family_code(${familyId},${codeHash}) as ok`)[0].ok,
        true,
      );
      const command = async (actor, body) =>
        (
          await q`select education.school_command(${actor}::uuid,${JSON.stringify(body)}::text::jsonb) as result`
        )[0].result;
      const snapshot = async (actor) =>
        (await q`select education.school_snapshot(${actor}::uuid) as result`)[0].result;
      const deny = async (actor, body, expected) => {
        let actual;
        await q
          .savepoint(async () => {
            await command(actor, body);
          })
          .catch((error) => {
            actual = error.code;
          });
        assert.equal(actual, expected);
      };
      const assignment = {
        action: "batch-assign",
        requestId: randomUUID(),
        classId,
        title: "Contamos grupos",
        subject: "matematicas",
        goal: "Comprender grupos iguales",
        instructions: "Explica cómo contar cada grupo",
        dueAt: "2026-11-10",
        factors: [
          [2, 3],
          [3, 2],
        ],
      };
      const first = await command(teacherId, assignment);
      assert.equal(first.assigned, 2);
      assert.deepEqual(await command(teacherId, assignment), first);
      assert.equal(
        (await snapshot(teacherId)).lessons.filter((lesson) =>
          first.assignments.some((entry) => entry.id === lesson.id),
        ).length,
        2,
      );
      await deny(otherId, { ...assignment, requestId: randomUUID() }, "P0002");
      await deny(familyId, { ...assignment, requestId: randomUUID() }, "42501");
      checks.push("Atomic class assignment, exact retry and cross-account rejection");

      const assigned = first.assignments.find((entry) => entry.learnerId === pupil);
      const [{ id: device }] =
        await q`insert into education.devices(teacher_id,learner_id,token_hash)
        values(${teacherId},${pupil},${createHash("sha256").update(randomUUID()).digest("hex")}) returning id`;
      const payload = {
        resultId: randomUUID(),
        assignmentId: assigned.id,
        lessonId: assigned.lessonId,
        completed: true,
        attempts: 3,
        hints: 1,
        elapsedSeconds: 27,
        completedCount: 2,
        detailsShared: true,
        clientReported: false,
        answers: [
          { a: 2, b: 3, choice: 5, correct: false },
          { a: 2, b: 3, choice: 6, correct: true },
          { a: 3, b: 2, choice: 6, correct: true },
        ],
      };
      await q`insert into education.device_lesson_results(result_id,assignment_id,device_id,payload,request_hash,correct_count)
        values(${payload.resultId},${assigned.id},${device},${JSON.stringify(payload)}::text::jsonb,'fictional-receipt',2)`;
      await command(teacherId, {
        action: "review-lesson",
        requestId: randomUUID(),
        assignmentId: assigned.id,
        status: "needs_support",
        observation: "Revisar la explicación de los grupos",
        publish: false,
      });
      let child = (await snapshot(familyId)).lessons.find((lesson) => lesson.id === assigned.id);
      assert.equal(child.review, null);
      await command(teacherId, {
        action: "review-lesson",
        requestId: randomUUID(),
        assignmentId: assigned.id,
        status: "reviewed",
        observation: "Ha explicado correctamente las agrupaciones",
        publish: true,
      });
      assert.equal(
        (await snapshot(familyId)).lessons.find((lesson) => lesson.id === assigned.id).review
          .status,
        "reviewed",
      );
      checks.push("Human review stays private until teacher publishes it");

      const grade = {
        action: "save-grade",
        requestId: randomUUID(),
        learnerId: pupil,
        assignmentId: assigned.id,
        title: "Revisión manual",
        subject: "Matemáticas",
        value: 8.5,
        feedback: "Explica cómo agrupó",
        publish: false,
      };
      const draft = await command(teacherId, grade);
      assert.ok(!(await snapshot(familyId)).grades.some((entry) => entry.id === draft.id));
      const published = await command(teacherId, {
        ...grade,
        requestId: randomUUID(),
        gradeId: draft.id,
        expectedRevision: 1,
        publish: true,
      });
      assert.equal(published.revision, 2);
      assert.equal(
        (await snapshot(familyId)).grades.find((entry) => entry.id === draft.id).value,
        8.5,
      );
      await deny(
        teacherId,
        {
          ...grade,
          requestId: randomUUID(),
          gradeId: draft.id,
          expectedRevision: 1,
          publish: true,
        },
        "40001",
      );
      await deny(familyId, { ...grade, requestId: randomUUID() }, "P0002");
      checks.push("Manual official grade publication, revision conflict and family write denial");

      const message = await command(teacherId, {
        action: "send-message",
        requestId: randomUUID(),
        classId,
        title: "Tutoría de demostración",
        body: "Revisamos el progreso de la semana",
        allowReplies: true,
      });
      const visibleMessage = (await snapshot(familyId)).messages.find(
        (entry) => entry.id === message.id,
      );
      assert.deepEqual(visibleMessage.learnerIds, [pupil]);
      assert.equal(visibleMessage.allowReplies, true);
      await command(familyId, {
        action: "reply-message",
        requestId: randomUUID(),
        messageId: message.id,
        learnerId: pupil,
        body: "Recibido, gracias",
      });
      await deny(
        familyId,
        {
          action: "reply-message",
          requestId: randomUUID(),
          messageId: message.id,
          learnerId: second,
          body: "No autorizado",
        },
        "P0002",
      );
      await command(familyId, {
        action: "mark-message-read",
        requestId: randomUUID(),
        messageId: message.id,
      });
      const readMessage = (await snapshot(teacherId)).messages.find(
        (entry) => entry.id === message.id,
      );
      assert.equal(readMessage.readCount, 1);
      assert.equal(readMessage.replies.length, 1);
      checks.push("Scoped communications, guardian reply and reading receipt");

      const event = await command(teacherId, {
        action: "save-event",
        requestId: randomUUID(),
        classId,
        title: "Tutoría",
        description: "Seguimiento con la familia",
        kind: "meeting",
        startsAt: "2026-11-10T16:00:00+01:00",
        endsAt: "2026-11-10T16:30:00+01:00",
      });
      assert.ok((await snapshot(familyId)).events.some((entry) => entry.id === event.id));
      const preferences = {
        action: "save-settings",
        requestId: randomUUID(),
        learnerId: pupil,
        expectedRevision: 0,
        dailyMinutes: 25,
        startTime: "09:00",
        endTime: "19:00",
        timezone: "Europe/Madrid",
        language: "es",
        voiceEnabled: false,
        sharePractice: false,
        captionsEnabled: false,
        textFirst: false,
      };
      await command(familyId, preferences);
      const configuration = (await snapshot(familyId)).settings.find(
        (entry) => entry.learnerId === pupil,
      );
      assert.equal(configuration.captionsEnabled, true);
      assert.equal(configuration.textFirst, true);
      await deny(
        teacherId,
        { ...preferences, requestId: randomUUID(), expectedRevision: 1 },
        "42501",
      );
      const [{ result: deviceContext }] =
        await q`select education.device_school_context(${pupil},${teacherId}) as result`;
      assert.equal(deviceContext.deviceSettings.dailyMinutes, 25);
      assert.equal(deviceContext.deviceSettings.utcOffsetMinutes, 60);
      assert.equal(deviceContext.deviceSettings.voiceEnabled, false);
      assert.equal(deviceContext.deviceSettings.captionsEnabled, true);
      assert.equal(deviceContext.learningSummary.completedLessons, 1);
      assert.equal(
        (await snapshot(familyId)).lessons.find((entry) => entry.id === assigned.id).result.answers
          .length,
        0,
      );
      await command(teacherId, {
        action: "save-profile",
        requestId: randomUUID(),
        learnerId: pupil,
        ageBand: "6–8",
        gradeLabel: "3.º de primaria",
      });
      checks.push(
        "Calendar, guardian device preferences, captions fallback and profile synchronization",
      );

      const minimal = { ...payload, answers: [], detailsShared: false, clientReported: true };
      assert.equal(
        (
          await q`select education.minimize_device_receipt(${device},${assigned.id},${payload.resultId},'private-receipt',${JSON.stringify(minimal)}::text::jsonb) as accepted`
        )[0].accepted,
        true,
      );
      assert.equal(
        (
          await q`select education.minimize_device_receipt(${device},${assigned.id},${payload.resultId},'changed-receipt',${JSON.stringify({ ...minimal, hints: 2 })}::text::jsonb) as accepted`
        )[0].accepted,
        false,
      );
      checks.push("Lost-ACK privacy downgrade accepts only unchanged completion aggregates");

      await command(teacherId, {
        action: "withdraw-grade",
        requestId: randomUUID(),
        gradeId: draft.id,
      });
      assert.ok(!(await snapshot(familyId)).grades.some((entry) => entry.id === draft.id));
      await command(teacherId, {
        action: "delete-event",
        requestId: randomUUID(),
        eventId: event.id,
      });
      assert.ok(
        (await snapshot(familyId)).events.find((entry) => entry.id === event.id).cancelledAt,
      );
      await command(teacherId, {
        action: "withdraw-message",
        requestId: randomUUID(),
        messageId: message.id,
      });
      await deny(
        familyId,
        {
          action: "reply-message",
          requestId: randomUUID(),
          messageId: message.id,
          learnerId: pupil,
          body: "Respuesta tardía",
        },
        "P0002",
      );
      const [{ result: exported }] =
        await q`select education.export_learning_data(${familyId}) as result`;
      assert.equal(exported.school.role, "family");
      assert.ok(exported.school.lessons.some((entry) => entry.id === assigned.id));
      assert.ok(!exported.school.learners.some((entry) => entry.id === second));
      checks.push("Withdrawal controls and owner-scoped export include device records");
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
      "20261105-mochi-school-backend.json",
    ),
    JSON.stringify(output, null, 2) + "\n",
  );
  console.log(JSON.stringify(output));
} catch (error) {
  console.error(
    JSON.stringify({
      passed: false,
      code: error.code ?? error.name,
      checkCount: checks.length,
      stage,
      databaseMessage: ["42501", "42P01", "42703"].includes(error.code)
        ? String(error.message).slice(0, 160)
        : undefined,
      message:
        error instanceof assert.AssertionError
          ? error.message.slice(0, 200)
          : "School verification failed; no test transaction was committed",
    }),
  );
  process.exitCode = 1;
} finally {
  await pg.end({ timeout: 5 });
}
