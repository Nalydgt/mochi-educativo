# Qwen local

`model.json` fija el Qwen3-4B-Instruct-2507 Q4_K_M y la imagen llama.cpp por
revisión, tamaño y SHA-256. Los pesos se guardan en el NAS y no se suben a Git.
Hermes conserva su servidor de 65.536 tokens, KV F16, ocho hilos y herramientas.
`tools/Deploy-Mochi.py stage` clona únicamente la configuración activa en una
instancia de 8.192 tokens, puerto privado 8776 y límite de 4 GiB. Son los mismos
pesos de solo lectura; sus cachés de atención pertenecen a procesos diferentes.

El adaptador de Hermes conserva sus esquemas de herramientas y comprime la
identidad solo cuando coincide con la versión conocida. La ruta directa usa
`gateway/fast_brain.py` y las memorias locales del mismo perfil; nunca anuncia
ni ejecuta herramientas. Los fallos y peticiones de acción vuelven a Hermes.

Qwen/Unsloth: Apache-2.0. llama.cpp: MIT. Licencias conservadas en `licenses/`.
No hay candidatos de otros modelos ni respaldo de nube configurado.
