/* Original Coucou artwork, rendered once at the actual device pixel size.
 * Runtime motion is native; these are cropped transparent paint layers.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'tools/coucou-render/package.json'));
const {build}=require('esbuild');
const {createCanvas,Path2D,DOMMatrix,ImageData}=require('@napi-rs/canvas');
const runtime=path.join(root,'.runtime/coucou-native');
fs.mkdirSync(runtime,{recursive:true});
const upstream=path.join(root,'.references/coucou-latest');
const commit='47d1c2da12bf1dce8fb28b825757d497c1e1d88d';
if(execFileSync('git',['-C',upstream,'rev-parse','HEAD'],{encoding:'utf8'}).trim()!==commit)throw new Error('Unexpected Coucou revision');
const stub=path.join(runtime,'sound.mjs');fs.writeFileSync(stub,'export const Sound={play(){}};\n');
const entry=path.join(runtime,'entry.mjs');
fs.writeFileSync(entry,`export {BotEngine} from ${JSON.stringify(path.join(upstream,'windows/src/mochi/engine.ts'))};\nexport {drawOutfitBehind,drawOutfitFront,makeHead} from ${JSON.stringify(path.join(upstream,'windows/src/mochi/outfits.ts'))};\n`);
await build({entryPoints:[entry],bundle:true,platform:'node',format:'esm',outfile:path.join(runtime,'native.mjs'),
  plugins:[{name:'silent',setup(b){b.onResolve({filter:/\/core\/sound$/},()=>({path:stub}));}}]});
Object.assign(globalThis,{Path2D,DOMMatrix,ImageData,document:{createElement(){return createCanvas(1,1);}}});
const {BotEngine,drawOutfitBehind,drawOutfitFront,makeHead}=await import(pathToFileURL(path.join(runtime,'native.mjs')).href);
const destination=path.join(root,'firmware/assets/mochi-native');fs.mkdirSync(destination,{recursive:true});
const canvas=createCanvas(466,466),ctx=canvas.getContext('2d');
const records=[];
function save(id,kind,outfit){
 const pixels=ctx.getImageData(0,0,466,466).data;
 let x0=466,y0=466,x1=0,y1=0;
 for(let y=0;y<466;y++)for(let x=0;x<466;x++)if(pixels[(y*466+x)*4+3]){x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);}
 if(x0>x1)return;
 x0=Math.max(0,x0-2);y0=Math.max(0,y0-2);x1=Math.min(465,x1+2);y1=Math.min(465,y1+2);
 // The RGB565A8 decoder uses even colour and alpha strides.
 if((x1-x0+1)%2)x1++;
 const w=x1-x0+1,h=y1-y0+1;
 const cropped=createCanvas(w,h);cropped.getContext('2d').drawImage(canvas,x0,y0,w,h,0,0,w,h);
 const filename=id+'.png';fs.writeFileSync(path.join(destination,filename),cropped.toBuffer('image/png'));
 records.push({id,kind,outfit,file:filename,x:x0-233,y:y0-233,width:w,height:h});
}
function clear(){ctx.resetTransform();ctx.clearRect(0,0,466,466);ctx.translate(233,233);}
for(const [id,outfit] of [['body','none'],['pumpkin_body','pumpkin']]){
 clear();const bot=new BotEngine();bot.outfit=outfit;bot.outfitPresence=1;bot.drawBody(ctx,bot.bodyPath(136.8,105.6,120),120,136.8,105.6);save(id,'body',outfit);
}
const outfits=['partyHat','beanie','crown','sunglasses','roundGlasses','bow','scarf','witchHat','pumpkin','santaHat','bunnyEars'];
for(const outfit of outfits){
 if(outfit==='witchHat'){
  clear();const head=makeHead(120,0,0,0,0),pose={presence:1,morph:0};
  drawOutfitBehind(ctx,outfit,head,pose);
  ctx.globalCompositeOperation='destination-out';
  const bot=new BotEngine();bot.drawBody(ctx,bot.bodyPath(136.8,105.6,120),120,136.8,105.6);
  ctx.globalCompositeOperation='source-over';drawOutfitFront(ctx,outfit,head,pose);
  save(outfit+'_front','front',outfit);
 }else for(const [kind,draw] of [['back',drawOutfitBehind],['front',drawOutfitFront]]){
  clear();draw(ctx,outfit,makeHead(120,0,0,0,0),{presence:1,morph:0});save(outfit+'_'+kind,kind,outfit);
 }
}
fs.writeFileSync(path.join(destination,'rendered.json'),JSON.stringify({commit,author:'Louis Raillé',radius:120,assets:records},null,2)+'\n');
console.log(JSON.stringify({native_layers:records.length,full_resolution:true}));
