# Mochi font fallback

Montserrat Medium is copied from LVGL's original font-generation sources in
the Waveshare reference checkout. License: `../../licenses/Montserrat-OFL.txt`.
Original embedded notice: Copyright 2011 The Montserrat Project Authors
(https://github.com/JulietaUla/Montserrat). The included OFL notice also records
the project's current attribution.
The matching LVGL ASCII fonts retain their icons; a same-size fallback adds
Latin accented letters, Spanish punctuation and common typographic symbols.

Regenerate the three compiled fonts with:

```powershell
npm ci --prefix tools/fonts --ignore-scripts
node tools/Prepare-MochiFonts.mjs
```

`@personalize` checks 21 representative glyphs at all three UI sizes on the
device. `Check-MochiPersonalization.py` exercises tabs, arrows and swipes through
LVGL's real pointer processing and captures the live preview.
