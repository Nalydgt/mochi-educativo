"""Execute the production scene C with descriptor-to-SVG host stubs (MSVC)."""
from pathlib import Path
import json,os,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'docs/mediciones/20261105-lesson-scene-host'
BUILD=ROOT/'.runtime/lesson-scene-host'
BUILD.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
vs=Path(r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC')
vc=sorted(vs.iterdir())[-1]
kits=Path(r'C:\Program Files (x86)\Windows Kits\10')
kit=sorted((kits/'Include').iterdir())[-1].name
env=os.environ.copy()
env['PATH']=str(vc/'bin/Hostx64/x64')+';'+env['PATH']
env['INCLUDE']=';'.join(map(str,[vc/'include',kits/'Include'/kit/'ucrt',kits/'Include'/kit/'shared',kits/'Include'/kit/'um']))
env['LIB']=';'.join(map(str,[vc/'lib/x64',kits/'Lib'/kit/'ucrt/x64',kits/'Lib'/kit/'um/x64']))
exe=BUILD/'scene.exe'
subprocess.run([str(vc/'bin/Hostx64/x64/cl.exe'),'/nologo','/std:c11','/TC','/utf-8','/W3','/O1','/D_CRT_SECURE_NO_WARNINGS','/I'+str(HERE/'stub'),str(HERE/'harness.c'),'/Fo:'+str(BUILD/'scene.obj'),'/Fe:'+str(exe)],env=env,check=True,capture_output=True,text=True)
cases=[('hub',3,3,0),('hub5',3,3,0),('launcher',3,3,0),('hub-compact',3,3,0),('help',3,3,0),('apples-3x3',3,3,0),('fish-3x2',3,2,1),('cars-3x4',3,4,2),('dense-12x4',12,4,0),('complete',3,3,3),('voice',3,3,0)]
verification=subprocess.run([str(exe),'verify'],capture_output=True,check=True)
verified=json.loads(verification.stderr)
report=[];files=[]
for name,a,b,step in cases:
 mode='hub' if name=='hub5' else name if name in ('hub','hub-compact','complete','voice','launcher','help') else 'groups'
 r=subprocess.run([str(exe),mode,str(a),str(b),str(step),'0','5' if name=='hub5' else '3'],capture_output=True,check=True)
 svg=OUT/(name+'.svg');svg.write_bytes(r.stdout);files.append(str(svg));d=json.loads(r.stderr);d['file']=svg.name;report.append(d)
subprocess.run(['node',str(HERE/'render.mjs'),*files],check=True)
(OUT/'report.json').write_text(json.dumps({'source':'firmware/main/mochi_lesson_scene.c executed unchanged','fontLimitation':'Host Montserrat TTF approximates device bitmap font rasterization; chrome illustrative, scene descriptors exact','verification':verified,'launcherLimitation':'Existing Coucou body texture with illustrative placeholder face; exact native C launcher geometry','cases':report},indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
