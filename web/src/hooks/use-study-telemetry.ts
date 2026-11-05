import { useEffect, useRef } from "react";
import type { StudyContext } from "@/lib/education/analytics";

const endpoint = "/api/education/telemetry";
const idleAfter = 90_000;
const interval = 25_000;

export function noteStudyFailure() {
  void fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      visitId: crypto.randomUUID(),
      event: "failure",
      surface: "aventura",
      sessionId: null,
      activityId: null,
      format: null,
      active: false,
    }),
  }).catch(() => undefined);
}

export function useStudyTelemetry({ surface, sessionId, activityId, format }: StudyContext) {
  const channel = useRef<((context: StudyContext) => void) | null>(null);

  useEffect(() => {
    let context: StudyContext | undefined;
    let visitId = crypto.randomUUID();
    let lastAction = performance.now();
    let entered = false;
    let pending = Promise.resolve();

    function send(event: "enter" | "sample" | "leave") {
      if (!context) return;
      const active = context.surface !== "peluqo" && performance.now() - lastAction < idleAfter;
      const body = JSON.stringify({ ...context, visitId, event, active });
      if (
        event === "leave" &&
        navigator.sendBeacon?.(endpoint, new Blob([body], { type: "application/json" }))
      )
        return;
      pending = pending.then(async () => {
        await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: event === "leave",
        }).catch(() => undefined);
      });
    }

    function visible() {
      if (document.visibilityState === "visible") {
        if (!entered && context) {
          lastAction = performance.now();
          send("enter");
          entered = true;
        }
      } else {
        close();
      }
    }

    function close() {
      if (!entered) return;
      send("leave");
      entered = false;
      visitId = crypto.randomUUID();
    }

    function interact(event: Event) {
      if (event.isTrusted) lastAction = performance.now();
    }

    channel.current = (next) => {
      const alreadyEntered = entered;
      context = next;
      visible();
      if (alreadyEntered && entered) send("enter");
    };
    document.addEventListener("visibilitychange", visible);
    document.addEventListener("pointerdown", interact, { passive: true });
    document.addEventListener("keydown", interact);
    window.addEventListener("pagehide", close);
    window.addEventListener("pageshow", visible);
    const timer = window.setInterval(() => {
      if (entered && document.visibilityState === "visible") send("sample");
    }, interval);

    return () => {
      close();
      channel.current = null;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
      document.removeEventListener("pointerdown", interact);
      document.removeEventListener("keydown", interact);
      window.removeEventListener("pagehide", close);
      window.removeEventListener("pageshow", visible);
    };
  }, []);

  useEffect(() => {
    channel.current?.({ surface, sessionId, activityId, format });
  }, [surface, sessionId, activityId, format]);
}
