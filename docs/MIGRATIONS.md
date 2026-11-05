# Migraciones y dependencias

La base educativa ha evolucionado mediante migraciones incrementales. **No se
ha validado una reconstrucción completa desde una base vacía con estos archivos
por sí solos.** No ejecutes `deploy/*.sql` en orden alfabético ni asumas que un
nombre de archivo acredita su instalación.

## Historial que se conserva

- `web/drizzle/migrations/`: migraciones numeradas de cuentas/aprendizaje y su
  journal. Respeta su orden numérico y el estado de la base de destino.
- `web/supabase/migrations/`: historial con timestamps. Incluye la migración de
  documentos heredados; sus dependencias deben existir previamente.
- `web/deploy/`: SQL incremental del piloto y funciones posteriores.

El entorno instalado también tiene dependencias de Auth, documentos,
`inference_jobs`, telemetría y funciones auxiliares. El historial del proyecto
Supabase del operador es la autoridad para saber qué está aplicado. Conservar
estos scripts no sustituye una copia del esquema ni una revisión de permisos.

## Orden relativo del bloque educativo

Con el baseline de Auth/cuentas/roles privados, documentos e inferencia ya
preparado, el bloque actual requiere este orden relativo:

1. `education.sql` y `education-access.sql` como baseline educativo.
2. `education-adaptive-progress.sql`.
3. `education-student-access.sql`.
4. `education-study-priorities.sql`.
5. `education-home-studio.sql`.
6. `education-analytics.sql`.
7. `education-privacy.sql`.
8. `education-device-lessons.sql`.
9. `education-school-product.sql`.
10. `education-adult-role-hardening.sql`.
11. `education-care-collaboration.sql`.
12. `web/supabase/migrations/20261105232924_mochi_text_conversation.sql`, después
    del bloque anterior; admite origen escrito conservando permisos y retención.

Los demás scripts conservados corresponden a funcionalidades o ampliaciones
anteriores. No se ofrece un comando que aplique todo automáticamente porque
ese bootstrap todavía no está acreditado. Verifica dependencias, transacciones
y resultados en una base de prueba propia antes de integrarlo.

Las pruebas `web/tools/verify-school-product.mjs` y
`web/tools/verify-care-collaboration.mjs` comprueban contratos con datos
ficticios y rollback. Necesitan credenciales privadas de prueba creadas por el
operador y algunas rutas de informe históricas requieren revisión en el nuevo
layout. No contienen esas credenciales dentro del export.

El servicio de aplicación usa un rol restringido. Las tablas educativas
privadas y sus funciones comprueban actor, vínculo y alcance; no se deben
reemplazar por permisos generales para `anon` o `authenticated`.
