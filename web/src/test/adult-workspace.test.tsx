import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AdultWorkspace } from "@/components/education/AdultWorkspace";
import { adultRequest } from "@/lib/education/adult-client";
import { schoolSettingsSchema, type SchoolSnapshot } from "@/lib/education/school-schema";

const account = vi.hoisted(() => ({ id: "11111111-1111-4111-8111-111111111111" as string | null }));
const navigate = vi.hoisted(() => vi.fn());
vi.mock("@/lib/education/adult-client", () => ({
  useAdultAccountId: () => account.id,
  adultRequest: vi.fn(),
}));
vi.mock("@/integrations/supabase/client", () => ({
  supabase: { auth: { getSession: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn() } },
}));
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ to, children, ...props }: { to: string; children: ReactNode }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

const classId = "22222222-2222-4222-8222-222222222222";
const learnerId = "33333333-3333-4333-8333-333333333333";
const lessonId = "44444444-4444-4444-8444-444444444444";
const secondLearnerId = "88888888-8888-4888-8888-888888888888";
const groupId = "99999999-9999-4999-8999-999999999999";
const batchId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const alertId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const stamp = "2026-11-05T15:00:00.000Z";
function fixture(role: "teacher" | "family" = "teacher"): SchoolSnapshot {
  return {
    role,
    adult: { id: account.id!, name: "Adulto de prueba" },
    classes: [{ id: classId, name: "3.º A" }],
    learners: [
      {
        id: learnerId,
        name: "Alex de prueba",
        classId,
        ageBand: "9–12",
        gradeLabel: "3.º Primaria",
      },
    ],
    lessons: [
      {
        id: lessonId,
        lessonId: "55555555-5555-4555-8555-555555555555",
        learnerId,
        classId,
        learnerName: "Alex de prueba",
        title: "Agrupaciones de prueba",
        subject: "matematicas",
        goal: "Comprender los grupos iguales",
        instructions: "Cuenta los objetos de los grupos",
        dueAt: "2026-11-10",
        factors: [[2, 3]],
        createdAt: stamp,
        result: {
          resultId: "66666666-6666-4666-8666-666666666666",
          attempts: 2,
          hints: 1,
          elapsedSeconds: 45,
          correctCount: 1,
          receivedAt: stamp,
          completedCount: 1,
          detailsShared: true,
          clientReported: false,
          answers: [
            { a: 2, b: 3, choice: 5, correct: false },
            { a: 2, b: 3, choice: 6, correct: true },
          ],
        },
        review: null,
      },
    ],
    grades: [],
    messages: [],
    events: [],
    devices: [],
    materials: [],
    settings: [
      {
        ...schoolSettingsSchema.parse({
          learnerId,
          dailyMinutes: 30,
          startTime: "16:00",
          endTime: "20:00",
          timezone: "Europe/Madrid",
          language: "es",
          voiceEnabled: true,
          captionsEnabled: false,
          textFirst: false,
          sharePractice: true,
        }),
        revision: 3,
        updatedAt: stamp,
        updatedBy: account.id!,
      },
    ],
  };
}
let snapshot: SchoolSnapshot;
let onboard: { role: "teacher" | "family" | null; needsConfirmation: boolean };
beforeEach(() => {
  account.id = "11111111-1111-4111-8111-111111111111";
  snapshot = fixture();
  onboard = { role: "teacher", needsConfirmation: false };
  vi.mocked(adultRequest).mockReset();
  navigate.mockReset();
  vi.mocked(adultRequest).mockImplementation(async (path, payload) => {
    if (path === "/api/education/adult-onboarding") {
      if (payload) onboard = { role: "family", needsConfirmation: false };
      return onboard as never;
    }
    if (path === "/api/education/school" && payload === undefined) return snapshot as never;
    return { ok: true } as never;
  });
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.removeAttribute("open");
    },
  });
});
afterEach(cleanup);
function mount(initialView?: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AdultWorkspace {...(initialView ? { initialView } : {})} />
    </QueryClientProvider>,
  );
}

describe("adult product workspace", () => {
  it("keeps accompaniment private to the family even through a teacher deep link", async () => {
    snapshot.careAlerts = [
      {
        id: alertId,
        learnerId,
        category: "possible_peer_bullying",
        createdAt: stamp,
        status: "pending_review",
        reviewedAt: null,
      },
    ];
    mount("care");
    expect(await screen.findByRole("heading", { name: "Tu aula, al día." })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Acompañamiento/ })).toBeNull();
    expect(screen.queryByText("Posible dificultad entre compañeros")).toBeNull();
  });
  it("lets a linked family review a minimized notice without exposing another learner", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    snapshot.careAlerts = [
      {
        id: alertId,
        learnerId,
        category: "possible_peer_bullying",
        createdAt: stamp,
        status: "pending_review",
        reviewedAt: null,
      },
      {
        id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        learnerId: secondLearnerId,
        category: "possible_peer_bullying",
        createdAt: stamp,
        status: "pending_review",
        reviewedAt: null,
      },
    ];
    mount("care");
    const review = await screen.findByRole("button", { name: "Marcar como revisado" });
    expect(screen.getAllByText("Posible dificultad entre compañeros")).toHaveLength(1);
    expect(vi.mocked(adultRequest).mock.calls.filter(([, payload]) => !!payload)).toHaveLength(0);
    fireEvent.click(review);
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({ action: "review-care-alert", alertId, status: "reviewed" }),
      ),
    );
  });
  it("saves explicit family opt-in and an editable pause reminder with the current revision", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    mount("settings");
    const optIn = await screen.findByLabelText(/Recibir avisos privados de acompañamiento/);
    expect(optIn).not.toBeChecked();
    fireEvent.click(optIn);
    fireEvent.change(screen.getByLabelText("Recordatorio de pausa cada (minutos)"), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar ajustes" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "save-settings",
          learnerId,
          expectedRevision: 3,
          reminderMinutes: 7,
          familySupportAlertsEnabled: true,
        }),
      ),
    );
  });
  it("can disable reminders without enabling accompaniment signals", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    mount("settings");
    fireEvent.click(await screen.findByLabelText("Avisar para hacer una pausa"));
    expect(screen.getByLabelText("Recordatorio de pausa cada (minutos)")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Guardar ajustes" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "save-settings",
          reminderMinutes: null,
          familySupportAlertsEnabled: false,
        }),
      ),
    );
  });
  it("does not expose family alert preferences in teacher settings", async () => {
    snapshot.settings[0]!.familySupportAlertsEnabled = true;
    mount("settings");
    expect(
      await screen.findByRole("heading", { name: "El Mochi de Alex de prueba" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Recibir avisos privados de acompañamiento/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Guardar ajustes" })).toBeNull();
  });
  it("shows only linked learner recognition and does not create a ranking", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    snapshot.points = [
      {
        id: alertId,
        learnerId,
        points: 10,
        reason: "review",
        sourceId: lessonId,
        createdAt: stamp,
      },
      {
        id: groupId,
        learnerId: secondLearnerId,
        points: 20,
        reason: "group",
        sourceId: batchId,
        createdAt: stamp,
      },
    ];
    mount("recognition");
    const learner = (await screen.findByRole("heading", { name: "Alex de prueba" })).closest(
      "article",
    )!;
    expect(within(learner).getByText("+10")).toBeInTheDocument();
    expect(within(learner).queryByText("+20")).toBeNull();
    expect(screen.queryByRole("button", { name: /clasificación|ranking/i })).toBeNull();
  });
  it("requires voluntary group participation before saving a supervised helper role", async () => {
    snapshot.learners.push({
      id: secondLearnerId,
      name: "Sam de prueba",
      classId,
      ageBand: "9–12",
      gradeLabel: "3.º",
    });
    mount("collaboration");
    fireEvent.click(await screen.findByRole("button", { name: "Organizar un grupo" }));
    fireEvent.change(screen.getByLabelText("Nombre del grupo"), {
      target: { value: "Equipo Girasol" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Alex de prueba" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Sam de prueba" }));
    fireEvent.change(screen.getByLabelText("Participación de Alex de prueba"), {
      target: { value: "helper" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear grupo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Confirma la participación voluntaria",
    );
    expect(
      vi
        .mocked(adultRequest)
        .mock.calls.some(
          ([, body]) => (body as { action?: string } | undefined)?.action === "save-group",
        ),
    ).toBe(false);
    for (const check of screen.getAllByRole("checkbox", {
      name: "He confirmado su participación voluntaria.",
    }))
      fireEvent.click(check);
    fireEvent.click(screen.getByRole("button", { name: "Crear grupo" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "save-group",
          classId,
          name: "Equipo Girasol",
          members: expect.arrayContaining([
            { learnerId, peerRole: "helper", voluntary: true },
            { learnerId: secondLearnerId, peerRole: "member", voluntary: true },
          ]),
        }),
      ),
    );
  });
  it("assigns a shared task to the selected group through its canonical action", async () => {
    snapshot.learners.push({
      id: secondLearnerId,
      name: "Sam de prueba",
      classId,
      ageBand: "9–12",
      gradeLabel: "3.º",
    });
    snapshot.groups = [
      {
        id: groupId,
        classId,
        name: "Equipo Girasol",
        revision: 2,
        archivedAt: null,
        members: [
          { learnerId, peerRole: "helper", voluntary: true, buddyAlias: "Sol" },
          { learnerId: secondLearnerId, peerRole: "member", voluntary: true, buddyAlias: null },
        ],
      },
    ];
    mount("collaboration");
    fireEvent.click(await screen.findByRole("button", { name: "Asignar al grupo" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Fecha de entrega"), {
      target: { value: "2026-11-10" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Asignar actividad" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({ action: "assign-group", groupId, dueAt: "2026-11-10" }),
      ),
    );
    expect(
      vi
        .mocked(adultRequest)
        .mock.calls.some(
          ([, body]) => (body as { action?: string } | undefined)?.action === "batch-assign",
        ),
    ).toBe(false);
  });
  it("requires published practice and teacher confirmation before acknowledging peer help", async () => {
    const secondLessonId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const review = {
      status: "reviewed" as const,
      observation: "Práctica explicada",
      reviewedAt: stamp,
      publishedAt: stamp,
      authorName: "Docente",
    };
    snapshot.learners.push({
      id: secondLearnerId,
      name: "Sam de prueba",
      classId,
      ageBand: "9–12",
      gradeLabel: "3.º",
    });
    snapshot.lessons[0] = {
      ...snapshot.lessons[0]!,
      groupId,
      groupBatchId: batchId,
      peerRole: "helper",
      review,
    };
    snapshot.lessons.push({
      ...snapshot.lessons[0]!,
      id: secondLessonId,
      learnerId: secondLearnerId,
      learnerName: "Sam de prueba",
      peerRole: "member",
    });
    mount("collaboration");
    const submit = await screen.findByRole("button", { name: "Confirmar ayuda" });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Actividad de quien ha acompañado"), {
      target: { value: lessonId },
    });
    fireEvent.change(screen.getByLabelText("Estudiante acompañado"), {
      target: { value: secondLearnerId },
    });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Confirmo que la ayuda se ha realizado/));
    fireEvent.click(submit);
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "confirm-help",
          assignmentId: lessonId,
          helpedLearnerId: secondLearnerId,
        }),
      ),
    );
  });
  it("keeps help confirmation unavailable while the other practice review is private", async () => {
    const secondLessonId = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const review = {
      status: "reviewed" as const,
      observation: "Práctica explicada",
      reviewedAt: stamp,
      publishedAt: stamp,
      authorName: "Docente",
    };
    snapshot.learners.push({
      id: secondLearnerId,
      name: "Sam de prueba",
      classId,
      ageBand: "9–12",
      gradeLabel: "3.º",
    });
    snapshot.lessons[0] = {
      ...snapshot.lessons[0]!,
      groupId,
      groupBatchId: batchId,
      peerRole: "helper",
      review,
    };
    snapshot.lessons.push({
      ...snapshot.lessons[0]!,
      id: secondLessonId,
      learnerId: secondLearnerId,
      learnerName: "Sam de prueba",
      peerRole: "member",
      review: { ...review, publishedAt: null },
    });
    mount("collaboration");
    const submit = await screen.findByRole("button", { name: "Confirmar ayuda" });
    fireEvent.change(screen.getByLabelText("Actividad de quien ha acompañado"), {
      target: { value: lessonId },
    });
    fireEvent.click(screen.getByLabelText(/Confirmo que la ayuda se ha realizado/));
    expect(submit).toBeDisabled();
    expect(screen.queryByRole("option", { name: "Sam de prueba" })).toBeNull();
    expect(
      vi
        .mocked(adultRequest)
        .mock.calls.some(
          ([, body]) => (body as { action?: string } | undefined)?.action === "confirm-help",
        ),
    ).toBe(false);
  });
  it("opens adult sign-in without consulting a learner cookie or showing games", () => {
    account.id = null;
    mount();
    expect(screen.getByRole("heading", { name: "Entra en tu espacio" })).toBeInTheDocument();
    expect(screen.getByLabelText("Correo")).toBeInTheDocument();
    expect(screen.queryByText("Mundos")).toBeNull();
    expect(adultRequest).not.toHaveBeenCalled();
  });
  it("uses the server family role and never exposes teacher navigation", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    mount();
    expect(
      await screen.findByRole("heading", { name: "Acompañar también es comprender." }),
    ).toBeInTheDocument();
    const nav = screen.getByRole("complementary", { name: "Navegación del panel" });
    expect(within(nav as HTMLElement).queryByText("Clases y alumnos")).toBeNull();
    expect(screen.queryByRole("button", { name: "Asignar actividad" })).toBeNull();
    expect(screen.getByRole("button", { name: "Sus actividades" })).toBeInTheDocument();
  });
  it("assigns a reviewed form to its selected class with an opaque request receipt", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Asignar actividad" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Fecha de entrega"), {
      target: { value: "2026-11-10" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Asignar actividad" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "batch-assign",
          classId,
          subject: "matematicas",
          dueAt: "2026-11-10",
          requestId: expect.stringMatching(/^[a-f\d-]{36}$/),
        }),
      ),
    );
  });
  it("returns keyboard focus to the opener when a dialog is cancelled", async () => {
    mount();
    const opener = await screen.findByRole("button", { name: "Asignar actividad" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(opener).toHaveFocus());
  });
  it("uses the selected class for an editable AI proposal without assigning it", async () => {
    const secondClass = "77777777-7777-4777-8777-777777777777";
    snapshot.classes.push({ id: secondClass, name: "4.º B" });
    vi.mocked(adultRequest).mockImplementation(async (path, payload) => {
      if (path === "/api/education/adult-onboarding") return onboard as never;
      if (!payload) return snapshot as never;
      return {
        title: "Propuesta para cuarto",
        goal: "Razonar con agrupaciones iguales",
        instructions: "Cuenta los objetos de estos grupos.",
        factors: [[4, 5]],
      } as never;
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Asignar actividad" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Clase"), { target: { value: secondClass } });
    fireEvent.change(within(dialog).getByLabelText("¿Qué quieres reforzar?"), {
      target: { value: "Agrupaciones para cuarto de Primaria" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crear propuesta editable" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({ action: "suggest-assignment", classId: secondClass }),
      ),
    );
    await waitFor(() =>
      expect(within(dialog).getByLabelText("Título")).toHaveValue("Propuesta para cuarto"),
    );
    expect(
      vi
        .mocked(adultRequest)
        .mock.calls.some(
          ([, payload]) => (payload as { action?: string } | undefined)?.action === "batch-assign",
        ),
    ).toBe(false);
  });
  it("records a human review without automatically creating an official grade", async () => {
    mount("reviews");
    fireEvent.click(await screen.findByRole("button", { name: "Revisar" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Observación docente"), {
      target: { value: "Ha explicado cómo agrupar. Practicaremos otro ejemplo en clase." },
    });
    fireEvent.click(within(dialog).getByLabelText(/Compartir la observación/));
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar revisión" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({ action: "review-lesson", assignmentId: lessonId, publish: true }),
      ),
    );
    expect(
      vi
        .mocked(adultRequest)
        .mock.calls.some(
          ([, payload]) => (payload as { action?: string } | undefined)?.action === "save-grade",
        ),
    ).toBe(false);
  });
  it("requires the teacher to enter an official grade and choose publication", async () => {
    mount("grades");
    fireEvent.click(await screen.findByRole("button", { name: "Añadir calificación" }));
    const dialog = screen.getByRole("dialog");
    const grade = within(dialog).getByLabelText("Calificación (0 a 10)");
    expect(grade).toHaveValue(null);
    fireEvent.change(within(dialog).getByLabelText("Evaluación"), {
      target: { value: "Control de agrupaciones" },
    });
    fireEvent.change(grade, { target: { value: "8.5" } });
    fireEvent.click(within(dialog).getByLabelText(/Publicar para la familia/));
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar calificación" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({ action: "save-grade", learnerId, value: 8.5, publish: true }),
      ),
    );
  });
  it("provides a complete text alternative when family disables voice and checks revision", async () => {
    snapshot = fixture("family");
    onboard = { role: "family", needsConfirmation: false };
    mount("settings");
    const voice = await screen.findByLabelText(/Permitir conversación por voz/);
    fireEvent.click(voice);
    expect(screen.getByLabelText(/Mostrar texto de preguntas y respuestas/)).toBeChecked();
    expect(screen.getByLabelText(/Priorizar texto/)).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Guardar ajustes" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith(
        "/api/education/school",
        expect.objectContaining({
          action: "save-settings",
          learnerId,
          expectedRevision: 3,
          voiceEnabled: false,
          captionsEnabled: true,
          textFirst: true,
        }),
      ),
    );
  });
  it("asks for adult confirmation explicitly without automatically enrolling a visitor", async () => {
    onboard = { role: null, needsConfirmation: true };
    mount();
    const confirm = await screen.findByRole("checkbox", {
      name: "Soy mayor de edad y gestionaré mi espacio familiar.",
    });
    expect(vi.mocked(adultRequest).mock.calls.filter(([, payload]) => !!payload)).toHaveLength(0);
    fireEvent.click(confirm);
    fireEvent.click(screen.getByRole("button", { name: "Continuar al panel familiar" }));
    await waitFor(() =>
      expect(adultRequest).toHaveBeenCalledWith("/api/education/adult-onboarding", {
        confirmAdult: true,
      }),
    );
  });
});
