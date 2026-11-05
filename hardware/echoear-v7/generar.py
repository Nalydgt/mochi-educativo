"""Adapt the supplied EchoEar enclosure to the compact Waveshare project.

Only geometry and metadata are read from the supplied 3MF; no embedded
instructions, firmware, printer profiles or executable content are used.
"""
from pathlib import Path
import sys,json,math,struct,hashlib,itertools,argparse
import bpy,bmesh,numpy as np
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import cad_base as c
from cad_base import cylinder,cube,boolean,union,dup,finish,mat,render
P=c.P;REPORT=c.REPORT
SCREWS=P['case_screws']['centers'];STACK=P['internal_stack']['mount_centers']
SCALE=P['exterior']['source_scale'];R=32*SCALE+P['exterior']['outer_radial_allowance']
ZC=-1.67228463*SCALE;FRONT=P['exterior']['front_plane'];WALL=2.0
BOTTOM=ZC-math.sqrt(R*R-(P['exterior']['flat_print_landing_diameter']/2)**2)
REG=json.loads((ROOT/'referencias/guts_registration.json').read_text())

def load_stl(path,name,zshift=0):
    raw=path.read_bytes();n=struct.unpack_from('<I',raw,80)[0]
    dt=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    v,f=np.unique(np.frombuffer(raw,dtype=dt,count=n,offset=84)['vertices'].reshape(-1,3),axis=0,return_inverse=True)
    v=v.astype(float);v[:,2]+=zshift
    me=bpy.data.meshes.new(name);me.from_pydata(v.tolist(),[],f.reshape(-1,3).tolist());me.update()
    ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob);c.recalc(ob);return ob

def source_front():
    d=np.load(ROOT/'referencias/canonical_source.npz');a=d['object_2_v']
    # Rotate the registered source a quarter turn so its original ears are up.
    v=np.c_[a[:,1],-(a[:,0]-4.59408299),a[:,2]]*SCALE
    me=bpy.data.meshes.new('EchoEar source ears and front');me.from_pydata(v.tolist(),[],d['object_2_f'].tolist());me.update()
    o=bpy.data.objects.new('Frontal original EchoEar escalado',me);bpy.context.collection.objects.link(o);c.recalc(o);return o

def ball(name,radius):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=192,ring_count=96,radius=radius,location=(0,0,ZC))
    o=bpy.context.object;o.name=name;return o

def slab(name,z0,z1):return cube(name,(120,120,z1-z0),(0,0,(z0+z1)/2))
def bore(o,d,z0,z1,xy=(0,0)):boolean(o,cylinder('Paso '+str(d),d,z0,z1,xy))
def rect(name,w,h,r,z0,z1,xy=(0,0)):
    o=c.rounded_prism(name,w,h,r,z0,z1);o.location.x,o.location.y=xy;return o
def radial(o,p,n):
    n=Vector(n).normalized();t=Vector((-n.y,n.x,0));z=Vector((0,0,1))
    b=Matrix((t,z,n)).transposed().to_4x4();b.translation=Vector(p);o.matrix_world=b@o.matrix_world
    c.activate(o);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);return o
def rcyl(name,d,s0,s1,p,n):return radial(cylinder(name,d,s0,s1),p,n)
def port(o,w,h,s0,s1,z,radius=1):
    cut=c.rounded_prism('Canal USB-C',w,h,radius,s0,s1)
    boolean(o,radial(cut,(0,0,z),(-1,0,0)))
def nut_slot(o,xy):
    x,y=xy;a=math.atan2(y,x);n=Vector((math.cos(a),math.sin(a),0))
    h=cylinder('Tuerca M2',4.2/math.cos(math.pi/6),-23.2,-21.3,xy,vertices=6);h.rotation_euler.z=a-math.pi/6;boolean(o,h)
    s=cube('Entrada lateral tuerca',(6.5,4.3,1.9),(x-2.85*n.x,y-2.85*n.y,-22.25));s.rotation_euler.z=a;boolean(o,s)

def display_cage():
    o=cylinder('Soporte circular Waveshare',51.6,0,10.7)
    bore(o,47.6,-1,12)
    for x,y in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):
        union(o,cylinder('Apoyo inserto OEM',5.8,0,2.5,(x,y)))
        a=math.atan2(y,x);r=math.hypot(x,y);end=26.1;length=end-r
        b=cube('Puente apoyo OEM',(length+1.0,5.0,2.5),(math.cos(a)*(r+end)/2,math.sin(a)*(r+end)/2,1.25));b.rotation_euler.z=a;union(o,b)
        bore(o,2.4,-1,2.6,(x,y))
    for xy in SCREWS:
        union(o,cylinder('Pilar cierre frontal',6,0,5.8,xy))
        bore(o,1.8,.6,6.5,xy);bore(o,2.4,-1,.6,xy)
    # Space behind the microSD socket (service by opening the case).
    boolean(o,cube('Reserva microSD',(17.5,18,3.6),(15.25,.25,7.9)))
    return o

def button(front,feature,index):
    p=Vector(feature['actuator_face_center_case_relative_mm']);p.z+=10.13000196
    n=Vector(feature['outward_normal_case']).normalized()
    hit,loc,_,_=front.ray_cast(p+n*55,-n)
    if not hit:raise RuntimeError('Missing button surface')
    mouth=(loc-p).dot(n)
    union(front,rcyl('Guia boton',5.4,4.8,mouth-.2,p,n))
    boolean(front,rcyl('Camara collar',5.1,-.6,4.8,p,n));boolean(front,rcyl('Taladro boton',3.2,4.7,mouth+4,p,n))
    o=rcyl('Pulsador '+str(index),4.4,1.2,4.8,p,n)
    nose=rcyl('Punta',1.6,.25,1.4,p,n)
    lim=radial(cube('Altura punta',(2,1,1.5),(0,0,.75)),p,n)
    boolean(nose,lim,'INTERSECT');union(o,nose);union(o,rcyl('Vastago',2.5,4.4,mouth+1.1,p,n))
    o['axis_origin']=list(p);o['axis_direction']=list(n)
    REPORT.setdefault('buttons',[]).append({'index':index,'origin':list(p),'axis':list(n),'mouth_station':mouth,'bore':3.2,'stem':2.5,'rest_gap':.25,'nose_width_height':[1.6,1.0]})
    return o

def clean(o):
    # Booleans can leave micron-sized duplicate vertices on coincident surfaces.
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000002)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.000002)
    bm.to_mesh(o.data);bm.free()

def export(o,filename,material,flip=False,axis=None):
    finish(o,material)
    if not flip and axis is None:c.export(o,filename);return
    t=dup(o,'PRINT '+o.name)
    if axis is None:t.matrix_world=Matrix.Rotation(math.pi,4,'X')@t.matrix_world
    else:
        p,n=map(Vector,axis);u=Vector((-n.y,n.x,0));z=Vector((0,0,1))
        b=Matrix((u,z,n)).transposed().to_4x4();b.translation=p
        t.matrix_world=Matrix.Rotation(math.pi,4,'X')@b.inverted()
    c.export(t,filename);c.PARTS.remove(t);bpy.data.objects.remove(t,do_unlink=True);c.PARTS.append(o)

def bounds(o):
    q=np.asarray([list(o.matrix_world@v.co)for v in o.data.vertices]);return q.min(0),q.max(0)
def clearance(a,b,label):
    aa,bb=bounds(a),bounds(b);vol=0.0
    if np.all(aa[1]>bb[0]+1e-5)and np.all(bb[1]>aa[0]+1e-5):
        tmp=dup(a,'TEMP clearance');boolean(tmp,b,'INTERSECT',discard=False)
        bm=bmesh.new();bm.from_mesh(tmp.data);vol=abs(bm.calc_volume())if bm.faces else 0;bm.free();bpy.data.objects.remove(tmp,do_unlink=True)
    row={'a':a.name,'b':b.name,'kind':label,'intersection_mm3':round(vol,6)};REPORT.setdefault('mechanical_checks',[]).append(row)
    if vol>.025:print('COLLISION',row,flush=True);REPORT.setdefault('failed_checks',[]).append(row)

def main(no_render=False):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
    ivory=mat('Marfil',(.87,.81,.73),.43);pink=mat('Rosa suave',(.77,.35,.4),.4);dark=mat('Pantalla',(.008,.015,.025),.26)
    # Reconstruct the measured spherical skin and preserve the original ears.
    # One common sphere controls BOTH sides of the seam, including its tangent.
    outside=ball('Piel comun medida del EchoEar',R);boolean(outside,slab('Plano frontal',BOTTOM,FRONT),'INTERSECT')
    union(outside,source_front())
    front=dup(outside,'01 Frontal EchoEar adaptado');boolean(front,slab('Mitad frontal',.2,25),'INTERSECT')
    cavity=ball('Interior esfera frontal',R-WALL);boolean(cavity,slab('Techo interior',-50,10),'INTERSECT');boolean(front,cavity)
    union(front,display_cage())
    bore(front,49.7,9.99,12.901);bore(front,45.5,12.9,25)
    port(front,12.6,8.2,22,45,4.83,1.5);port(front,16,10,27,45,5.7,2)
    for yy in (10.958917046,-11.738123269):boolean(front,cylinder('Conducto micro',1.8,-45,-17,(yy,3.8),axis='X'))
    features=json.loads((ROOT/'referencias/medidas_waveshare.json').read_text(encoding='utf-8'))['features']
    buttons=[button(front,f,i+1)for i,f in enumerate([f for f in features if 'actuator_face_center_case_relative_mm'in f])]
    back=dup(outside,'02 Trasera EchoEar adaptada');boolean(back,slab('Mitad trasera',BOTTOM,0),'INTERSECT')
    boolean(back,ball('Interior trasera',R-WALL))
    for xy in SCREWS:union(back,cylinder('Torre cierre',7,BOTTOM,0,xy))
    for xy in STACK:
        union(back,cylinder('Pilar bandejas',8,BOTTOM,-19.3,xy));bore(back,2.4,-25,-19.2,xy);nut_slot(back,xy)
    boolean(back,outside,'INTERSECT')
    for xy in SCREWS:bore(back,2.4,BOTTOM-2,.1,xy);bore(back,4.4,BOTTOM-2,-4,xy)
    for xy in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):bore(back,4.4,-2.5,.2,xy)
    for yy in (-7,-3,1,5,9):boolean(back,cylinder('Salida sonido',1.8,-45,-20,(yy,-7),axis='X'))
    carrier=load_stl(ROOT/'referencias/carrier.stl','03 Bandeja bateria GPS',REG['04_bandeja_bateria_y_GPS.stl'])
    boolean(carrier,ball('Holgura bandeja a piel esferica',R-WALL-.3),'INTERSECT')
    speaker=load_stl(ROOT/'referencias/speaker.stl','04 Soporte altavoz',REG['05_soporte_altavoz.stl'])
    spacer=load_stl(ROOT/'referencias/spacer.stl','05 Separador 7.7mm',REG['06_separador_interno_7_7mm.stl'])
    other=dup(spacer,'05 Separador segundo');other.location.x+=STACK[1][0]-STACK[0][0];other.location.y+=STACK[1][1]-STACK[0][1]
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'auditoria/pre_export.blend'))
    export(front,'01_frontal_gato_EchoEar.stl',ivory,flip=True)
    export(back,'02_trasera_EchoEar.stl',ivory,flip=True)
    export(carrier,'03_bandeja_bateria_GPS.stl',ivory);export(speaker,'04_soporte_altavoz.stl',ivory);export(spacer,'05_separador_7_7mm.stl',pink);finish(other,pink)
    for i,b in enumerate(buttons):export(b,'06_boton_inferior.stl'if i==0 else'07_boton_superior.stl',pink,axis=(b['axis_origin'],b['axis_direction']))
    gauge=cylinder('08 Prueba pantalla',56,0,3);bore(gauge,49.7,-1,4);export(gauge,'08_prueba_pantalla.stl',ivory);gauge.hide_render=True;gauge.hide_set(True)
    battery=rect('ENV EEMB500',26.5,42,2,-17.7,-10.3,(1,-2));gps=cube('ENV GNSS27',(27,27,6.7),(1,1,-23.05))
    sp=rect('ENV altavoz',32.5,22.5,.3,-8.8,-5,(1,1));adapter=cube('ENV adaptador',(8,8,6),(-18,-3,-14.4))
    for a in (front,back):
        for b in (carrier,speaker,spacer,other,*buttons,battery,gps,sp,adapter):clearance(a,b,'minimal interior clearance')
    clearance(front,back,'case seam')
    glass=cylinder('ENV glass49.0',48.96,11.8,12.9);clearance(front,glass,'screen seating');clearance(back,glass,'screen seating')
    if REPORT.get('failed_checks'):
        (ROOT/'auditoria/interferencias.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8');raise RuntimeError('Interference')
    for o in (battery,gps,sp,adapter,glass):bpy.data.objects.remove(o,do_unlink=True)
    REPORT.update({'pass':True,'validation_mode':'quick','scope':'Mesh topology and static clearances only; no full button, hardware, electronics or physical tests.',
      'exterior':{'source':'EchoEar supplied 3MF','source_sha256':json.loads((ROOT/'auditoria/source.json').read_text())['source_sha256'],'source_scale':SCALE,'sphere_radius_mm':R,'sphere_center_z':ZC,'front_plane_z':FRONT,'seam_gap':.2,'common_curvature_both_halves':True,'front_surface_radius_at_seam':math.sqrt(R*R-(.2-ZC)**2),'rear_surface_radius_at_seam':math.sqrt(R*R-ZC**2),'original_ear_mesh_retained':True},
      'assembly_dimensions_mm':(np.maximum(bounds(front)[1],bounds(back)[1])-np.minimum(bounds(front)[0],bounds(back)[0])).tolist(),
      'battery_dimensions_mm':[24.5,40,5.9],'gps_dimensions_mm':[27,27,6.7],
      'print_orientation':{'front':'front flat face on bed, rotated aboutX','back':'open mating rim on bed, rotated aboutX; internal supports required'},
      'stl_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))},
      'source_files_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ('generar.py','cad_base.py','parametros.json')}})
    (ROOT/'validacion.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    # Editable component references; display-face animation below is a preview.
    finish(cube('REF EEMB24.5x40x5.9',(24.5,40,5.9),(1,-2,-14.75),.3),pink)
    finish(cube('REF GNSS27x27x6.7',(27,27,6.7),(1,1,-23.05),.2),ivory)
    finish(cube('REF Altavoz32x22x3.5',(32,22,3.5),(1,1,-7.05),.3),dark)
    finish(cylinder('REF Pantalla49',48.96,11.8,12.9),dark)
    sc.render.engine='CYCLES';sc.cycles.samples=16;sc.cycles.use_denoising=True;sc.render.resolution_x=1200;sc.render.resolution_y=1200;sc.render.resolution_percentage=100;sc.world.color=(.25,.24,.23)
    for loc,power in [((-80,80,140),700000),((100,30,100),450000),((20,-80,-120),500000)]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=105;c.aim(o,(0,0,-8))
    bpy.ops.object.camera_add(location=(90,30,160));cam=bpy.context.object;cam.name='Camara';cam.data.type='ORTHO';cam.data.ortho_scale=112;c.aim(cam,(0,0,-8));sc.camera=cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion();area.spaces.active.region_3d.view_distance=125;area.spaces.active.region_3d.view_location=(0,0,-8)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'EchoEar_V7_montaje.blend'))
    if no_render:return
    for x in (-7,7):
        e=c.ellipse_prism('REF Ojos',5.4,7.2,12.91,12.96);e.location.x=x;e.location.y=1.5;finish(e,ivory)
    for x in (-12,12):
        e=c.ellipse_prism('REF Colorete',5,2,12.91,12.96);e.location.x=x;e.location.y=-4;finish(e,pink)
    render('01_gato_curva_continua.png',(90,30,160),(0,1,-7),110)
    render('02_perfil_union.png',(150,8,18),(0,0,-8),110)
    render('03_trasera.png',(80,30,-155),(0,0,-10),110)
    front.hide_render=True;back.hide_render=True
    for o in bpy.data.objects:
        if o.name.startswith(('REF Pantalla','REF Ojos','REF Colorete')):o.hide_render=True
    render('04_interior.png',(70,-45,-130),(0,0,-7),108)
    print('ECHOEAR_V7_DONE',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--no-render',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if'--'in sys.argv else[]);main(a.no_render)
