import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const require=createRequire(path.resolve(here,'../coucou-render/package.json'));
const {createCanvas,loadImage,GlobalFonts}=require('@napi-rs/canvas');
GlobalFonts.registerFromPath(path.resolve(here,'../fonts/Montserrat-Medium.ttf'),'Montserrat');
for(const filename of process.argv.slice(2)){
  let svg=fs.readFileSync(filename,'utf8');
  if(path.basename(filename)==='launcher.svg'){
    // Illustrative home composition only: existing licensed body texture plus
    // placeholder face, followed by the exact C launcher's draw descriptors.
    const body=fs.readFileSync(path.resolve(here,'../../firmware/assets/mochi-native/body.png')).toString('base64');
    svg=svg.replace("<rect width='466' height='466' fill='#000000'/>",`<rect width='466' height='466' fill='#000000'/><image x='94' y='132' width='278' height='216' href='data:image/png;base64,${body}'/><ellipse cx='188' cy='242' rx='12' ry='16' fill='#201a18'/><ellipse cx='278' cy='242' rx='12' ry='16' fill='#201a18'/>`);
    fs.writeFileSync(filename.replace(/\.svg$/,'.illustrative-home.svg'),svg);
  }
  const image=await loadImage(Buffer.from(svg));
  const canvas=createCanvas(466,466);canvas.getContext('2d').drawImage(image,0,0);
  fs.writeFileSync(filename.replace(/\.svg$/,'.png'),canvas.toBuffer('image/png'));
}
