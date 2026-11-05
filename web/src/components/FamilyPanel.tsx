import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ArrowRight, Pencil, UserRoundPlus } from "lucide-react";
import { accountData, saveLearner, selectLearner, saveAccount } from "@/lib/learning.functions";
import { learnerInput } from "@/lib/learning-schema";
import { EmptyState, Field, PageTitle, Section, Tag } from "./Layout";
import { PrivacyAction } from "./PrivacyAction";
import { Mascot } from "./Stickers";
import { Button } from "./ui/button";

const colors = { sunburst: "Amarillo", mint: "Menta", lavender: "Lavanda", ember: "Naranja" };

export function FamilyPanel({ embedded = false }: { embedded?: boolean }) {
  const client = useQueryClient();
  const read = useServerFn(accountData);
  const save = useServerFn(saveLearner);
  const select = useServerFn(selectLearner);
  const edit = useServerFn(saveAccount);
  const query = useQuery({ queryKey: ["account"], queryFn: () => read() });
  const [editing, setEditing] = useState<string>();
  const [notice, setNotice] = useState<{ text: string; error?: boolean }>();
  const [busy, setBusy] = useState(false);
  const [selecting, setSelecting] = useState<string>();
  const [accountBusy, setAccountBusy] = useState(false);
  const account = query.data;
  const current = account?.learners.find((learner) => learner.id === editing);
  const refresh = () => client.invalidateQueries({ queryKey: ["account"] });
  const fail = (error: unknown, fallback: string) =>
    setNotice({ text: error instanceof Error ? error.message : fallback, error: true });

  async function choose(id: string) {
    setSelecting(id);
    setNotice(undefined);
    try {
      await select({ data: { id } });
      await refresh();
      setNotice({ text: "Perfil seleccionado." });
    } catch (error) {
      fail(error, "No se pudo seleccionar el perfil.");
    } finally {
      setSelecting(undefined);
    }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setNotice(undefined);
    try {
      const data = learnerInput.parse({
        id: editing,
        display_name: fields.get("name"),
        education_level: fields.get("level"),
        grade_level: fields.get("grade"),
        age_band: fields.get("age"),
        color: fields.get("color"),
        ia: fields.get("ia") === "on",
      });
      const learner = await save({ data });
      if (!account?.profile?.active_learner_id) await select({ data: { id: learner.id } });
      setEditing(undefined);
      form.reset();
      await refresh();
      setNotice({ text: "Perfil guardado." });
    } catch (error) {
      fail(error, "No se pudo guardar el perfil.");
    } finally {
      setBusy(false);
    }
  }

  async function saveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setAccountBusy(true);
    setNotice(undefined);
    try {
      await edit({ data: { display_name: String(fields.get("display_name")) } });
      await refresh();
      setNotice({ text: "Cuenta guardada." });
    } catch (error) {
      fail(error, "No se pudo guardar la cuenta.");
    } finally {
      setAccountBusy(false);
    }
  }

  return (
    <>
      {!embedded && (
        <Section tone="sky">
          <PageTitle
            kicker="Mi Peluqo"
            title="Tu espacio familiar"
            sub="Gestiona tus perfiles de aprendizaje y la configuración de tu cuenta."
            art="reserva"
          />
        </Section>
      )}
      <Section>
        <h2 className="mb-4 text-2xl font-bold">Perfiles de aprendizaje en casa</h2>
        {query.error ? (
          <p role="alert" className="platform-message">
            {query.error.message}
          </p>
        ) : query.isPending ? (
          <p role="status">Cargando tus perfiles…</p>
        ) : (
          <>
            {account && account.learners.length > 0 ? (
              <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {account.learners.map((learner) => {
                  const color = (learner.avatar_config as { color?: string } | null)?.color;
                  const active = account.profile?.active_learner_id === learner.id;
                  const completed = account.progress.filter(
                    (result) => result.learner_id === learner.id && result.status === "completed",
                  ).length;
                  return (
                    <li key={learner.id} className="card">
                      <div className="flex flex-wrap items-center gap-3">
                        <Mascot color={color ?? "sunburst"} />
                        <div className="min-w-0">
                          <h3 className="text-xl font-bold [overflow-wrap:anywhere]">
                            {learner.display_name}
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            {[learner.education_level, learner.grade_level, learner.age_band]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Tag color="bg-mist">
                          {completed}{" "}
                          {completed === 1 ? "lección completada" : "lecciones completadas"}
                        </Tag>
                        {active && <Tag>Perfil activo</Tag>}
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {!active && (
                          <Button
                            variant="outline"
                            disabled={!!selecting}
                            onClick={() => void choose(learner.id)}
                          >
                            {selecting === learner.id ? "Seleccionando…" : "Seleccionar"}
                          </Button>
                        )}
                        <Button variant="outline" onClick={() => setEditing(learner.id)}>
                          <Pencil aria-hidden="true" /> Editar
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState title="Crea tu primer perfil">
                Cada perfil guarda sus lecciones, sus insignias y el aspecto de su Peluqo.
              </EmptyState>
            )}
            {notice && (
              <p className="platform-message mt-5" role={notice.error ? "alert" : "status"}>
                {notice.text}
              </p>
            )}
            <div className="mt-6 flex flex-wrap gap-2">
              <Link className="btn btn-primary" to="/progreso">
                Consultar progreso <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>

            <div className="platform-settings">
              <div>
                <h2 className="text-xl font-bold">
                  {editing ? "Editar perfil" : "Crear perfil de aprendizaje"}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Utiliza un apodo. Al crear un perfil infantil confirmas que eres su adulto
                  responsable.
                </p>
              </div>
              <form
                key={editing ?? "new"}
                className="grid gap-4 sm:grid-cols-2"
                aria-busy={busy}
                onSubmit={saveProfile}
              >
                <Field
                  label="Apodo"
                  name="name"
                  defaultValue={current?.display_name}
                  required
                  maxLength={60}
                />
                <Field
                  label="Curso orientativo"
                  name="grade"
                  defaultValue={current?.grade_level}
                  maxLength={30}
                />
                <label className="platform-field">
                  <span className="label">Etapa educativa</span>
                  <select
                    className="platform-input"
                    name="level"
                    defaultValue={current?.education_level}
                  >
                    {["Primaria", "Secundaria", "Bachillerato", "Universidad"].map((level) => (
                      <option key={level}>{level}</option>
                    ))}
                  </select>
                </label>
                <label className="platform-field">
                  <span className="label">Franja de edad</span>
                  <select className="platform-input" name="age" defaultValue={current?.age_band}>
                    {["6–8", "9–12", "12–13", "14–17", "18+"].map((age) => (
                      <option key={age}>{age}</option>
                    ))}
                  </select>
                </label>
                <label className="platform-field">
                  <span className="label">Color de Peluqo</span>
                  <select
                    className="platform-input"
                    name="color"
                    defaultValue={(current?.avatar_config as { color?: string } | null)?.color}
                  >
                    {Object.entries(colors).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex min-h-11 items-center gap-2">
                  <input
                    type="checkbox"
                    name="ia"
                    defaultChecked={(current?.preferences as { ia?: boolean } | null)?.ia}
                  />{" "}
                  Permitir tutor con IA
                </label>
                <div className="flex flex-wrap gap-2 sm:col-span-2">
                  <Button disabled={busy}>
                    {!editing && <UserRoundPlus aria-hidden="true" />}
                    {busy ? "Guardando…" : "Guardar perfil"}
                  </Button>
                  {editing && (
                    <Button type="button" variant="outline" onClick={() => setEditing(undefined)}>
                      Cancelar edición
                    </Button>
                  )}
                </div>
              </form>
            </div>

            <div className="platform-settings">
              <div>
                <h2 className="text-xl font-bold">Mi cuenta</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Cambia el nombre que aparece en tu espacio.
                </p>
              </div>
              <form className="max-w-md space-y-3" aria-busy={accountBusy} onSubmit={saveName}>
                <Field
                  key={account?.profile?.display_name}
                  label="Nombre visible"
                  name="display_name"
                  defaultValue={account?.profile?.display_name}
                  maxLength={60}
                  required
                />
                <Button disabled={accountBusy}>
                  {accountBusy ? "Guardando…" : "Guardar cuenta"}
                </Button>
              </form>
            </div>
            <PrivacyAction />
          </>
        )}
      </Section>
    </>
  );
}
