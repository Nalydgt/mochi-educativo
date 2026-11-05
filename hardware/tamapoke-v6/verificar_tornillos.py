"""Check fastener envelopes and washers in the generated assembly.

Printed pilot/metal thread engagement is intentional and excluded. All heads,
washers, captured nuts and unthreaded lengths are tested against the assembly.
"""
from pathlib import Path
import sys,json,math,hashlib
import bpy
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import generar as g
from cad_base import cylinder,boolean,union,finish,mat

def main():
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'tamapoke_v6_montaje.blend'))
    material=mat('Referencia metal M2',(.30,.31,.33),.3,.7)
    plastic=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith(('01 ','02 ','03 ','04 ','05 ','06 ','Pulsador '))]
    electronic=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith(('CAD ','REF EEMB','REF GNSS','REF Altavoz'))]
    refs=[]
    def bolt(name,xy,z0,z1,h0,h1):
        o=cylinder(name,2,z0,z1,xy,vertices=64);union(o,cylinder('Cabeza M2',3.8,h0,h1,xy,vertices=64));finish(o,material);refs.append(o)
    for xy in g.SCREWS:bolt('REF M2x8 cierre tramo libre',xy,-4,.55,-6,-4)
    for xy in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):bolt('REF M2x5 OEM tramo libre',xy,0,2.45,-2,0)
    for xy in g.STACK:
        bolt('REF M2x16 interior',xy,-24.3,-8.3,-8.3,-6.3)
        w=cylinder('REF Arandela D5 H0.5',5,-8.8,-8.3,xy);boolean(w,cylinder('Hueco arandela',2.2,-9,-8,xy));finish(w,material);refs.append(w)
        # One micron below the nominal loaded plane avoids an Exact-Boolean
        # coplanar contact artefact. Independent STL sections verify the exact
        # bearing face and the complete AF4 chamber at its nominal dimensions.
        n=cylinder('REF Tuerca M2',4/math.cos(math.pi/6),-22.901,-21.301,xy,vertices=6);n.rotation_euler.z=math.atan2(xy[1],xy[0])-math.pi/6;boolean(n,cylinder('Hueco tuerca',2,-24,-20,xy));finish(n,material);refs.append(n)
    g.REPORT={'mechanical_checks':[]}
    body=bpy.data.objects['03 Cuerpo sin carga magnetica']
    for n,xy in zip([o for o in refs if 'Tuerca' in o.name],g.STACK):
        outward=g.Vector((xy[0],xy[1],0)).normalized()
        for distance in (0,.5,1,2,4,6):
            test=g.dup(n,'TEMP nut loading');test.location-=outward*distance;test.location.z-=.049
            g.collision(test,body,'straight side-loading nut sweep, 0.05mm below loaded plane')
            bpy.data.objects.remove(test,do_unlink=True)
    for fastener in refs:
        for part in plastic+electronic:
            a,b=g.bbox(fastener),g.bbox(part)
            if not(g.np.all(a[1]>b[0]+1e-5)and g.np.all(b[1]>a[0]+1e-5)):continue
            g.collision(fastener,part,'fastener exposed envelope')
    result={'pass':not g.REPORT.get('failed_checks'),'method':'Exact mesh intersections; intentional printed pilot and metal thread engagement excluded. Not a stress or physical tightening test.',
        'hardware_count':len(refs),'checks':g.REPORT['mechanical_checks'],'failed_checks':g.REPORT.get('failed_checks',[]),
        'nut_boolean_contact_inset_mm':.001,'nut_loading_height_below_loaded_plane_mm':.05,'nut_loading_distances_mm':[0,.5,1,2,4,6],
        'stl_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))},
        'mechanical_report_sha256':hashlib.sha256((ROOT/'validacion_mecanica.json').read_bytes()).hexdigest()}
    (ROOT/'validacion_tornillos.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if not result['pass']:raise RuntimeError('Unresolved fastener interference')
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'tamapoke_v6_montaje.blend'))
    print('HARDWARE_PASS',len(result['checks']),'checks',flush=True)

if __name__=='__main__':main()
