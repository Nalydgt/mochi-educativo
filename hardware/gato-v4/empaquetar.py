"""Package the reviewed V4 print files and editable source, verifying every byte."""
from pathlib import Path
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


def main():
    vr=json.loads((ROOT/'validacion_stl.json').read_text(encoding='utf-8'))
    mr=json.loads((ROOT/'validacion_mecanica.json').read_text(encoding='utf-8'))
    require(vr['pass'] and vr['part_count']==8, 'Independent STL validation must pass on all eight files')
    require(len(mr['mechanical_checks'])==925, 'Expected 925 mechanical checks')
    require(all(c['intersection_mm3']<=c['allowed_mm3'] for c in mr['mechanical_checks']),
            'Mechanical clearance validation failed')
    for r in vr['parts']:
        p=ROOT/'stl'/r['file']
        require(sha(p)==r['sha256'], 'Stale STL report: '+p.name)
    require(mr['closure']['nut_retaining_shoulder_mm']==2, 'Invalid closure nut shoulder')
    require(mr['nut_load_paths']['M2_retaining_shoulder_mm']==2, 'Invalid M2 nut shoulder')
    drawing=json.loads((ROOT/'auditoria/cotas_y_anclajes_metadata.json').read_text(encoding='utf-8'))
    for name,h in drawing['input_sha256'].items():
        require(sha(ROOT/name)==h, 'Stale drawing input: '+name)
    base=list((ROOT/'stl').glob('*.stl'))
    base += [ROOT/n for n in ('LEEME.md','parametros.json','validacion_stl.json','validacion_mecanica.json')]
    base += [ROOT/'vistas'/n for n in ('01_gato_v4.png','02_frontal_v4.png','05_cotas_y_anclajes.png','06_frontal_stl_una_pieza.png')]
    base += [ROOT/'referencias/bateria-955565.jpg']
    extra=[ROOT/n for n in ('gato_v4_montaje.blend','generar.py','cad_base.py','validar_stl.py','vista_stl.py','teselar_step.py','empaquetar.py')]
    extra += [p for p in (ROOT/'auditoria').iterdir() if p.is_file() and p.suffix in ('.json','.py')]
    extra += [ROOT/'referencias'/n for n in ('step_mesh_native.npz','plano-oficial.png','waveshare-ESP32-S3-Touch-AMOLED-1_75.stp')]
    extra += [ROOT/'vistas'/n for n in ('03_botones_guiados.png','04_montaje_interior.png')]
    packages=[]
    for name,files in [('Mochi_Gato_V4_STL.zip',base),('Mochi_Gato_V4_Completo.zip',base+extra)]:
        files=sorted(set(files))
        manifest={'revision':'Mochi gato V4','units':'mm','validation':'Digital geometric checks; physical fitting still required as described in LEEME.md','files':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files}}
        target=ROOT/name
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in files:z.write(p,'Mochi_Gato_V4/'+p.relative_to(ROOT).as_posix())
            z.writestr('Mochi_Gato_V4/SHA256.json',json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        with zipfile.ZipFile(target) as z:
            require(z.testzip() is None, 'Package CRC verification failed: '+name)
            for p in files:
                data=z.read('Mochi_Gato_V4/'+p.relative_to(ROOT).as_posix())
                require(hashlib.sha256(data).hexdigest()==sha(p), 'Package integrity verification failed: '+p.name)
        packages.append({'file':name,'bytes':target.stat().st_size,'sha256':sha(target),'entries':len(files)+1})
    (ROOT/'entrega.json').write_text(json.dumps({'packages':packages,'stl_count':8,'mechanical_checks':925,'assembly_dimensions_mm':mr['assembly_bounds_mm']},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(packages,indent=2))

if __name__=='__main__':main()
