import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

export function useAdultAccountId() {
  const [id, setId] = useState<string | null>();
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((_event, session) =>
      setId(session?.user.id ?? null),
    );
    return () => data.subscription.unsubscribe();
  }, []);
  return id;
}

export async function adultRequest<T>(path: string, payload?: unknown): Promise<T> {
  const session = (await supabase.auth.getSession()).data.session;
  if (!session) throw new Error("Inicia sesión con tu cuenta adulta.");
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(payload !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "No se pudo completar la solicitud.");
  return data as T;
}
