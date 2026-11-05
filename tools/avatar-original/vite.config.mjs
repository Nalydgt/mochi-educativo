import { defineConfig } from 'vite';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const source = path.join(root, '.references/oneworks-avatar');
const output = path.join(root, 'firmware/assets/mochi-original');
export default defineConfig({
  root: here,
  esbuild: { jsx: 'automatic' },
  resolve: { alias: [
    { find: /^@oneworks\/avatar$/, replacement: path.join(source, 'packages/avatar/src/index.ts') },
    { find: /^react$/, replacement: path.join(here, 'node_modules/react/index.js') },
    { find: /^react\/jsx-runtime$/, replacement: path.join(here, 'node_modules/react/jsx-runtime.js') },
    { find: /^react-dom\/client$/, replacement: path.join(here, 'node_modules/react-dom/client.js') }
    ,{ find: /^gifenc$/, replacement: path.join(here, 'node_modules/gifenc/dist/gifenc.esm.js') }
  ] },
  server: { fs: { allow: [root] } },
  plugins: [{ name: 'mochi-local-export', configureServer(server) {
    server.middlewares.use('/save-export', (req, res) => {
      if (req.method !== 'POST') { res.statusCode = 405; res.end(); return; }
      let input = '';
      req.on('data', chunk => { input += chunk; if (input.length > 20000000) req.destroy(); });
      req.on('end', () => { try {
        const { files } = JSON.parse(input);
        if (!Array.isArray(files) || files.length > 40) throw new Error('Invalid export');
        fs.mkdirSync(output, { recursive: true });
        for (const { name, data, encoding } of files) {
          if (!/^[a-z0-9_.-]+\.(svg|png|json)$/.test(name)) throw new Error('Invalid filename');
          fs.writeFileSync(path.join(output, name), encoding === 'base64' ? Buffer.from(data, 'base64') : data);
        }
        res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ saved: files.map(f => f.name) }));
      } catch (error) { res.statusCode = 400; res.end(String(error)); } });
    });
  } }]
});
