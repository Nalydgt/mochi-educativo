# Optional MOCHI Bun export

This source harness uses OneWorks' real React renderer and capture API. It does
not alter the selected firmware character or any device settings. The user chose
to retain the existing character for personal use and demonstrations; this bundle
is an optional alternative only.

Required source checkout: `.references/oneworks-avatar` at commit
`a06ba84c123cf82e2b1a59c36b403392e22f9d08` from
https://github.com/oneworks-ai/avatar (MIT; notice retained with assets).

From this directory:

```powershell
npm ci
npm run dev
```

Open `http://127.0.0.1:5194/`. The page renders the concrete scene from `main.tsx`.
Click **Exportar bundle**, or call `await window.mochiExport()` in the page. The
local-only development middleware saves the official SVG, transparent PNG and
serialized versioned definitions under `firmware/assets/mochi-original`.

Reopen the page and the PNG independently. Confirm the small rounded crown,
white body, glossy eyes, smile and cheeks; transparent background; no logos; and
512 × 512 RGBA exports. Then, from the workspace root:

```powershell
python tools/Prepare-MochiOriginal.py
```

That script checks the source revision and alpha/dimensions, packages six native
RGB565A8 textures, writes `mochi_original_index.inc` plus hash manifest, and saves
the static source preview `preview-466.png`. This packaging uses Pillow and numpy
from the repository's existing Python tooling. No generated source image is
substituted for the official export.

The unselected renderer expects each `body_*.rgb565a8` resource embedded with the
symbol prefix `original_` (for example `RENAME_TO original_body_white`). Do not
add it to CMake without an explicit character selection and full native build,
memory, frame-time, audio-DMA sync, motion, and wardrobe acceptance checks.
