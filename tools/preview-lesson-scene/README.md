# Native lesson scene preview

Run from the workspace root:

```powershell
python tools/preview-lesson-scene/preview.py
```

The host harness includes and executes the production
`firmware/main/mochi_lesson_scene.c` **without changing its drawing code**.
Minimal LVGL stubs serialize its rectangle, triangle, line and text draw
descriptors to SVG. The existing `@napi-rs/canvas` dependency renders PNGs.
Microsoft Visual Studio Build Tools and the Windows SDK are used only to compile
the host harness; no firmware build configuration or device is touched.

Outputs: `docs/mediciones/20261105-lesson-scene-host/`. The report includes 432
real-C quantity cases: factors 1–12 for each of three themes. Totals up to 48 must
draw exactly their product; higher totals must draw no partial item collection
and retain every labelled group.

Scene geometry and counts come from the production C. Preview text uses the
existing Montserrat TTF, whose host rasterization differs from the device bitmap
font. Surrounding UI labels and answer buttons are illustrative layout context,
not a screenshot of installed firmware. In particular, answer values are sample
chrome rather than the lesson runner's shuffled distractors. The launcher image
composes the exact C launcher with the existing Coucou body texture and a clearly
illustrative placeholder face; it does not emulate Coucou's animation engine.

Ponds, foliage and ground use a single native rounded-rectangle primitive with
`LV_RADIUS_CIRCLE`. This replaces the triangle fans whose radial antialias seams
were also confirmed on the physical display in firmware 0.14.2. Dimensions and
centres are retained; wide shapes become smooth capsules. These previews do not
establish device frame time, touch behavior, audio sync, or RAM usage.
