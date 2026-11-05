# MOCHI Bun — optional OneWorks adaptation

This alternative is **not selected in the firmware build**. The user's selected
personal/demo character remains the existing renderer. Do not change that choice
merely by regenerating these assets.

The body geometry derives from the Bun preset in OneWorks Avatar, version
1.0.0-rc.9, source commit `a06ba84c123cf82e2b1a59c36b403392e22f9d08`:
https://github.com/oneworks-ai/avatar

Copyright (c) 2026-present One Works contributors. The complete MIT license is
retained in `OneWorks-MIT.txt`. This notice records software/geometry provenance;
it makes no claim about trademarks or third-party rights.

The authored scene uses explicit version-1 `oneworks.avatar` definitions. Changes
from Bun: white and five pastel materials; a small rounded crown; a centered,
contained view; no preset decals, logos, pleats or third-party brand marks; an
adapted smile and subtle original cheek decals. SVG and PNG files were captured
using the official React renderer's `AvatarHandle.capture` API. The same concrete
definitions are stored alongside every capture. No private editor URL encoding
or copied DOM path was used to construct the scene.

Body texture variants use supported 1px neutral-material eyes because the schema
has no separate eye-visibility flag; mouth, highlights and decals are disabled
before official capture. Packaging resamples 512px to the physical 466px canvas,
crops transparent padding, then encodes RGB565 plus 8-bit alpha. It does not use
upscaled GIFs or assets from the existing character.

`mochi_original.c` is a separate, unselected native adaptation. Its face, clothing,
motifs and procedural motion are newly authored code. Its compatible catalogue
identifiers preserve saved preferences and existing diagnostic callers; visual
motion is not copied from the old renderer. It has not passed physical display,
timing, audio-sync, wardrobe or accessibility acceptance testing. The preview
shows the official source capture, not a capture from installed firmware.

Regeneration: `tools/avatar-original/README.md` and
`tools/Prepare-MochiOriginal.py`. Asset hashes and dimensions: `manifest.json`.
