# Perfil mochi

Personalidad actual solicitada por el usuario: curiosa, afectuosa y con criterio,
con lenguaje natural y adulto. Sin ñoñerías, adornos infantiles, fantasías
añadidas ni preguntas de relleno. El humor se usa con discreción.

SOUL.md define la identidad completa; SOUL-VOICE.md contiene la versión breve
compartida por las rutas habladas. `tools/Update-MochiPersona.py` respalda y
actualiza ambas en el NAS, preservando MEMORY y USER. El adaptador de Hermes
solo compacta una identidad que coincide exactamente con su referencia conocida.

Hermes mantiene el perfil independiente mochi, Qwen local de 65.536 tokens y
los conjuntos web, memory, session_search, terminal, file, todo, cronjob y
code_execution. Su hogar es `/opt/data/profiles/mochi`; el perfil default no se
modifica. Las integraciones siguen necesitando sus cuentas y programas.

El proveedor mochi-local comparte SQLite con la pasarela. La ruta directa lee
los mismos archivos de perfil mediante un montaje de solo lectura y consulta
los mismos recuerdos e historial. Los datos temporales del dispositivo y las
correcciones actuales tienen prioridad. Los recursos personales no se incluyen
en este directorio del repositorio.
