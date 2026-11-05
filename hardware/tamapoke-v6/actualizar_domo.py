"""Reuse the fitted V6 assembly; change only the rear, with minimal checks."""
from pathlib import Path
import sys,json,hashlib,math
import bpy
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import generar as g
from cad_base import finish,mat,cylinder,render

def main():
    old=json.loads((ROOT/'validacion_mecanica.json').read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'tamapoke_v6_montaje.blend'))
    for o in list(bpy.data.objects):
        if o.name.startswith(('03 Cuerpo','REF M2','REF Arandela','REF Tuerca')):bpy.data.objects.remove(o,do_unlink=True)
    ivory=bpy.data.materials['Marfil'];pink=bpy.data.materials['Rosa suave'];dark=bpy.data.materials['Pantalla y componentes']
    back=g.make_rear();g.export(back,'03_cuerpo_sin_carga_magnetica.stl',ivory)
    cat=bpy.data.objects['01 Frontal gato'];mochi=bpy.data.objects['02 Frontal mochi']
    internals=[o for o in bpy.data.objects if o.type=='MESH'and o.name.startswith(('04 ','05 ','06 ','Pulsador ','REF EEMB','REF GNSS','REF Altavoz'))]
    for o in [cat,mochi,*internals]:g.collision(back,o,'minimal rear clearance')
    bat=g.rect('TEMP battery clearance',26.5,42,2,-17.7,-10.3,(1,-2))
    gps=g.cube('TEMP GPS clearance',(27,27,6.7),(1,1,-23.05))
    for o in (bat,gps):g.collision(back,o,'minimal component clearance');bpy.data.objects.remove(o,do_unlink=True)
    if g.REPORT.get('failed_checks'):raise RuntimeError('Rear interference')
    old['parts']=[p for p in old['parts']if p['stl']!='03_cuerpo_sin_carga_magnetica.stl']+g.REPORT['parts']
    old['mechanical_checks']=g.REPORT['mechanical_checks'];old.pop('failed_checks',None)
    old['validation_mode']='quick';old['pass']=True
    old['method']='Minimal rear mesh and interior envelope checks. Previous front fit retained; full STEP, moving buttons and hardware sweeps not rerun.'
    old['full_step_sweep_rerun']=False;old['hardware_sweep_rerun']=False
    old['rear_dome']={'outer_profile_z_r_mm':g.dome_profile(),'inner_profile_z_r_mm':g.dome_profile(True),'normal_offset_mm':2,'flat_landing_diameter_mm':20,'external_supports_required':True}
    old['source_files_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ('generar.py','cad_base.py','parametros.json','actualizar_domo.py')}
    old['stl_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))}
    for label,f in [('cat',cat),('mochi',mochi)]:
        bb=[g.bbox(o)for o in [f,back,*[o for o in internals if o.name.startswith('Pulsador ')]]]
        old['assembly_'+label+'_dimensions_mm']=(g.np.max([x[1]for x in bb],axis=0)-g.np.min([x[0]for x in bb],axis=0)).tolist()
    (ROOT/'validacion_mecanica.json').write_text(json.dumps(old,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    scene=bpy.context.scene;scene.cycles.samples=12;scene.render.resolution_x=1000;scene.render.resolution_y=1000
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'tamapoke_v6_montaje.blend'))
    refs=[o for o in bpy.data.objects if o.name.startswith('CAD ')]
    for r in refs:r.hide_render=True
    face=finish(cylinder('REF Cara ilustrativa',48.96,12.7,12.9),dark)
    for x in (-7,7):
        eye=g.c.ellipse_prism('REF Ojo',4.2,7,12.92,12.98);eye.location.x=x;eye.location.y=2;finish(eye,ivory)
    for x in (-13,13):
        cheek=g.c.ellipse_prism('REF Colorete',4.3,2,12.92,12.98);cheek.location.x=x;cheek.location.y=-4;finish(cheek,pink)
    pts=[]
    for j in range(25):a=math.pi+math.pi*j/24;pts.append((3*math.cos(a),-3+1.9*math.sin(a)))
    for j in range(24,-1,-1):a=math.pi+math.pi*j/24;pts.append((2.3*math.cos(a),-3+1.2*math.sin(a)))
    finish(g.c.prism('REF Sonrisa',pts,12.92,12.98),ivory)
    render('01_gato.png',(75,45,150),(0,4,-10),108)
    render('02_gato_frontal.png',(0,4,160),(0,4,-10),88)
    cat.hide_render=True;mochi.hide_render=False
    render('03_mochi.png',(75,45,150),(0,0,-10),106)
    mochi.hide_render=True;cat.hide_render=False
    render('04_trasera_sin_imanes.png',(75,35,-160),(0,0,-14),108)
    render('07_perfil_redondo.png',(150,0,30),(0,2,-10),104)
    cat.hide_render=True;face.hide_render=True;back.hide_render=True
    for o in bpy.data.objects:
        if o.name.startswith(('REF Ojo','REF Colorete','REF Sonrisa')):o.hide_render=True
    for r in refs:r.hide_render=False
    render('05_distribucion_interior.png',(85,-50,-140),(0,0,-6),104)
    print('QUICK_DOME_COMPLETE',flush=True)

if __name__=='__main__':main()
