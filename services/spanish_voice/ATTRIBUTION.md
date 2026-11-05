# Speaker 03 runtime

- Chatterbox by Resemble AI, MIT; source commit
  `5de7a54aa4e5e2baadb0182dde554908b48b85c2`:
  https://github.com/resemble-ai/chatterbox
- Multilingual V3 checkpoint from ResembleAI/chatterbox, revision
  `5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18`:
  https://huggingface.co/ResembleAI/chatterbox
- The short conditioning reference was generated with Qwen3-TTS VoiceDesign,
  revision `5ecdb67327fd37bb2e042aab12ff7391903235d3`:
  https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign
- The selected sample is `voice-bank/prueba-espanol-03/01-saludo.wav`.
  The profile fixes the original reference, checkpoint and generation settings.
  The built-in Perth watermark is retained.

`profile.json` includes asset hashes. The runtime generates one speaker at a
time, on the NAS CPU, and returns mono 16 kHz PCM. Logs contain timings and
byte counts, without audio, text or tokens.

The optional accelerated T3 uses chatterbox.cpp by Gianfranco Cordella,
MIT, revision `ddca05fb69c2910b0d7b5eae420d360ed98c067b`, with GGML pinned to
`58c3805840b516b2a88ff867ccf7bb41dba79951`. The local adapter separates learned
speech positions from KV positions and retains the original Torch sampling
processors, S3Gen decoder and Perth watermark. The full upstream MIT license
is in `licenses/chatterbox-cpp-MIT.txt`; exported native artifacts include both
upstream license notices. Native builds require the original NAS AVX2/FMA CPU.
