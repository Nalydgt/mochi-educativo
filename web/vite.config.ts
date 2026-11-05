// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { NitroConfig } from "nitro/types";

const hosted = process.env["NITRO_PRESET"] === "vercel" || process.env["VERCEL"] === "1";
const vercelConfig = {
  preset: "vercel",
  vercel: { functions: { runtime: "nodejs24.x", maxDuration: 210 } },
  routeRules: {
    "/expedicion": { headers: { "X-Robots-Tag": "noindex, nofollow" } },
  },
} satisfies NitroConfig;

export default defineConfig({
  nitro: hosted ? vercelConfig : { preset: "node-server" },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
