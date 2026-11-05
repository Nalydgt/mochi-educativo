import { AsyncLocalStorage } from "node:async_hooks";
import type { Row } from "postgres";
import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from "node:crypto";
import { db } from "./db.server";
import { deviceLessonResultSchema, evaluateDeviceLesson } from "./device-lessons";
import { supportSignalSchema } from "./school-schema";
import { ApiError, adultAccount } from "./adult-auth.server";
import { resolveHomeStudio } from "./home-studio.server";
import { normalizeStudentCode } from "./student-access";
import { legacyStudentCode, openStudentLogin, randomAccessCode } from "./student-access.server";
import { InferenceUnavailable, queueInference, type InferenceContext } from "./inference.server";
import {
  recommendActivities,
  recommendStudyFormat,
  recommendWorld,
  type StudyAttempt,
} from "./study";
import { learnerPreferencesSchema } from "./personalization";
import type { StudyPriority } from "./priority";
import {
  activitiesFor,
  allowedAccessory,
  checkAnswer,
  commandSchema,
  defaultWorld,
  isAssessment,
  missionSchema,
  publicActivity,
  supportsCards,
  type Activity,
  type Mission,
  type Phase,
} from "./schema";

type Actor =
  | { kind: "teacher"; teacherId: string; home: boolean }
  | { kind: "learner"; learnerId: string; loginHash: string; classId: string };
type Sql = ReturnType<typeof db>;
const hash = (v: string) => createHash("sha256").update(v).digest("hex");
const secret = () => randomBytes(32).toString("base64url");
type RequestScope = {
  teacher?: string;
  learner?: string;
  class?: string;
  login?: string;
  code?: string;
  service?: string;
};
const requestScope = new AsyncLocalStorage<RequestScope>();
const transactions = new WeakSet<object>();
function scope() {
  const s = requestScope.getStore();
  if (!s) throw new Error("Missing request database scope");
  return s;
}
async function setScope(q: Sql) {
  const s = scope();
  await q.unsafe(
    "SELECT set_config('peluqo.teacher',$1,true),set_config('peluqo.learner',$2,true),set_config('peluqo.class',$3,true),set_config('peluqo.login',$4,true),set_config('peluqo.code',$5,true),set_config('peluqo.service',$6,true)",
    [s.teacher ?? "", s.learner ?? "", s.class ?? "", s.login ?? "", s.code ?? "", s.service ?? ""],
  );
}
const read = async <T extends Row = Row>(
  q: Sql,
  sql: string,
  args: unknown[] = [],
): Promise<T[]> => {
  if (transactions.has(q)) {
    await setScope(q);
    return Array.from(await q.unsafe<T[]>(sql, args as never[]));
  }
  return q.begin(async (tx) => {
    const connection = tx as unknown as Sql;
    await setScope(connection);
    return Array.from(await connection.unsafe<T[]>(sql, args as never[]));
  }) as Promise<T[]>;
};
async function one(q: Sql, sql: string, args: unknown[] = []) {
  const r = await read(q, sql, args);
  if (!r[0]) throw new ApiError(404, "No disponible o no autorizado.");
  return r[0];
}
const trans = async <T>(fn: (q: Sql) => Promise<T>) =>
  db().begin(async (q) => {
    const connection = q as unknown as Sql;
    transactions.add(connection);
    try {
      return await fn(connection);
    } finally {
      transactions.delete(connection);
    }
  }) as Promise<T>;
const json = (v: unknown) => JSON.stringify(v);
function equal(a: string, b: string) {
  return timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
}
function cookie(request: Request) {
  return (
    request.headers
      .get("cookie")
      ?.split(";")
      .map((x) => x.trim())
      .find((x) => x.startsWith("peluqo_student="))
      ?.slice(15) ?? ""
  );
}
function cookieHeader(request: Request, token: string, maxAge?: number) {
  const secure = new URL(request.url).protocol === "https:" || process.env["VERCEL"] === "1";
  const parts = [`peluqo_student=${token}`, "HttpOnly", "SameSite=Strict", "Path=/"];
  if (maxAge !== undefined) parts.push(`Max-Age=${maxAge}`);
  if (secure) parts.push("Secure");
  return parts.join("; ");
}
async function actor(request: Request): Promise<Actor> {
  const bearer = request.headers.get("authorization");
  const home = request.headers.get("x-peluqo-space") === "home";
  if (home || bearer?.startsWith("Bearer ")) {
    const account = await adultAccount(request, home ? undefined : "teacher");
    const teacherId = home ? await resolveHomeStudio(account) : account;
    scope().teacher = teacherId;
    if (!home) await one(db(), "SELECT id FROM education.teachers WHERE id=$1", [teacherId]);
    return { kind: "teacher", teacherId, home };
  }
  const token = cookie(request);
  if (!token) throw new ApiError(401, "Entra con tu código individual.");
  scope().login = hash(token);
  const login = await one(
    db(),
    "SELECT learner_id,hash FROM education.logins WHERE hash=$1 AND NOT revoked AND expires_at>now()",
    [hash(token)],
  );
  scope().learner = login["learner_id"];
  const l = await one(db(), "SELECT * FROM education.learners WHERE id=$1", [login["learner_id"]]);
  scope().class = l["class_id"];
  return { kind: "learner", learnerId: l["id"], classId: l["class_id"], loginHash: login["hash"] };
}
function teacher(a: Actor) {
  if (a.kind !== "teacher") throw new ApiError(403, "Esta acción corresponde al docente.");
  return a.teacherId;
}
function learner(a: Actor) {
  if (a.kind !== "learner") throw new ApiError(403, "Entra como alumno para comenzar.");
  return a;
}
async function classroom(q: Sql, a: Actor, id: string) {
  return one(q, "SELECT * FROM education.classes WHERE id=$1 AND teacher_id=$2", [id, teacher(a)]);
}
async function pupil(q: Sql, a: Actor, id: string) {
  return one(
    q,
    "SELECT l.* FROM education.learners l JOIN education.classes c ON c.id=l.class_id WHERE l.id=$1 AND c.teacher_id=$2",
    [id, teacher(a)],
  );
}
async function session(q: Sql, a: Actor, id: string, lock = false) {
  const l = learner(a);
  return one(
    q,
    `SELECT s.*,v.mission FROM education.sessions s JOIN education.versions v ON v.id=s.version_id JOIN education.logins g ON g.hash=s.login_hash WHERE s.id=$1 AND s.learner_id=$2 AND s.login_hash=$3 AND NOT g.revoked AND g.expires_at>now()${lock ? " FOR UPDATE OF s" : ""}`,
    [id, l.learnerId, l.loginHash],
  );
}
function activity(s: Row, id: string): Activity {
  const m = missionSchema.parse(s["mission"]);
  const a = activitiesFor(m, s["phase"] as Phase).find((a) => a.id === id);
  if (!a) throw new ApiError(409, "La actividad no pertenece a la fase actual.");
  return a;
}
async function emit(q: Sql, id: string, type: string, payload: unknown) {
  const context = await one(q, "SELECT phase,active_activity FROM education.sessions WHERE id=$1", [
    id,
  ]);
  payload = {
    ...(payload as Record<string, unknown>),
    phase: context["phase"],
    activityId: (payload as Record<string, unknown>)["activityId"] ?? context["active_activity"],
  };
  await read(q, "INSERT INTO education.events(session_id,type,payload) VALUES($1,$2,$3::jsonb)", [
    id,
    type,
    payload,
  ]);
}
async function throttle(q: Sql, key: string, limit: number) {
  const r = await one(
    q,
    `INSERT INTO education.throttle(key,count) VALUES($1,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN education.throttle.window_start<now()-interval '5 minutes' THEN 1 ELSE education.throttle.count+1 END,window_start=CASE WHEN education.throttle.window_start<now()-interval '5 minutes' THEN now() ELSE education.throttle.window_start END RETURNING count`,
    [key],
  );
  if (r["count"] > limit)
    throw new ApiError(429, "Espera unos minutos antes de volver a intentarlo.");
}
async function discoveries(q: Sql, id: string) {
  const r = await one(
    q,
    `SELECT count(DISTINCT (s.version_id,a.activity_id)) FILTER(WHERE a.id IS NOT NULL)::int AS discoveries,
      count(DISTINCT (s.version_id,a.activity_id)) FILTER(WHERE a.id IS NOT NULL AND a.hints=0)::int AS unaided,
      count(DISTINCT s.id) FILTER(WHERE s.completed_at IS NOT NULL)::int AS completed
      FROM education.sessions s LEFT JOIN education.attempts a ON a.session_id=s.id AND a.correct AND a.phase='practice' WHERE s.learner_id=$1`,
    [id],
  );
  return {
    discoveries: r["discoveries"] as number,
    unaided: r["unaided"] as number,
    completed: r["completed"] as number,
  };
}
async function validateSources(q: Sql, classId: string, m: Mission) {
  const ids = [
    ...new Set(
      [...m.diagnostic, ...m.practice, ...m.final, ...m.retention].flatMap((a) =>
        a.sources.map((s) => s.chunkId),
      ),
    ),
  ];
  const rows = await read(
    q,
    "SELECT ch.id,ch.page FROM education.chunks ch JOIN education.documents d ON d.id=ch.document_id WHERE d.class_id=$1 AND ch.id=ANY($2::uuid[])",
    [classId, ids],
  );
  const valid = new Map(rows.map((r) => [r["id"], r["page"]]));
  for (const a of [...m.diagnostic, ...m.practice, ...m.final, ...m.retention])
    for (const s of a.sources)
      if (!valid.has(s.chunkId) || valid.get(s.chunkId) !== s.page)
        throw new ApiError(
          400,
          "Hay una referencia que no pertenece a los materiales de esta clase.",
        );
}
async function ai(path: string, body: unknown, context: InferenceContext = {}) {
  if (process.env["PELUQO_INFERENCE_QUEUE"] === "1") {
    try {
      return await queueInference(path, body, context);
    } catch (error) {
      throw new ApiError(
        503,
        error instanceof InferenceUnavailable && error.reason === "usage_limit"
          ? "El servicio de IA ha alcanzado su cuota temporal. Vuelve a intentarlo cuando se renueve. Tus aventuras publicadas siguen disponibles."
          : "Peluqo no pudo preparar la respuesta. Puedes seguir con las actividades publicadas.",
      );
    }
  }
  const url = process.env["PELUQO_AI_URL"],
    key = process.env["PELUQO_INTEGRATION_KEY"];
  if (!url || !key) throw new ApiError(503, "El servicio educativo del NAS no está conectado.");
  const response = await fetch(url + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: json(body),
    signal: AbortSignal.timeout(600000),
  });
  if (!response.ok)
    throw new ApiError(
      503,
      "El NAS no ha podido completar la solicitud. Tus materiales publicados siguen disponibles.",
    );
  return response.json();
}
async function sources(q: Sql, sessionRow: Row, question: string): Promise<Row[]> {
  const rows = await read(
    q,
    `SELECT ch.id,ch.page,ch.content,d.name FROM education.chunks ch JOIN education.documents d ON d.id=ch.document_id WHERE d.class_id=(SELECT class_id FROM education.versions WHERE id=$1) AND ch.id=ANY($2::uuid[])`,
    [
      sessionRow["version_id"],
      [
        ...new Set(
          [
            ...sessionRow["mission"].diagnostic,
            ...sessionRow["mission"].practice,
            ...sessionRow["mission"].final,
            ...sessionRow["mission"].retention,
          ].flatMap((a: Activity) => a.sources.map((s) => s.chunkId)),
        ),
      ],
    ],
  );
  const words = question.toLocaleLowerCase("es").match(/[\p{L}]{4,}/gu) ?? [];
  return rows
    .map((r) => ({
      ...r,
      rank: words.filter((w) => r["content"].toLocaleLowerCase("es").includes(w)).length,
    }))
    .sort((a, b) => b.rank - a.rank)
    .slice(0, 6)
    .map(({ rank, ...r }) => r);
}

async function recentSessions(q: Sql, l: ReturnType<typeof learner>) {
  return read(
    q,
    "SELECT id,version_id,phase,completed_at,retention_completed_at FROM education.sessions WHERE learner_id=$1 AND login_hash=$2 ORDER BY opened_at DESC,created_at DESC",
    [l.learnerId, l.loginHash],
  );
}

async function curiosity(a: Actor, question: string, requestId: string) {
  const l = learner(a);
  const current = (await recentSessions(db(), l))[0];
  if (isAssessment(current?.["phase"]))
    throw new ApiError(
      403,
      "Termina las preguntas de esta etapa para volver a conversar con Peluqo.",
    );
  const existing = (
    await read(
      db(),
      "SELECT id,question,text,kind,sources FROM education.curiosity_turns WHERE id=$1 AND learner_id=$2",
      [requestId, l.learnerId],
    )
  )[0];
  if (existing) {
    if (existing["question"] !== question)
      throw new ApiError(409, "Ese identificador ya se utilizó.");
    return existing;
  }
  await throttle(db(), "tutor:" + l.learnerId, 20);
  const history = await read(
    db(),
    "SELECT question,left(text,450) AS text FROM education.curiosity_turns WHERE learner_id=$1 ORDER BY created_at DESC LIMIT 2",
    [l.learnerId],
  );
  const refs = current ? await sources(db(), await session(db(), l, current["id"]), question) : [];
  const reply = await ai(
    "/curiosity",
    { question, sources: refs, history: history.reverse() },
    { classId: l.classId, learnerId: l.learnerId },
  );
  if (
    !reply ||
    typeof reply.text !== "string" ||
    !reply.text.trim() ||
    reply.text.length > 1800 ||
    !["general", "material", "guidance"].includes(reply.kind) ||
    !Array.isArray(reply.sourceIds) ||
    reply.sourceIds.some((id: unknown) => !refs.some((r) => r["id"] === id))
  )
    throw new ApiError(502, "Peluqo necesita volver a preparar la respuesta.");
  const used =
    reply.kind === "material"
      ? refs
          .filter((r) => reply.sourceIds.includes(r["id"]))
          .map((r) => ({ chunkId: r["id"], page: r["page"], name: r["name"] }))
      : [];
  if (reply.kind === "material" && !used.length)
    throw new ApiError(502, "Peluqo necesita comprobar la fuente.");
  return trans(async (q) => {
    await one(
      q,
      "SELECT hash FROM education.logins WHERE hash=$1 AND NOT revoked AND expires_at>now()",
      [l.loginHash],
    );
    const live = (await recentSessions(q, l))[0];
    if (live?.["id"] !== current?.["id"] || isAssessment(live?.["phase"]))
      throw new ApiError(409, "La etapa ha cambiado. Vuelve a preguntar cuando termines.");
    await read(
      q,
      "INSERT INTO education.curiosity_turns(id,learner_id,question,text,kind,sources) VALUES($1,$2,$3,$4,$5,$6::jsonb) ON CONFLICT(id) DO NOTHING",
      [requestId, l.learnerId, question, reply.text.trim(), reply.kind, used],
    );
    const saved = await one(
      q,
      "SELECT id,question,text,kind,sources FROM education.curiosity_turns WHERE id=$1 AND learner_id=$2",
      [requestId, l.learnerId],
    );
    if (saved["question"] !== question) throw new ApiError(409, "Ese identificador ya se utilizó.");
    return saved;
  });
}
async function tutor(a: Actor, sessionId: string, question: string, requestId: string) {
  const s = await session(db(), a, sessionId);
  const existing = await read(db(), "SELECT * FROM education.turns WHERE id=$1 AND session_id=$2", [
    requestId,
    s["id"],
  ]);
  if (existing[0]) {
    if (existing[0]["question"] !== question)
      throw new ApiError(409, "Ese identificador ya se utilizó.");
    if (existing[0]["phase"] !== s["phase"] || existing[0]["activity_id"] !== s["active_activity"])
      throw new ApiError(409, "La etapa o la actividad ha cambiado. Vuelve a preguntar.");
    return existing[0];
  }
  await throttle(db(), "tutor:" + s["learner_id"], 20);
  let answer: { text: string; emotion: string; sourceIds: string[] };
  const refs = await sources(db(), s, question);
  if (s["phase"] !== "practice")
    answer = {
      text: "Ahora estamos comprobando lo que sabes sin ayuda. Puedo repetir las instrucciones; las pistas vuelven durante la práctica.",
      emotion: "think",
      sourceIds: [],
    };
  else
    answer = await ai(
      "/tutor",
      {
        question,
        sources: refs,
        companion: (
          await one(db(), "SELECT companion FROM education.learners WHERE id=$1", [s["learner_id"]])
        )["companion"],
        activity: activity(
          s,
          s["active_activity"] ?? activitiesFor(s["mission"], "practice")[0]?.id ?? "",
        ).instruction,
      },
      { classId: learner(a).classId, learnerId: learner(a).learnerId },
    );
  if (
    !answer ||
    typeof answer.text !== "string" ||
    !answer.text.trim() ||
    answer.text.length > 3000 ||
    !Array.isArray(answer.sourceIds) ||
    answer.sourceIds.some((id) => !refs.some((r) => r["id"] === id))
  )
    throw new ApiError(502, "La respuesta no contiene referencias válidas.");
  const used = refs
    .filter((r) => answer.sourceIds.includes(r["id"]))
    .map((r) => ({ chunkId: r["id"], page: r["page"], name: r["name"] }));
  if (s["phase"] === "practice" && !used.length)
    answer.text =
      "No encuentro esa información en los materiales aprobados. Pregunta al docente o prueba otra pregunta sobre esta misión.";
  return trans(async (q) => {
    const current = await session(q, a, s["id"], true);
    if (current["phase"] !== s["phase"] || current["active_activity"] !== s["active_activity"])
      throw new ApiError(409, "La etapa ha cambiado. Vuelve a preguntar.");
    const inserted = await read(
      q,
      `INSERT INTO education.turns(id,session_id,question,text,emotion,sources,activity_id,phase) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8) ON CONFLICT(id) DO NOTHING RETURNING id`,
      [
        requestId,
        s["id"],
        question,
        answer.text,
        ["happy", "think", "wow", "encourage"].includes(answer.emotion) ? answer.emotion : "think",
        used,
        s["active_activity"],
        s["phase"],
      ],
    );
    if (inserted.length && s["phase"] === "practice" && used.length)
      await read(
        q,
        "INSERT INTO education.hints(session_id,activity_id,kind) VALUES($1,$2,'tutor')",
        [s["id"], s["active_activity"] ?? activitiesFor(s["mission"], "practice")[0]!.id],
      );
    const saved = await one(q, "SELECT * FROM education.turns WHERE id=$1 AND session_id=$2", [
      requestId,
      s["id"],
    ]);
    if (saved["question"] !== question)
      throw new ApiError(409, "Solicitud repetida con otra pregunta.");
    return saved;
  });
}
async function state(a: Actor) {
  if (a.kind === "teacher") {
    const classes = await read(
      db(),
      "SELECT id,name,draft,created_at FROM education.classes WHERE teacher_id=$1 ORDER BY created_at",
      [a.teacherId],
    );
    const ids = classes.map((c) => c["id"]);
    return {
      role: "teacher",
      home: a.home,
      classes,
      learners: await read(
        db(),
        `SELECT l.*, (SELECT count(*)::int FROM education.family_links f WHERE f.learner_id=l.id) AS family_count
         FROM education.learners l WHERE l.class_id=ANY($1::uuid[]) ORDER BY l.name`,
        [ids],
      ),
      documents: await read(
        db(),
        "SELECT id,class_id,name,created_at FROM education.documents WHERE class_id=ANY($1::uuid[])",
        [ids],
      ),
      versions: await read(
        db(),
        "SELECT id,class_id,created_at,mission->>'title' AS title FROM education.versions WHERE class_id=ANY($1::uuid[]) ORDER BY created_at DESC",
        [ids],
      ),
      sessions: await read(
        db(),
        `SELECT s.id,s.learner_id,s.phase,s.version_id,s.completed_at,s.retention_completed_at,s.created_at
         FROM education.sessions s JOIN education.learners l ON l.id=s.learner_id WHERE l.class_id=ANY($1::uuid[])`,
        [ids],
      ),
      devices: await read(
        db(),
        "SELECT id,learner_id,session_id,revoked,last_seen_at FROM education.devices WHERE teacher_id=$1",
        [a.teacherId],
      ),
    };
  }
  const l = await one(
    db(),
    "SELECT id,name,companion,support,web_preferences FROM education.learners WHERE id=$1",
    [a.learnerId],
  );
  const preferences = learnerPreferencesSchema.parse(l["web_preferences"]);
  const [sessions, versions, priorityRow] = await Promise.all([
    recentSessions(db(), a),
    read<
      Parameters<typeof recommendWorld>[0][number] & {
        created_at: string;
        title: string;
        intro: string;
      }
    >(
      db(),
      `SELECT id,created_at,mission->>'title' AS title,mission->>'intro' AS intro,mission->>'subject' AS subject,
       mission->>'ageBand' AS age_band,mission->>'course' AS course,coalesce(mission->'world'->>'theme','reserve') AS theme
       FROM education.versions WHERE class_id=$1 ORDER BY created_at DESC`,
      [a.classId],
    ),
    one(db(), "SELECT education.student_study_priorities($1) AS priorities", [a.loginHash]),
  ]);
  const priorities = priorityRow["priorities"] as StudyPriority[];
  const current = sessions[0];
  let learning = null;
  if (current) {
    const s = await session(db(), a, current["id"]);
    const m = missionSchema.parse(s["mission"]);
    const recent =
      s["phase"] === "practice"
        ? ((await read(
            db(),
            `SELECT a.session_id,a.activity_id,a.competency,a.correct,a.hints,a.study_format,m.item->>'type' AS game
           FROM education.attempts a JOIN education.sessions s ON s.id=a.session_id JOIN education.versions v ON v.id=s.version_id
           LEFT JOIN LATERAL (SELECT item FROM jsonb_array_elements(v.mission->'practice') item WHERE item->>'id'=a.activity_id LIMIT 1) m ON true
           WHERE s.learner_id=$1 AND a.phase='practice' ORDER BY a.created_at DESC,a.id DESC LIMIT 80`,
            [a.learnerId],
          )) as StudyAttempt[])
        : [];
    learning = {
      id: current["id"],
      version_id: current["version_id"],
      phase: current["phase"],
      completed_at: current["completed_at"],
      retention_completed_at: current["retention_completed_at"],
      title: m.title,
      subject: m.subject ?? null,
      intro: m.intro,
      world: isAssessment(s["phase"])
        ? null
        : (m.world ?? defaultWorld(m.practice, m.title === "La expedición de los vertebrados")),
      activities: activitiesFor(m, s["phase"] as Phase).map(publicActivity),
      studyRecommendations:
        s["phase"] === "practice"
          ? Object.fromEntries(
              m.practice.map((item) => [
                item.id,
                recommendStudyFormat(s["id"], item.id, l["support"], recent),
              ]),
            )
          : {},
      recommendations:
        s["phase"] === "practice"
          ? recommendActivities(s["id"], m.practice, recent, preferences, priorities, l["support"])
          : [],
      attempts: await read(
        db(),
        "SELECT activity_id,phase,CASE WHEN phase='practice' THEN correct END AS correct,hints,created_at FROM education.attempts WHERE session_id=$1 ORDER BY created_at",
        [s["id"]],
      ),
      hints: await read(
        db(),
        "SELECT activity_id,count(*)::int AS count FROM education.hints WHERE session_id=$1 GROUP BY activity_id",
        [s["id"]],
      ),
      turns:
        s["phase"] === "practice" || s["phase"] === "completed"
          ? await read(
              db(),
              "SELECT id,question,text,sources FROM education.turns WHERE session_id=$1 ORDER BY created_at",
              [s["id"]],
            )
          : [],
    };
  }
  return {
    role: "learner",
    learner: { ...l, web_preferences: preferences },
    progress: await discoveries(db(), a.learnerId),
    learning,
    worldsInProgress: sessions.map((s) => ({ versionId: s["version_id"], phase: s["phase"] })),
    curiosity: isAssessment(current?.["phase"])
      ? []
      : await read(
          db(),
          "SELECT id,question,text,kind,sources FROM education.curiosity_turns WHERE learner_id=$1 ORDER BY created_at DESC LIMIT 20",
          [a.learnerId],
        ),
    versions,
    recommendedWorld: !isAssessment(current?.["phase"])
      ? recommendWorld(
          versions,
          sessions.map((s) => s["version_id"]),
          preferences,
          priorities,
        )
      : null,
    devices: await read(
      db(),
      "SELECT id,session_id,last_seen_at FROM education.devices WHERE learner_id=$1 AND NOT revoked",
      [a.learnerId],
    ),
  };
}
async function upload(request: Request, a: Actor) {
  const form = await request.formData();
  const classId = String(form.get("classId") ?? "");
  await classroom(db(), a, classId);
  const f = form.get("file");
  const maxMb =
    process.env["VERCEL"] === "1" || process.env["PELUQO_INFERENCE_QUEUE"] === "1" ? 4 : 10;
  if (!(f instanceof File) || f.size < 1 || f.size > maxMb * 1024 * 1024)
    throw new ApiError(400, `Selecciona un PDF digital o TXT de hasta ${maxMb} MB.`);
  const bytes = Buffer.from(await f.arrayBuffer());
  let pages: string[];
  if (f.name.toLowerCase().endsWith(".txt")) pages = [bytes.toString("utf8")];
  else if (f.name.toLowerCase().endsWith(".pdf") && bytes.subarray(0, 5).toString() === "%PDF-") {
    const { extractText, getDocumentProxy } = await import("unpdf");
    const pdf = await getDocumentProxy(new Uint8Array(bytes));
    try {
      if (pdf.numPages > 100) throw new ApiError(400, "Máximo 100 páginas.");
      pages = (await extractText(pdf, { mergePages: false })).text;
    } finally {
      await (pdf as unknown as { destroy?: () => Promise<void> }).destroy?.();
    }
  } else throw new ApiError(400, "Solo se admiten PDF digital o TXT.");
  if (!pages.join("").trim() || pages.join("").length > 300000)
    throw new ApiError(
      400,
      "No hay texto extraíble o supera 300.000 caracteres. Los PDF escaneados necesitan OCR y no se admiten todavía.",
    );
  return trans(async (q) => {
    const d = await one(
      q,
      "INSERT INTO education.documents(class_id,name,mime,bytes) VALUES($1,$2,$3,$4) RETURNING id",
      [
        classId,
        f.name.slice(0, 150),
        f.name.endsWith(".txt") ? "text/plain" : "application/pdf",
        bytes,
      ],
    );
    for (let p = 0; p < pages.length; p++)
      for (let i = 0; i < (pages[p]?.length ?? 0); i += 1200) {
        const content = pages[p]!.slice(i, i + 1400).trim();
        if (content)
          await read(q, "INSERT INTO education.chunks(document_id,page,content) VALUES($1,$2,$3)", [
            d["id"],
            f.name.endsWith(".txt") ? null : p + 1,
            content,
          ]);
      }
    return { documentId: d["id"] };
  });
}
const schoolOnlyActions = new Set([
  "assign-device-lesson",
  "issue-code",
  "issue-family-code",
  "revoke-family-access",
  "approve-pair",
  "bind-device",
  "revoke-device",
]);
async function command(
  request: Request,
  a: Actor,
  c: ReturnType<typeof commandSchema.parse>,
): Promise<unknown> {
  if (a.kind === "teacher" && a.home && schoolOnlyActions.has(c.action))
    throw new ApiError(403, "Esta opción está disponible en el aula escolar.");
  switch (c.action) {
    case "assign-device-lesson": {
      await pupil(db(), a, c.learnerId);
      return one(
        db(),
        `INSERT INTO education.device_lessons(teacher_id,learner_id,title,subject,goal,instructions,due_at,factors)
         VALUES($1,$2,$3,$4,$5,$6,$7::date,$8::jsonb) RETURNING id,lesson_id`,
        [teacher(a), c.learnerId, c.title, c.subject, c.goal, c.instructions, c.dueAt, c.factors],
      );
    }
    case "create-class":
      return one(
        db(),
        "INSERT INTO education.classes(teacher_id,name) VALUES($1,$2) RETURNING id",
        [teacher(a), c.name],
      );
    case "create-learner":
      await classroom(db(), a, c.classId);
      return one(db(), "INSERT INTO education.learners(class_id,name) VALUES($1,$2) RETURNING id", [
        c.classId,
        c.name,
      ]);
    case "delete-learner":
      return trans(async (q) => {
        await pupil(q, a, c.learnerId);
        await read(
          q,
          "UPDATE education.devices SET revoked=true,session_id=NULL WHERE learner_id=$1",
          [c.learnerId],
        );
        await read(q, "DELETE FROM education.learners WHERE id=$1", [c.learnerId]);
        return { ok: true };
      });
    case "document-source":
      return read(
        db(),
        "SELECT ch.id,ch.page,ch.content FROM education.chunks ch JOIN education.documents d ON d.id=ch.document_id JOIN education.classes c ON c.id=d.class_id WHERE d.id=$1 AND c.teacher_id=$2 ORDER BY ch.page NULLS FIRST,ch.id",
        [c.documentId, teacher(a)],
      );
    case "issue-code":
      return legacyStudentCode(teacher(a), c.learnerId);
    case "issue-family-code": {
      const owner = teacher(a);
      const familyCode = "F" + randomAccessCode();
      const result = await one(db(), "SELECT education.issue_family_code($1,$2,$3) AS allowed", [
        owner,
        c.learnerId,
        hash(familyCode),
      ]);
      if (!result["allowed"]) throw new ApiError(404, "No se encontró al alumno de tu clase.");
      return { code: "F-" + familyCode.slice(1) };
    }
    case "revoke-family-access": {
      const result = await one(db(), "SELECT education.revoke_family_links($1,$2) AS allowed", [
        teacher(a),
        c.learnerId,
      ]);
      if (!result["allowed"]) throw new ApiError(404, "No se encontró al alumno de tu clase.");
      return { ok: true };
    }
    case "generate": {
      await classroom(db(), a, c.classId);
      const chunks = await read(
        db(),
        "SELECT ch.id,ch.page,ch.content FROM education.chunks ch JOIN education.documents d ON d.id=ch.document_id WHERE d.id=$1 AND d.class_id=$2 ORDER BY ch.page NULLS FIRST,ch.id",
        [c.documentId, c.classId],
      );
      if (!chunks.length) throw new ApiError(400, "Procesa un material primero.");
      const proposal = await ai(
        "/generate",
        { sources: chunks, topic: c.topic ?? "" },
        { classId: c.classId },
      );
      if (proposal?.error === "material_insuficiente")
        throw new ApiError(
          400,
          "Elige un tema que aparezca en el material o añade otro documento.",
        );
      const generated = missionSchema.parse(proposal);
      await validateSources(db(), c.classId, generated);
      await read(
        db(),
        "UPDATE education.classes SET draft=$1::jsonb WHERE id=$2 AND teacher_id=$3",
        [generated, c.classId, teacher(a)],
      );
      return { draft: generated };
    }
    case "save-draft":
      await classroom(db(), a, c.classId);
      await validateSources(db(), c.classId, c.mission);
      await read(db(), "UPDATE education.classes SET draft=$1::jsonb WHERE id=$2", [
        c.mission,
        c.classId,
      ]);
      return { ok: true };
    case "publish":
      return trans(async (q) => {
        const cl = await classroom(q, a, c.classId);
        const m = missionSchema.parse(cl["draft"]);
        await validateSources(q, c.classId, m);
        return one(
          q,
          "INSERT INTO education.versions(class_id,mission) VALUES($1,$2::jsonb) RETURNING id",
          [c.classId, m],
        );
      });
    case "override":
      await pupil(db(), a, c.learnerId);
      await read(db(), "UPDATE education.learners SET support=$1 WHERE id=$2", [
        c.support,
        c.learnerId,
      ]);
      return { ok: true };
    case "start":
      return trans(async (q) => {
        const l = learner(a);
        await one(q, "SELECT id FROM education.versions WHERE id=$1 AND class_id=$2", [
          c.versionId,
          l.classId,
        ]);
        await one(q, "SELECT id FROM education.learners WHERE id=$1 FOR UPDATE", [l.learnerId]);
        const current = (await recentSessions(q, l))[0];
        if (isAssessment(current?.["phase"]) && current?.["version_id"] !== c.versionId)
          throw new ApiError(
            409,
            "Termina las preguntas de tu aventura antes de abrir otro mundo.",
          );
        const resume = (
          await read(
            q,
            "SELECT id FROM education.sessions WHERE learner_id=$1 AND login_hash=$2 AND version_id=$3 ORDER BY opened_at DESC LIMIT 1",
            [l.learnerId, l.loginHash, c.versionId],
          )
        )[0];
        if (resume) {
          await read(q, "UPDATE education.sessions SET opened_at=clock_timestamp() WHERE id=$1", [
            resume["id"],
          ]);
          return resume;
        }
        const s = await one(
          q,
          "INSERT INTO education.sessions(learner_id,login_hash,version_id) VALUES($1,$2,$3) RETURNING id",
          [l.learnerId, l.loginHash, c.versionId],
        );
        await emit(q, s["id"], "mission_started", {});
        return s;
      });
    case "ask":
      return curiosity(a, c.question, c.requestId);
    case "focus":
      return trans(async (q) => {
        const s = await session(q, a, c.sessionId, true);
        activity(s, c.activityId);
        await read(q, "UPDATE education.sessions SET active_activity=$1 WHERE id=$2", [
          c.activityId,
          s["id"],
        ]);
        return { ok: true };
      });
    case "answer":
      return trans(async (q) => {
        const s = await session(q, a, c.sessionId, true);
        const old = await read(
          q,
          "SELECT * FROM education.attempts WHERE session_id=$1 AND request_id=$2",
          [s["id"], c.requestId],
        );
        if (old[0]) {
          if (old[0]["study_format"] !== c.studyFormat)
            throw new ApiError(409, "Solicitud repetida con otro formato.");
          if (old[0]["activity_id"] !== c.activityId || json(old[0]["answer"]) !== json(c.answer)) {
            if (
              old[0]["activity_id"] !== c.activityId ||
              !Object.keys(c.answer).every((k) => old[0]!["answer"][k] === c.answer[k]) ||
              Object.keys(old[0]["answer"]).length !== Object.keys(c.answer).length
            )
              throw new ApiError(409, "Solicitud repetida con otra respuesta.");
          }
          return {
            correct: old[0]["phase"] === "practice" ? old[0]["correct"] : null,
            replayed: true,
          };
        }
        const ac = activity(s, c.activityId);
        const prior = await read(
          q,
          "SELECT correct FROM education.attempts WHERE session_id=$1 AND activity_id=$2",
          [s["id"], ac.id],
        );
        if ((s["phase"] !== "practice" && prior.length) || prior.some((p) => p["correct"]))
          throw new ApiError(409, "Esta respuesta ya quedó registrada.");
        const practice = s["phase"] === "practice";
        if (c.studyFormat === "cards" && (!practice || !supportsCards(ac)))
          throw new ApiError(400, "El formato de práctica no se aplica a la evaluación.");
        const correct = checkAnswer(ac, c.answer);
        const h = await one(
          q,
          "SELECT count(*)::int AS n FROM education.hints WHERE session_id=$1 AND activity_id=$2",
          [s["id"], ac.id],
        );
        await read(
          q,
          "INSERT INTO education.attempts(session_id,request_id,activity_id,phase,competency,answer,correct,hints,study_format) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9)",
          [
            s["id"],
            c.requestId,
            ac.id,
            s["phase"],
            ac.competency,
            c.answer,
            correct,
            h["n"],
            c.studyFormat,
          ],
        );
        if (practice && !correct && prior.length >= 1)
          await read(
            q,
            "INSERT INTO education.hints(session_id,activity_id,kind) VALUES($1,$2,'automatic')",
            [s["id"], ac.id],
          );
        await emit(
          q,
          s["id"],
          "attempt_evaluated",
          practice
            ? {
                correct,
                mood: correct ? "happy" : "encourage",
                text: correct
                  ? "¡Lo has conseguido!"
                  : "Buena idea. Podemos probarlo de otra manera.",
              }
            : { mood: "think", text: "He guardado tu respuesta." },
        );
        return {
          correct: practice ? correct : null,
          explanation: practice
            ? correct
              ? ac.explanation
              : "Podemos intentarlo otra vez. " + (prior.length >= 1 ? ac.hints[0] : "")
            : "Respuesta registrada.",
          support: practice && !correct && prior.length >= 1,
          challenge: practice && correct && prior.length === 0 && h["n"] === 0,
        };
      });
    case "hint":
      return trans(async (q) => {
        const s = await session(q, a, c.sessionId, true);
        if (s["phase"] !== "practice")
          throw new ApiError(403, "Las evaluaciones se realizan sin pistas.");
        const ac = activity(s, c.activityId);
        const n = await one(
          q,
          "SELECT count(*)::int AS n FROM education.hints WHERE session_id=$1 AND activity_id=$2",
          [s["id"], ac.id],
        );
        const hint = ac.hints[Math.min(n["n"], ac.hints.length - 1)]!;
        await read(q, "INSERT INTO education.hints(session_id,activity_id) VALUES($1,$2)", [
          s["id"],
          ac.id,
        ]);
        await emit(q, s["id"], "hint_requested", { mood: "think", text: hint });
        return { hint };
      });
    case "advance":
      return trans(async (q) => {
        const s = await session(q, a, c.sessionId, true);
        if (s["phase"] === "completed") {
          if (
            new Date(s["completed_at"]).getTime() + 7 * 86400000 > Date.now() ||
            s["retention_completed_at"]
          )
            throw new ApiError(409, "El repaso diferido estará disponible siete días después.");
          await read(
            q,
            "UPDATE education.sessions SET phase='retention',active_activity=NULL WHERE id=$1",
            [s["id"]],
          );
          return { ok: true };
        }
        const items = activitiesFor(s["mission"], s["phase"]);
        const done = await read(
          q,
          "SELECT DISTINCT activity_id FROM education.attempts WHERE session_id=$1 AND phase=$2 AND ($2<>'practice' OR correct)",
          [s["id"], s["phase"]],
        );
        if (!items.every((i) => done.some((r) => r["activity_id"] === i.id)))
          throw new ApiError(409, "Completa las actividades de esta etapa.");
        const next =
          s["phase"] === "diagnostic"
            ? "practice"
            : s["phase"] === "practice"
              ? "final"
              : "completed";
        await read(
          q,
          `UPDATE education.sessions SET phase=$1,active_activity=NULL,completed_at=CASE WHEN $2='final' THEN now() ELSE completed_at END,retention_completed_at=CASE WHEN $2='retention' THEN now() ELSE retention_completed_at END WHERE id=$3`,
          [next, s["phase"], s["id"]],
        );
        await emit(q, s["id"], next === "completed" ? "mission_completed" : "phase_changed", {
          phase: next,
          mood: "happy",
          text:
            next === "completed"
              ? "¡Expedición completada! Hemos descubierto mucho juntos."
              : "Vamos a la siguiente etapa.",
        });
        return { ok: true };
      });
    case "preferences": {
      const l = learner(a);
      const preferences = learnerPreferencesSchema.parse(c.preferences);
      await read(db(), "UPDATE education.learners SET web_preferences=$1::jsonb WHERE id=$2", [
        preferences,
        l.learnerId,
      ]);
      return { ok: true };
    }
    case "companion":
      return trans(async (q) => {
        const l = learner(a);
        const p = await discoveries(q, l.learnerId);
        if (!allowedAccessory(c.companion.accessory, p.discoveries, p.completed))
          throw new ApiError(403, "Ese accesorio todavía no se ha desbloqueado.");
        await read(q, "UPDATE education.learners SET companion=$1::jsonb WHERE id=$2", [
          c.companion,
          l.learnerId,
        ]);
        const sessions = await read(
          q,
          "SELECT id FROM education.sessions WHERE learner_id=$1 AND login_hash=$2",
          [l.learnerId, l.loginHash],
        );
        for (const s of sessions) await emit(q, s["id"], "appearance_changed", c.companion);
        return { ok: true };
      });
    case "tutor":
      return tutor(a, c.sessionId, c.question, c.requestId);
    case "approve-pair":
      return trans(async (q) => {
        const l = await pupil(q, a, c.learnerId);
        const p = await one(
          q,
          "SELECT * FROM education.pairings WHERE code_hash=$1 AND expires_at>now() AND device_id IS NULL FOR UPDATE",
          [hash(c.code.toUpperCase())],
        );
        const token = deviceToken(p["secret_hash"], p["id"]);
        const d = await one(
          q,
          "INSERT INTO education.devices(teacher_id,learner_id,token_hash) VALUES($1,$2,$3) RETURNING id",
          [teacher(a), l["id"], hash(token)],
        );
        await read(q, "UPDATE education.pairings SET device_id=$1 WHERE id=$2", [d["id"], p["id"]]);
        return { deviceId: d["id"] };
      });
    case "bind-device":
      return trans(async (q) => {
        if (a.kind === "learner") {
          await one(
            q,
            "SELECT hash FROM education.logins WHERE hash=$1 AND learner_id=$2 AND NOT revoked AND expires_at>now() FOR SHARE",
            [a.loginHash, a.learnerId],
          );
          if (c.sessionId) await session(q, a, c.sessionId, true);
        }
        const d = await one(
          q,
          a.kind === "learner"
            ? "SELECT * FROM education.devices WHERE id=$1 AND learner_id=$2 AND NOT revoked FOR UPDATE"
            : "SELECT * FROM education.devices WHERE id=$1 AND teacher_id=$2 AND NOT revoked FOR UPDATE",
          [c.deviceId, a.kind === "learner" ? a.learnerId : teacher(a)],
        );
        if (c.sessionId) {
          await one(
            q,
            `SELECT s.id FROM education.sessions s JOIN education.logins l ON l.hash=s.login_hash WHERE s.id=$1 AND s.learner_id=$2 AND NOT l.revoked AND l.expires_at>now()`,
            [c.sessionId, d["learner_id"]],
          );
        }
        if (d["session_id"] !== c.sessionId) {
          await read(
            q,
            "UPDATE education.devices SET session_id=$1,ack=(SELECT coalesce(max(seq),0) FROM education.events WHERE session_id=$1) WHERE id=$2",
            [c.sessionId, d["id"]],
          );
          if (c.sessionId)
            await emit(q, c.sessionId, "device_activated", {
              text: "Ya estoy contigo. Elige un reto en la web.",
              mood: "happy",
            });
        }
        return { ok: true };
      });
    case "revoke-device":
      await read(
        db(),
        "UPDATE education.devices SET revoked=true,session_id=NULL WHERE id=$1 AND teacher_id=$2",
        [c.deviceId, teacher(a)],
      );
      return { ok: true };
    default:
      throw new ApiError(400, "Acción no válida.");
  }
}
function deviceToken(pendingHash: string, id: string) {
  const key = process.env["PELUQO_PAIRING_KEY"];
  if (!key) throw new ApiError(503, "Emparejamiento no configurado.");
  return createHmac("sha256", key)
    .update(pendingHash + id)
    .digest("base64url");
}
async function device(request: Request) {
  const key = process.env["PELUQO_INTEGRATION_KEY"];
  if (!key || !equal(request.headers.get("x-integration-key") ?? "", key))
    throw new ApiError(401, "Conector no autorizado.");
  scope().service = "true";
  const b = (await request.json()) as Row;
  const q = db();
  if (b["action"] === "pair-start") {
    await throttle(q, "pair-start", 30);
    const text = randomAccessCode(8),
      pending = secret();
    await read(
      q,
      `INSERT INTO education.pairings(code_hash,secret_hash,expires_at) VALUES($1,$2,now()+interval '5 minutes')`,
      [hash(text), hash(pending)],
    );
    return { code: text, pending, expiresIn: 300 };
  }
  if (b["action"] === "pair-status") {
    if (typeof b["pending"] !== "string" || b["pending"].length > 100)
      throw new ApiError(400, "Solicitud no válida.");
    const p = await one(
      q,
      "SELECT p.*,d.revoked FROM education.pairings p LEFT JOIN education.devices d ON d.id=p.device_id WHERE p.secret_hash=$1 AND p.expires_at>now()",
      [hash(b["pending"])],
    );
    return p["device_id"] && !p["revoked"]
      ? { paired: true, token: deviceToken(p["secret_hash"], p["id"]) }
      : { paired: false };
  }
  const token = request.headers.get("authorization")?.replace(/^Bearer /, "") ?? "";
  const d = await one(q, "SELECT * FROM education.devices WHERE token_hash=$1 AND NOT revoked", [
    hash(token),
  ]);
  await read(q, "UPDATE education.devices SET last_seen_at=now() WHERE id=$1", [d["id"]]);
  if (b["action"] === "support-signal") {
    const signal = supportSignalSchema.parse(b);
    try {
      const receipt = await one(
        q,
        "SELECT education.ingest_support_signal($1,$2,$3,$4,$5,$6) AS result",
        [
          d["id"],
          signal.signalId,
          signal.category,
          signal.source,
          signal.schoolPeerContext,
          signal.childConfirmed,
        ],
      );
      return receipt["result"];
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error ? String(error.code) : "";
      if (code === "42501")
        throw new ApiError(
          403,
          "El acompañamiento familiar no está habilitado para este dispositivo.",
        );
      if (code === "23505") throw new ApiError(409, "La señal ya pertenece a otra petición.");
      if (code === "22023") throw new ApiError(400, "La señal de acompañamiento no es válida.");
      throw error;
    }
  }
  if (b["action"] === "lesson-result") {
    const result = deviceLessonResultSchema.parse(b);
    return trans(async (tx) => {
      await one(
        tx,
        "SELECT id FROM education.devices WHERE id=$1 AND NOT revoked AND learner_id=$2 FOR SHARE",
        [d["id"], d["learner_id"]],
      );
      const lesson = await one(
        tx,
        `SELECT a.* FROM education.device_lessons a JOIN education.learners l ON l.id=a.learner_id
         JOIN education.classes c ON c.id=l.class_id
         WHERE a.id=$1 AND a.lesson_id=$2 AND a.learner_id=$3 AND a.teacher_id=$4 AND c.teacher_id=$4`,
        [result.assignmentId, result.lessonId, d["learner_id"], d["teacher_id"]],
      );
      let evidence;
      try {
        evidence = evaluateDeviceLesson(lesson["factors"], result);
      } catch {
        throw new ApiError(400, "Las respuestas no corresponden a la actividad completada.");
      }
      const context = await one(tx, "SELECT education.device_school_context($1,$2) AS context", [
        d["learner_id"],
        d["teacher_id"],
      ]);
      if (context["context"]?.deviceSettings?.sharePractice === false)
        evidence = { ...evidence, answers: [], detailsShared: false };
      // Preserve receipt compatibility for legacy detailed deliveries without an explicit privacy flag.
      const canonicalResult = { ...result };
      if (canonicalResult.detailsShared !== false) {
        delete canonicalResult.detailsShared;
        delete canonicalResult.completedCount;
      }
      const requestHash = hash(json(canonicalResult));
      await read(
        tx,
        `INSERT INTO education.device_lesson_results(result_id,assignment_id,device_id,payload,request_hash,correct_count)
         VALUES($1,$2,$3,$4::jsonb,$5,$6) ON CONFLICT DO NOTHING`,
        [
          result.resultId,
          result.assignmentId,
          d["id"],
          evidence,
          requestHash,
          evidence.correctCount,
        ],
      );
      const saved = await one(
        tx,
        "SELECT result_id,assignment_id,device_id,request_hash,payload FROM education.device_lesson_results WHERE assignment_id=$1 OR result_id=$2",
        [result.assignmentId, result.resultId],
      );
      if (
        saved["result_id"] !== result.resultId ||
        saved["assignment_id"] !== result.assignmentId ||
        saved["device_id"] !== d["id"]
      )
        throw new ApiError(409, "Este resultado ya está registrado con datos diferentes.");
      if (saved["request_hash"] !== requestHash) {
        const minimized =
          result.detailsShared === false
            ? await one(
                tx,
                "SELECT education.minimize_device_receipt($1,$2,$3,$4,$5::jsonb) AS accepted",
                [d["id"], result.assignmentId, result.resultId, requestHash, evidence],
              )
            : null;
        if (!minimized?.["accepted"])
          throw new ApiError(409, "Este resultado ya está registrado con datos diferentes.");
      }
      return { accepted: true, resultId: result.resultId };
    });
  }
  if (b["action"] === "unpair") {
    await read(q, "UPDATE education.devices SET revoked=true,session_id=NULL WHERE id=$1", [
      d["id"],
    ]);
    return { ok: true };
  }
  let s: Row | undefined;
  if (d["session_id"]) {
    const rows = await read(
      q,
      "SELECT s.*,v.mission,l.class_id FROM education.sessions s JOIN education.versions v ON v.id=s.version_id JOIN education.learners l ON l.id=s.learner_id JOIN education.logins g ON g.hash=s.login_hash WHERE s.id=$1 AND NOT g.revoked AND g.expires_at>now()",
      [d["session_id"]],
    );
    s = rows[0];
  }
  if (b["action"] === "events") {
    const context = d["learner_id"]
      ? await one(q, "SELECT education.device_school_context($1,$2) AS context", [
          d["learner_id"],
          d["teacher_id"],
        ])
      : null;
    const lessons = d["learner_id"]
      ? await read(
          q,
          `SELECT a.id,a.lesson_id,a.title,a.instructions,a.factors FROM education.device_lessons a
       JOIN education.learners l ON l.id=a.learner_id JOIN education.classes c ON c.id=l.class_id
       WHERE a.learner_id=$1 AND a.teacher_id=$2 AND c.teacher_id=$2
       AND NOT EXISTS(SELECT FROM education.device_lesson_results r WHERE r.assignment_id=a.id)
       ORDER BY a.created_at,a.id LIMIT 1`,
          [d["learner_id"], d["teacher_id"]],
        )
      : [];
    const local = lessons[0];
    const groupContext = local
      ? await one(q, "SELECT education.device_group_context($1,$2,$3) AS context", [
          local["id"],
          d["learner_id"],
          d["teacher_id"],
        ])
      : null;
    const l = d["learner_id"]
      ? await one(q, "SELECT name,companion FROM education.learners WHERE id=$1", [d["learner_id"]])
      : null;
    const events = s
      ? await read(
          q,
          `SELECT seq::float8 AS seq,id,session_id,type,payload FROM education.events WHERE session_id=$1 AND seq>$2 AND created_at>now()-interval '30 seconds' ORDER BY seq LIMIT 20`,
          [s["id"], d["ack"]],
        )
      : [];
    return {
      ...(context?.["context"] ?? {}),
      v: 1,
      deviceId: d["id"],
      sessionId: s?.["id"] ?? null,
      phase: s?.["phase"] ?? null,
      activeActivity: s?.["active_activity"] ?? null,
      companion: l?.["companion"] ?? null,
      localLesson: local
        ? {
            id: local["lesson_id"],
            assignmentId: local["id"],
            title: local["title"],
            instructions: local["instructions"],
            kind: "multiplication",
            factors: local["factors"],
            ...(groupContext?.["context"] ?? {}),
          }
        : null,
      events,
    };
  }
  if (b["action"] === "ack") {
    if (!s || b["sessionId"] !== s["id"] || !Number.isSafeInteger(b["seq"]) || b["seq"] < 0)
      throw new ApiError(400, "Confirmación no válida.");
    await read(
      q,
      "UPDATE education.devices SET ack=greatest(ack,least($1,(SELECT coalesce(max(seq),0) FROM education.events WHERE session_id=$2))) WHERE id=$3",
      [b["seq"], s["id"], d["id"]],
    );
    return { ok: true };
  }
  if (!s) throw new ApiError(409, "El docente debe activar una sesión para este dispositivo.");
  if (b["action"] === "say-text") {
    if (typeof b["eventId"] !== "string" || b["eventId"].length !== 36)
      throw new ApiError(400, "Evento no válido.");
    const event = await one(
      q,
      "SELECT payload,type FROM education.events WHERE id=$1 AND session_id=$2 AND created_at>now()-interval '30 seconds'",
      [b["eventId"], s["id"]],
    );
    const payload = event["payload"];
    if (
      (payload.phase && payload.phase !== s["phase"]) ||
      (payload.activityId && s["active_activity"] && payload.activityId !== s["active_activity"]) ||
      (event["type"] === "hint_requested" && s["phase"] !== "practice")
    )
      throw new ApiError(404, "La pista ya no pertenece a la actividad actual.");
    return payload;
  }
  const who: Actor = {
    kind: "learner",
    learnerId: s["learner_id"],
    loginHash: s["login_hash"],
    classId: s["class_id"],
  };
  if (b["action"] === "turn") {
    const parsed = commandSchema.parse({
      action: "tutor",
      sessionId: s["id"],
      question: b["question"],
      requestId: b["requestId"],
    });
    if (parsed.action !== "tutor") throw new ApiError(400, "Turno no válido.");
    return tutor(who, s["id"], parsed.question, parsed.requestId);
  }
  throw new ApiError(400, "Acción de dispositivo no válida.");
}
export function handleEducation(request: Request, deviceRoute = false): Promise<Response> {
  return requestScope.run({}, () => handleScopedEducation(request, deviceRoute));
}
async function handleScopedEducation(request: Request, deviceRoute = false): Promise<Response> {
  const headers: Record<string, string> = { "Cache-Control": "no-store" };
  try {
    if (request.method !== "GET") {
      const origin = request.headers.get("origin");
      const expected = process.env["PELUQO_WEB_ORIGIN"] ?? new URL(request.url).origin;
      if (origin && origin !== expected) throw new ApiError(403, "Origen no autorizado.");
    }
    if (deviceRoute) return Response.json(await device(request), { headers });
    if (request.method === "GET")
      return Response.json(await state(await actor(request)), { headers });
    if (request.headers.get("content-type")?.includes("multipart/form-data"))
      return Response.json(await upload(request, await actor(request)), { headers });
    const c = commandSchema.parse(await request.json());
    if (c.action === "login") {
      const code = normalizeStudentCode(c.code);
      await throttle(db(), "login-global", 100);
      await throttle(db(), "login-code:" + hash(code), 8);
      const result = await openStudentLogin(code, {
        remember: c.remember,
        ...(c.learnerId ? { learnerId: c.learnerId } : {}),
      });
      headers["Set-Cookie"] = cookieHeader(
        request,
        result.token,
        c.remember ? result.maxAge : undefined,
      );
      return Response.json({ ok: true, profile: result.profile }, { headers });
    }
    if (c.action === "logout") {
      const token = cookie(request);
      scope().login = hash(token);
      const login = token
        ? await read(db(), "SELECT learner_id FROM education.logins WHERE hash=$1", [hash(token)])
        : [];
      if (login[0]) scope().learner = login[0]["learner_id"];
      if (token)
        await read(db(), "UPDATE education.logins SET revoked=true WHERE hash=$1", [hash(token)]);
      headers["Set-Cookie"] = cookieHeader(request, "", 0);
      return Response.json({ ok: true }, { headers });
    }
    return Response.json(await command(request, await actor(request), c), { headers });
  } catch (e) {
    const validation = e instanceof Error && e.name === "ZodError";
    const status = e instanceof ApiError ? e.status : validation ? 400 : 503;
    const message =
      e instanceof ApiError
        ? e.message
        : validation
          ? "Revisa el contenido: " + (e as Error).message.slice(0, 1200)
          : "No se pudo completar la operación educativa. Comprueba el servicio privado del NAS.";
    if (status >= 500)
      console.error("Education request failed", e instanceof Error ? e.name : "unknown");
    return Response.json({ error: message }, { status, headers });
  }
}
