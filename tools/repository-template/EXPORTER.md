# Exportador de fuentes

`tools/Prepare-MochiRepository.py` usa una allowlist por carpeta y formato. La
operación predeterminada es sólo lectura:

```powershell
python tools/Prepare-MochiRepository.py --plan
python tools/test_repository_export.py
```

Busca `web/` dentro del monorepo; en el workspace original admite que la web sea
un proyecto hermano. No recorre enlaces, junctions, `.runtime`, `.references`,
builds, paquetes instalados, datos, grabaciones, modelos ni fixtures privados.
De hardware conserva fuentes y parámetros, más los STL de `tamapoke-v6`; no las
galerías, fotografías ni entregas binarias de las otras iteraciones. La carpeta
vendorizada `web/deploy/supabase` se omite: sus ejemplos de Docker contienen
credenciales públicas de demostración que no deben confundirse con un setup
seguro. Se conservan las migraciones y funciones propias de `web/supabase`.

## Escaneo sin mostrar secretos

El plan comprueba formatos de claves de proveedor, JWT, bloques de clave
privada, URLs con contraseña, PIN y atributos literales sensibles. Compara
también credenciales configuradas en archivos locales conocidos, sin copiarlas
ni imprimirlas. El resultado sólo contiene rutas, hashes del archivo completo,
nombres de reglas y recuentos. Nunca contiene el texto coincidente.

La regla genérica de atributos puede señalar deliberadamente un token inventado
en un test o un ejemplo público de una biblioteca. Eso no lo aprueba por sí
solo. Tras inspeccionar el archivo, puede registrarse una excepción ligada a
su SHA-256 exacto en un JSON privado:

```json
{
  "approved": [
    {
      "path": "gateway/test_latency.py",
      "sha256": "REEMPLAZAR_POR_EL_FILE_SHA256_DEL_PLAN",
      "reason": "synthetic_in_process_test"
    }
  ]
}
```

Las categorías permitidas son `synthetic_in_process_test`,
`synthetic_rejection_only_test`, `public_upstream_usage_example` y
`generated_code_fragment`. La segunda se limita a pruebas de rechazo con datos
inventados, sin invitaciones válidas ni creación de cuentas. Cualquier cambio
del archivo invalida la excepción. Una excepción sólo puede resolver la regla
genérica `literal_secret_attribute`: **nunca** omite un valor configurado real,
un token reconocible, JWT, contraseña de base, clave privada o PIN.

```powershell
python tools/Prepare-MochiRepository.py --plan --literal-allowlist .runtime/reviewed-literals.json
```

## Copia explícita después de la revisión

```powershell
python tools/Prepare-MochiRepository.py --write --literal-allowlist .runtime/reviewed-literals.json
```

Si el escaneo está bloqueado, no se crea el destino. Si pasa, se crea
`.runtime/repository-export/mochi-educativo`. Si ese nombre existe, se elige
otro con timestamp y sufijo único. No se sobrescriben exportaciones anteriores,
no se borra ni se mueve ninguna fuente y nunca se ejecuta Git o un despliegue.

Cada archivo copiado se verifica por hash. Un fallo retiene la nueva carpeta
incompleta para inspección; no intenta limpiar recursivamente directorios.
`REPOSITORY_MANIFEST.json` y `SECRET_SCAN.json` documentan el resultado.

Los formatos textuales conocidos se normalizan de CRLF a LF **antes** del
escaneo, del cálculo de SHA-256 y de la escritura. El manifest registra
`normalize_lf` cuando cambia un archivo. Sus hashes describen el contenido
exportado y siguen siendo válidos tras el checkout con `.gitattributes`.
Las imágenes, capas RGB565, fuentes y STL permanecen byte por byte intactos.
La normalización también cubre avisos textuales sin extensión como
`ESPHOME-LICENSE`.

Las carpetas de datos y fixtures siguen bloqueadas de forma general. Sólo se
incluyen explícitamente dos dependencias revisadas: `web/src/data/peluqo.ts`
(catálogo legado importado por el laboratorio) y
`web/fixtures/reviewed-mission.ts` (contenido docente sintético que usan las
pruebas). Esto no incorpora fixtures de cuentas, grabaciones ni datos de QA.

Además de esa normalización textual, los únicos ajustes de código son las rutas del monorepo en
`Check-MochiLessonVoice.py`, `web/tools/pilot.py`,
`web/tools/configure-peluqo-board.py` y la creación previa de `.runtime` en
`web/tools/build-pilot.py`. Las demás referencias de rutas se reportan sin
reescribirlas. Las URLs no se sustituyen.
