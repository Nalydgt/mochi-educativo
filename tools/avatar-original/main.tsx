/* Official OneWorks renderer; concrete versioned definitions are the source.
 * Hardware uses the captured body and the same face proportions, with small
 * LVGL primitives for responsive blinking and actual I2S mouth animation. */
import React, { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createDefaultAvatarDefinition, parseAvatarDefinition, serializeAvatarDefinition } from '@oneworks/avatar';
import { Avatar } from '../../.references/oneworks-avatar/packages/react/src/renderer';
import { createAvatarEntityParts, getAvatarEntityPresetFaceStyle } from '../../.references/oneworks-avatar/src/avatarEntityPresets';
import './preview.css';

const base = createDefaultAvatarDefinition();
const parts = createAvatarEntityParts('bun').map(part => ({
  ...part,
  baseColor: '#fafbff', foregroundColor: '#262635', highlightColor: '#ffffff', shadowColor: '#c8cddd',
  ...(part.id === 'bun-crown' ? { shape: 'sphere', scaleX: .22, scaleY: .12, scaleZ: .45, y: -31, roundness: 100 } : {})
}));
// Intentionally authored from public definition fields and source preset factory.
// No editor URL tuple, copied projected SVG path, logo or back decal is used.
const definition = parseAvatarDefinition({
  ...base,
  metadata: { id: 'mochi-bun-1', name: 'MOCHI · Bun', createdAt: '2026-11-05T00:00:00Z' },
  scene: {
    ...base.scene,
    appearance: { ...base.scene.appearance, paletteId: 'white' },
    camera: { ...base.scene.camera, size: 512, background: 'transparent', frame: 'square', showFrameShadow: false },
    entity: { preset: 'bun', parts },
    decals: [
      { id: 'mochi-cheek-left', label: 'MOCHI left cheek', color: '#f6a9bb', height: 9, width: 21, x: -47, y: 18, opacity: 47, rotation: 0, shape: 'ellipse', side: 'front', targetPartId: 'bun-body' },
      { id: 'mochi-cheek-right', label: 'MOCHI right cheek', color: '#f6a9bb', height: 9, width: 21, x: 47, y: 18, opacity: 47, rotation: 0, shape: 'ellipse', side: 'front', targetPartId: 'bun-body' }
    ],
    face: {
      ...getAvatarEntityPresetFaceStyle('bun'),
      width: 27, height: 32, gap: 39,
      mouthEnabled: true, mouthShape: 'curve', mouthCurve: 38, mouthHeight: 5, mouthWidth: 29, mouthY: 49
    },
    effects: { ...base.scene.effects, showOutline: false, showAvatarShadow: false, showFaceShadow: false },
    lighting: { ...base.scene.lighting, enabled: true, azimuth: -48, elevation: 58, distance: 78, gridDensity: 400 },
    view: { yaw: 0, pitch: 0, roll: 0, positionX: 0, positionY: -8, scale: 1.52 }
  }
});

const sourceColors = ['white', 'sky', 'lavender', 'rose', 'mint', 'honey'];
const palette = ['#fafbff', '#bedcfb', '#dacef6', '#f7d4e4', '#cde8de', '#f5e2b4'];
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function App() {
  const avatar = useRef<any>(null);
  const [label, setLabel] = useState('MOCHI · OneWorks Bun');
  async function exportAll() {
    const files: Array<{name: string, data: string, encoding?: string}> = [];
    const capture = async (name: string, def: any) => {
      avatar.current.setDefinition(parseAvatarDefinition(def)); await sleep(180);
      files.push({ name: name + '.definition.json', data: serializeAvatarDefinition(avatar.current.getDefinition()) });
      files.push({ name: name + '.svg', data: await (await avatar.current.capture({ format: 'svg', size: 512, background: 'transparent', frame: 'square' })).text() });
      const blob = await avatar.current.capture({ format: 'png', size: 512, background: 'transparent', frame: 'square' });
      const data = await new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(blob); });
      files.push({ name: name + '.png', data, encoding: 'base64' });
    };
    await capture('avatar', definition);
    for (let color = 0; color < palette.length; color++) {
      // The official definition has no eye visibility flag. For this texture
      // variant, eyes use the supported 1px minimum and the base material.
      // Mouth, highlights and decals are disabled in the scene, before capture.
      const body = structuredClone(definition);
      body.scene.decals = [];
      body.scene.entity.parts = body.scene.entity.parts.map((part: any) => ({ ...part, baseColor: palette[color], foregroundColor: palette[color] }));
      body.scene.face = { ...body.scene.face, width: 1, height: 1, mouthEnabled: false, noseEnabled: false, eyeHighlight: { ...body.scene.face.eyeHighlight, enabled: false } };
      await capture('body-' + sourceColors[color], body);
    }
    avatar.current.setDefinition(definition); await sleep(180);
    const response = await fetch('/save-export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files }) });
    if (!response.ok) throw new Error(await response.text());
    setLabel('Exportación oficial guardada · 512 × 512 · seis colores');
    return response.json();
  }
  (window as any).mochiExport = exportAll;
  (window as any).mochiDefinition = definition;
  return <main><div className="caption"><b>MOCHI</b><span>{label}</span></div><div className="device"><Avatar ref={avatar} definition={definition} interactive={false} theme="dark" /></div><button onClick={() => exportAll().catch(error => setLabel(String(error)))}>Exportar bundle</button><p>Adaptación de Bun · OneWorks Avatar · MIT<br/>Captura oficial; sin marcas ni decals del preset.</p></main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
