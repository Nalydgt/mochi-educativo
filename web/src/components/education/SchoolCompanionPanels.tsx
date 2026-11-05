import { useState, type ReactNode } from "react";
import { HeartHandshake, ShieldCheck, Users } from "lucide-react";
import type { SchoolGroup, SchoolSnapshot } from "@/lib/education/school-schema";

type Run = <T = Record<string, unknown>>(
  payload: Record<string, unknown>,
  endpoint?: string,
) => Promise<T | null>;
type Props = { data: SchoolSnapshot; run: Run; busy: boolean; success: (text: string) => void };
const name = (data: SchoolSnapshot, id: string) =>
  data.learners.find((learner) => learner.id === id)?.name ?? "Estudiante";
const date = (value: string) =>
  new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", year: "numeric" }).format(
    new Date(value),
  );
function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="mw-panel">
      <div className="mw-panel-header">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}
function Field({
  label,
  children,
  full = false,
}: {
  label: string;
  children: ReactNode;
  full?: boolean;
}) {
  return (
    <label className={`mw-field${full ? " full" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function CarePanel({
  data,
  run,
  busy,
  success,
  configure,
}: Props & { configure: () => void }) {
  const [history, setHistory] = useState(false);
  if (data.role !== "family") return null;
  const alerts = (data.careAlerts ?? []).filter((alert) =>
    data.learners.some((learner) => learner.id === alert.learnerId),
  );
  const visible = alerts.filter((alert) => history || alert.status === "pending_review");
  return (
    <>
      <Section
        title="Un momento para conversar"
        description="Avisos privados para los adultos familiares vinculados a cada estudiante."
      >
        <div className="mw-care-intro">
          <HeartHandshake size={25} aria-hidden="true" />
          <div>
            <p>
              Una señal surgida al hablar con Mochi puede ayudaros a iniciar una conversación. Un
              aviso no confirma qué ha ocurrido.
            </p>
            <p className="mw-subtle">
              Aquí sólo se muestran el estudiante, la fecha y el estado del aviso. No se incluyen
              audios ni transcripciones. Cada adulto lo revisa por separado.
            </p>
          </div>
        </div>
        <div className="mw-care-preferences">
          {data.learners.map((learner) => (
            <p className="mw-list-row" key={learner.id}>
              <span>{learner.name}</span>
              <span className="mw-badge outline">
                {data.settings.find((setting) => setting.learnerId === learner.id)
                  ?.familySupportAlertsEnabled
                  ? "Avisos activados"
                  : "Avisos desactivados"}
              </span>
            </p>
          ))}
          <p className="mw-subtle">
            Los avisos están desactivados por defecto. Requieren que la familia los active y que el
            menor confirme que quiere compartir la señal.
          </p>
          <button className="mw-button small" onClick={configure}>
            Configurar avisos y privacidad
          </button>
        </div>
        <label className="mw-check">
          <input
            type="checkbox"
            checked={history}
            onChange={(event) => setHistory(event.target.checked)}
          />
          Mostrar también los avisos que he revisado
        </label>
      </Section>
      <Section title={history ? "Mis avisos de acompañamiento" : "Pendientes de revisar"}>
        {visible.length ? (
          visible.map((alert) => (
            <article className="mw-care-alert" key={alert.id}>
              <div className="mw-list-row">
                <div>
                  <h3>{name(data, alert.learnerId)}</h3>
                  <p className="mw-subtle">{date(alert.createdAt)}</p>
                </div>
                <span
                  className={`mw-badge ${alert.status === "pending_review" ? "warning" : "outline"}`}
                >
                  {alert.status === "pending_review"
                    ? "Por revisar"
                    : alert.status === "reviewed"
                      ? "Revisado por ti"
                      : "Descartado por ti"}
                </span>
              </div>
              <h3>Posible dificultad entre compañeros</h3>
              <p>
                Conviene hablar con calma para entender cómo se está sintiendo y qué ha pasado en su
                entorno escolar.
              </p>
              <div className="mw-form-actions">
                {alert.status === "pending_review" && (
                  <button
                    className="mw-button primary"
                    disabled={busy}
                    onClick={async () => {
                      if (
                        await run({
                          action: "review-care-alert",
                          alertId: alert.id,
                          status: "reviewed",
                        })
                      )
                        success(
                          "Has marcado el aviso como revisado. El estado de los otros adultos no cambia.",
                        );
                    }}
                  >
                    Marcar como revisado
                  </button>
                )}
                {alert.status !== "dismissed" && (
                  <button
                    className="mw-button"
                    disabled={busy}
                    onClick={async () => {
                      if (
                        await run({
                          action: "review-care-alert",
                          alertId: alert.id,
                          status: "dismissed",
                        })
                      )
                        success("Aviso descartado en tu espacio familiar.");
                    }}
                  >
                    Descartar aviso
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <div className="mw-empty">
            <ShieldCheck size={27} aria-hidden="true" />
            <h3>No hay avisos pendientes</h3>
            <p>Las señales de acompañamiento que se compartan con tu familia aparecerán aquí.</p>
          </div>
        )}
      </Section>
      <Section title="Cómo empezar a hablar">
        <p>
          Busca un momento tranquilo y escucha sin culpar ni dar por hecho lo ocurrido. Agradece que
          te lo cuente y acordad a qué adulto de confianza o persona del centro podéis pedir apoyo.
        </p>
        <p className="mw-subtle">
          Orientación para familias:{" "}
          <a
            href="https://www.unicef.org/egypt/bullying/tips-parents-bullied"
            target="_blank"
            rel="noopener noreferrer"
          >
            recomendaciones de UNICEF sobre acoso entre compañeros
          </a>
          .
        </p>
        <p className="mw-note">
          Este panel no establece diagnósticos ni sustituye la conversación y el acompañamiento de
          los adultos.
        </p>
      </Section>
    </>
  );
}

export function RecognitionPanel({
  data,
  pupilIds,
}: {
  data: SchoolSnapshot;
  pupilIds: Set<string>;
}) {
  const pupils = data.learners.filter((learner) => pupilIds.has(learner.id));
  const points = (data.points ?? []).filter((point) =>
    pupils.some((pupil) => pupil.id === point.learnerId),
  );
  const labels = {
    review: "Práctica revisada",
    group: "Colaboración del equipo",
    help: "Ayuda confirmada por el docente",
  };
  return (
    <>
      <Section
        title="Participación y colaboración"
        description="Puntos internos registrados por acciones educativas, sin clasificaciones entre estudiantes."
      >
        <div className="mw-recognition-rules">
          <p>
            <strong>10</strong>
            <span>Por actividad completada con revisión docente compartida.</span>
          </p>
          <p>
            <strong>20</strong>
            <span>Extra por miembro cuando todo el equipo tiene su revisión compartida.</span>
          </p>
          <p>
            <strong>5</strong>
            <span>Por una ayuda voluntaria confirmada por el docente.</span>
          </p>
        </div>
        <p className="mw-note">
          No cambian las calificaciones. No se comparan capacidades y no se restan puntos por
          equivocarse o descansar.
        </p>
      </Section>
      <Section title={data.role === "family" ? "El registro de tu familia" : "Registro del aula"}>
        {pupils.length ? (
          pupils.map((pupil) => {
            const rows = points
              .filter((point) => point.learnerId === pupil.id)
              .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
            return (
              <article className="mw-recognition-pupil" key={pupil.id}>
                <div className="mw-list-row">
                  <h3>{pupil.name}</h3>
                  <span className="mw-point-total">
                    {rows.reduce((sum, point) => sum + point.points, 0)}{" "}
                    <small>puntos internos</small>
                  </span>
                </div>
                {rows.length ? (
                  <ul className="mw-list">
                    {rows.map((point) => (
                      <li key={point.id}>
                        <div className="mw-list-row">
                          <div>
                            <strong>{labels[point.reason]}</strong>
                            <p className="mw-subtle">{date(point.createdAt)}</p>
                          </div>
                          <span className="mw-point-change">+{point.points}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mw-subtle">
                    Los reconocimientos aparecerán después de la revisión y confirmación del
                    docente.
                  </p>
                )}
              </article>
            );
          })
        ) : (
          <div className="mw-empty">
            <h3>Sin estudiantes en esta selección</h3>
            <p>Elige otra clase o vincula un estudiante para consultar su registro.</p>
          </div>
        )}
      </Section>
    </>
  );
}

type MemberDraft = {
  selected: boolean;
  peerRole: "member" | "helper";
  voluntary: boolean;
  buddyAlias: string;
};
function GroupForm({
  data,
  group,
  run,
  busy,
  success,
}: Props & { group?: SchoolGroup | undefined }) {
  const [classId, setClassId] = useState(group?.classId ?? data.classes[0]?.id ?? "");
  const [members, setMembers] = useState<Record<string, MemberDraft>>(() =>
    Object.fromEntries(
      (group?.members ?? []).map((member) => [
        member.learnerId,
        { ...member, selected: true, buddyAlias: member.buddyAlias ?? "" },
      ]),
    ),
  );
  const [error, setError] = useState("");
  const pupils = data.learners.filter((learner) => learner.classId === classId);
  const selected = pupils.filter((pupil) => members[pupil.id]?.selected);
  function update(id: string, patch: Partial<MemberDraft>) {
    setMembers((current) => ({
      ...current,
      [id]: {
        selected: false,
        peerRole: "member",
        voluntary: false,
        buddyAlias: "",
        ...current[id],
        ...patch,
      },
    }));
  }
  return (
    <form
      className="mw-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        const form = event.currentTarget;
        const fields = new FormData(form);
        if (selected.length < 2 || selected.length > 8) {
          setError("Elige entre dos y ocho estudiantes del mismo grupo clase.");
          return;
        }
        if (selected.some((pupil) => !members[pupil.id]?.voluntary)) {
          setError("Confirma la participación voluntaria de cada integrante antes de guardar.");
          return;
        }
        const payload = {
          action: "save-group",
          ...(group ? { groupId: group.id, expectedRevision: group.revision } : {}),
          classId,
          name: fields.get("name"),
          members: selected.map((pupil) => {
            const draft = members[pupil.id]!;
            return {
              learnerId: pupil.id,
              peerRole: draft.peerRole,
              voluntary: draft.voluntary,
              ...(draft.buddyAlias.trim() ? { buddyAlias: draft.buddyAlias.trim() } : {}),
            };
          }),
        };
        if (await run(payload)) {
          success(
            group
              ? "Grupo actualizado."
              : "Grupo creado. Ya puedes preparar una actividad compartida.",
          );
          if (!group) {
            setMembers({});
            form.reset();
          }
        }
      }}
    >
      <Field label="Clase">
        <select
          name="classId"
          value={classId}
          disabled={!!group}
          onChange={(event) => {
            setClassId(event.target.value);
            setMembers({});
          }}
        >
          {data.classes.map((item) => (
            <option value={item.id} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Nombre del grupo">
        <input
          name="name"
          required
          minLength={2}
          maxLength={60}
          defaultValue={group?.name ?? ""}
          placeholder="Por ejemplo, Equipo Girasol"
        />
      </Field>
      <fieldset className="mw-group-members mw-field full">
        <legend>Integrantes y participación voluntaria</legend>
        <p className="mw-subtle">
          Entre dos y ocho estudiantes. Acompañar es un papel voluntario y supervisado, sin
          etiquetas de capacidad.
        </p>
        {pupils.map((pupil) => {
          const draft = members[pupil.id];
          return (
            <div className="mw-group-member" key={pupil.id}>
              <label className="mw-check">
                <input
                  type="checkbox"
                  checked={draft?.selected ?? false}
                  onChange={(event) => update(pupil.id, { selected: event.target.checked })}
                />
                <strong>{pupil.name}</strong>
              </label>
              {draft?.selected && (
                <div className="mw-group-member-fields">
                  <Field label={`Participación de ${pupil.name}`}>
                    <select
                      value={draft.peerRole}
                      onChange={(event) =>
                        update(pupil.id, { peerRole: event.target.value as "member" | "helper" })
                      }
                    >
                      <option value="member">Participar en la actividad</option>
                      <option value="helper">Acompañar a un compañero</option>
                    </select>
                  </Field>
                  <Field label={`Alias para Mochi de ${pupil.name}`}>
                    <input
                      maxLength={16}
                      pattern={"[\\p{L}\\p{N} _\\-]+"}
                      value={draft.buddyAlias}
                      onChange={(event) => update(pupil.id, { buddyAlias: event.target.value })}
                      placeholder="Alias breve, sin apellidos"
                    />
                  </Field>
                  <label className="mw-check">
                    <input
                      type="checkbox"
                      checked={draft.voluntary}
                      onChange={(event) => update(pupil.id, { voluntary: event.target.checked })}
                    />
                    He confirmado su participación voluntaria.
                  </label>
                </div>
              )}
            </div>
          );
        })}
      </fieldset>
      {error && (
        <p className="mw-feedback error mw-field full" role="alert">
          {error}
        </p>
      )}
      <div className="mw-form-actions">
        <button className="mw-button primary" disabled={busy || !classId}>
          {busy ? "Guardando…" : group ? "Guardar grupo" : "Crear grupo"}
        </button>
        <p>{selected.length} integrantes seleccionados</p>
      </div>
    </form>
  );
}

function ConfirmHelp({ data, run, busy, success }: Props) {
  const [assignmentId, setAssignmentId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const eligible = data.lessons.filter(
    (lesson) =>
      lesson.peerRole === "helper" &&
      lesson.groupBatchId &&
      lesson.result &&
      lesson.review?.publishedAt &&
      !(data.points ?? []).some((point) => point.reason === "help" && point.sourceId === lesson.id),
  );
  const selected = eligible.find((lesson) => lesson.id === assignmentId);
  const recipients = selected
    ? data.lessons.filter(
        (lesson) =>
          lesson.groupBatchId === selected.groupBatchId &&
          lesson.learnerId !== selected.learnerId &&
          lesson.result &&
          lesson.review?.publishedAt,
      )
    : [];
  return (
    <Section
      title="Confirmar una ayuda realizada"
      description="La práctica de ambos estudiantes debe estar revisada y compartida antes de registrar una ayuda."
    >
      {eligible.length ? (
        <form
          className="mw-form"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!confirmed || !selected) return;
            const fields = new FormData(event.currentTarget);
            if (
              await run({
                action: "confirm-help",
                assignmentId: selected.id,
                helpedLearnerId: fields.get("helpedLearnerId"),
              })
            ) {
              setAssignmentId("");
              setConfirmed(false);
              success(
                "Ayuda confirmada. El registro añade 5 puntos una sola vez por actividad de acompañamiento.",
              );
            }
          }}
        >
          <Field label="Actividad de quien ha acompañado">
            <select
              value={assignmentId}
              required
              onChange={(event) => {
                setAssignmentId(event.target.value);
                setConfirmed(false);
              }}
            >
              <option value="">Selecciona una actividad revisada</option>
              {eligible.map((lesson) => (
                <option key={lesson.id} value={lesson.id}>
                  {lesson.learnerName} · {lesson.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Estudiante acompañado">
            <select name="helpedLearnerId" required key={assignmentId} defaultValue="">
              <option value="">Selecciona al compañero</option>
              {recipients.map((lesson) => (
                <option value={lesson.learnerId} key={lesson.id}>
                  {lesson.learnerName}
                </option>
              ))}
            </select>
          </Field>
          <label className="mw-check mw-field full">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Confirmo que la ayuda se ha realizado de forma voluntaria y bajo supervisión docente.
          </label>
          <div className="mw-form-actions">
            <button
              className="mw-button primary"
              disabled={busy || !confirmed || !recipients.length}
            >
              Confirmar ayuda
            </button>
          </div>
        </form>
      ) : (
        <div className="mw-empty">
          <HeartHandshake size={27} aria-hidden="true" />
          <h3>Aún no hay ayudas pendientes de confirmar</h3>
          <p>
            Asigna una actividad a un equipo con acompañamiento voluntario y publica las revisiones
            de sus integrantes.
          </p>
        </div>
      )}
    </Section>
  );
}

export function CollaborationPanel({
  data,
  run,
  busy,
  success,
  assign,
}: Props & { assign: (groupId: string) => void }) {
  const [showNew, setShowNew] = useState(false);
  if (data.role !== "teacher") return null;
  const groups = data.groups ?? [];
  const active = groups.filter((group) => !group.archivedAt);
  return (
    <>
      <Section
        title="Aprender con otros"
        description="Equipos pequeños, participación voluntaria y acompañamiento supervisado por el docente."
      >
        <p>
          Alterna los papeles según la actividad y lo que cada estudiante quiera aportar. Los grupos
          no clasifican capacidades y los reconocimientos no modifican las notas.
        </p>
        <button
          className="mw-button primary"
          onClick={() => setShowNew(!showNew)}
          aria-expanded={showNew}
        >
          {showNew ? "Cerrar nuevo grupo" : "Organizar un grupo"}
        </button>
        {showNew && (
          <div className="mw-section">
            <GroupForm data={data} run={run} busy={busy} success={success} />
          </div>
        )}
      </Section>
      <Section
        title="Equipos del aula"
        description="Al asignar una actividad, cada integrante recibe su propia copia y conserva su práctica individual."
      >
        {active.length ? (
          active.map((group) => {
            const lessons = data.lessons.filter((lesson) => lesson.groupId === group.id);
            const batches = [
              ...new Set(lessons.map((lesson) => lesson.groupBatchId).filter(Boolean)),
            ];
            return (
              <article className="mw-team" key={group.id}>
                <div className="mw-list-row">
                  <div>
                    <h3>{group.name}</h3>
                    <p className="mw-subtle">
                      {data.classes.find((item) => item.id === group.classId)?.name} ·{" "}
                      {group.members.length} integrantes
                    </p>
                  </div>
                  <button className="mw-button small" onClick={() => assign(group.id)}>
                    Asignar al grupo
                  </button>
                </div>
                <ul className="mw-team-roster">
                  {group.members.map((member) => (
                    <li key={member.learnerId}>
                      <span>{name(data, member.learnerId)}</span>
                      <small>
                        {member.peerRole === "helper"
                          ? "Acompañamiento voluntario"
                          : "Participante"}
                      </small>
                    </li>
                  ))}
                </ul>
                {batches.map((batch) => {
                  const rows = lessons.filter((lesson) => lesson.groupBatchId === batch);
                  return (
                    <p className="mw-note" key={batch}>
                      {rows[0]?.title} ·{" "}
                      {rows.filter((lesson) => !!lesson.review?.publishedAt).length} de{" "}
                      {rows.length} revisiones compartidas
                    </p>
                  );
                })}
                <details className="mw-inline-details">
                  <summary>Editar integrantes y participación</summary>
                  <GroupForm
                    key={`${group.id}-${group.revision}`}
                    group={group}
                    data={data}
                    run={run}
                    busy={busy}
                    success={success}
                  />
                </details>
                <button
                  className="mw-text-button"
                  disabled={busy}
                  onClick={async () => {
                    if (
                      window.confirm(
                        "¿Archivar este grupo? Las actividades y sus registros se conservan.",
                      ) &&
                      (await run({
                        action: "archive-group",
                        groupId: group.id,
                        expectedRevision: group.revision,
                      }))
                    )
                      success("Grupo archivado. Su práctica y sus registros se conservan.");
                  }}
                >
                  Archivar grupo
                </button>
              </article>
            );
          })
        ) : (
          <div className="mw-empty">
            <Users size={27} aria-hidden="true" />
            <h3>Los equipos empiezan aquí</h3>
            <p>
              Organiza un grupo de dos a ocho estudiantes de la misma clase para preparar una
              actividad compartida.
            </p>
          </div>
        )}
      </Section>
      <ConfirmHelp data={data} run={run} busy={busy} success={success} />
      <p className="mw-note">
        <ShieldCheck size={15} aria-hidden="true" />
        Las revisiones compartidas registran 10 puntos individuales. El lote completo añade 20 extra
        por integrante, 30 en total. Una ayuda confirmada añade 5 más, hasta 35 para quien acompaña,
        sin premios repetidos por la misma acción.
      </p>
    </>
  );
}
