"""Build byte-verified STL and editable V5 packages from the final reports."""
from pathlib import Path
import hashlib,json,zipfile
from PIL import Image

ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    vr=json.loads((ROOT/'validacion_stl.json').read_text(encoding='utf-8'))
    mr=json.loads((ROOT/'validacion_mecanica.json').read_text(encoding='utf-8'))
    assert vr['pass'] and vr['part_count']==15
    assert mr['pass'] and len(mr['parts'])==15 and not mr.get('failed_checks')
    assert mr['camera_direction']==mr['screen_direction']==[0,0,1]
    assert all(x['intersection_mm3']<=x['allowed_mm3'] for x in mr['mechanical_checks'])
    for part in vr['parts']:assert sha(ROOT/'stl'/part['file'])==part['sha256'],part['file']
    for name,h in mr['source_files_sha256'].items():assert sha(ROOT/name)==h,name
    assert sha(ROOT/'referencias/waveshare-ESP32-S3-Touch-AMOLED-1_75.stp')==mr['source_step_sha256']
    description=Image.open(ROOT/'vistas/08_distribucion_y_cotas.png').info['Description']
    for name in ('parametros.json','stl/01_frontal_gato.stl'):assert sha(ROOT/name) in description
    # This file belongs to the failed intermediate builds, never the delivery.
    (ROOT/'auditoria/interferencias_pendientes.json').unlink(missing_ok=True)
    base=list((ROOT/'stl').glob('*.stl'))
    base += [ROOT/n for n in ('LEEME.md','parametros.json','validacion_stl.json','validacion_mecanica.json')]
    base += [ROOT/'referencias'/n for n in ('bateria-955565.jpg','componentes_medidas.json')]
    base += [ROOT/'vistas'/n for n in ('01_gato_v5.png','02_frontal_v5.png','06_frontal_stl_una_pieza.png','08_distribucion_y_cotas.png')]
    extra=[ROOT/n for n in ('gato_v5_montaje.blend','generar.py','modulos_v5.py','cad_base.py','validar_stl.py','vista_stl.py','teselar_step.py','empaquetar.py')]
    extra += [ROOT/'auditoria'/n for n in ('step_parts.json','step_measurements_independent.json','dibujar_distribucion.py')]
    extra += [ROOT/'referencias'/n for n in ('step_mesh_native.npz','plano-oficial.png','waveshare-ESP32-S3-Touch-AMOLED-1_75.stp')]
    extra += [ROOT/'vistas'/n for n in ('03_botones_guiados.png','04_montaje_interior.png','05_camara_frontal.png','06_interruptor_y_ventilacion.png')]
    packages=[]
    for name,files in [('Mochi_Gato_V5_STL.zip',base),('Mochi_Gato_V5_Completo.zip',base+extra)]:
        files=sorted(set(files))
        manifest={'revision':'Mochi gato V5 front camera','units':'mm','camera_and_screen_direction':[0,0,1],
            'validation':'Digital geometry only. Physical module fitting and optical alignment required; see LEEME.md.',
            'files':{p.relative_to(ROOT).as_posix():sha(p) for p in files}}
        target=ROOT/name
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in files:z.write(p,'Mochi_Gato_V5/'+p.relative_to(ROOT).as_posix())
            z.writestr('Mochi_Gato_V5/SHA256.json',json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        with zipfile.ZipFile(target) as z:
            assert z.testzip() is None
            for p in files:assert hashlib.sha256(z.read('Mochi_Gato_V5/'+p.relative_to(ROOT).as_posix())).hexdigest()==sha(p)
        packages.append({'file':name,'bytes':target.stat().st_size,'sha256':sha(target),'entries':len(files)+1})
    result={'packages':packages,'stl_count':15,'mechanical_checks':len(mr['mechanical_checks']),
        'assembly_dimensions_mm':mr['assembly_bounds_mm'],'camera_and_screen_direction':[0,0,1]}
    (ROOT/'entrega.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
