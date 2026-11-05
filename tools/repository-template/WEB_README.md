# Web adulta de MOCHI

Esta carpeta forma parte del monorepo. Docentes y familias usan espacios
autenticados y permisos por estudiante. La práctica infantil sucede en la placa.
Los módulos educativos heredados permanecen como fuentes, con rutas antiguas
redirigidas al panel adulto correspondiente.

Consulta [la preparación](../docs/SETUP.md),
[las migraciones](../docs/MIGRATIONS.md) y
[la guía funcional](../docs/GUIA_MONOREPO.md).

```powershell
npm ci
npm test
npx tsc --noEmit
npm run build
```

Configura `.env.local` a partir de `.env.example`, sin añadirlo a Git. No hay
cuentas demo ni credenciales incluidas. Los tests de integración de Postgres
requieren una base propia con el historial y usuarios ficticios preparados.
