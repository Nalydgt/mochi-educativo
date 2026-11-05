"""Peluqo restart: original TamaPoke screen interface, three large printed parts."""
from pathlib import Path
import sys,json,math,itertools,hashlib,subprocess,shutil,os
import bpy,bmesh,numpy as np
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import cad_base as c
import base_geom as g
from cad_base import cylinder,cube,boolean,union,dup,finish,mat,render
P=c.P;REPORT=c.REPORT
R=34.;ZC=-3.;FRONT=15.;BOTTOM=-37.;WALL=2.
g.R=R;g.ZC=ZC;g.FRONT=FRONT;g.BOTTOM=BOTTOM
SCREWS=P['case_screws']['centers'];STEMS=P['tray']['stems'];SEATS=P['tray']['seats']
N=Vector(P['base']['normal_model']);LEVEL=P['base']['plane_offset'];THICK=2.4

def bore(o,d,z0,z1,xy=(0,0)):boolean(o,cylinder('Paso',d,z0,z1,xy))
def slab(z0,z1):return cube('Limite Z',(130,130,z1-z0),(0,0,(z0+z1)/2))
def halfspace(start,end):
    o=cube('Plano base',(150,150,end-start),(0,0,0));o.rotation_euler=Vector((0,0,1)).rotation_difference(N).to_euler();o.location=N*((start+end)/2);return o
def rect(name,w,h,r,z0,z1,xy=(0,0)):
    o=c.rounded_prism(name,w,h,r,z0,z1);o.location.x,o.location.y=xy;return o
def bridge(name,p,q,width,z0,z1):
    dx,dy=q[0]-p[0],q[1]-p[1]
    o=cube(name,(math.hypot(dx,dy)+1,width,z1-z0),((p[0]+q[0])/2,(p[1]+q[1])/2,(z0+z1)/2));o.rotation_euler.z=math.atan2(dy,dx);return o
def original_front():
    d=np.load(ROOT/'referencias/tamapoke_meshes.npz');v=d['vertices_1'];f=d['faces_1']
    me=bpy.data.meshes.new('TamaPoke original');me.from_pydata(v.tolist(),[],f.tolist());me.update()
    o=bpy.data.objects.new('01 Frontal original adaptado',me);bpy.context.collection.objects.link(o);return o,v

def add_v10_ears(front):
    old=g.load_stl(ROOT/'referencias/orejas_v10.stl','Referencia real V10')
    for v in old.data.vertices:
        v.co.y=-v.co.y;v.co.z=13.7-v.co.z
    old_center=Vector((0,0,-1.839513093));new_center=Vector((0,0,ZC))
    for side in (-1,1):
        # Retain the actual V10 silhouette and rounded tips. Fill the extracted
        # ear as one solid; copying shell scraps leaves a cut-open ear.
        points=[v.co.copy() for v in old.data.vertices if v.co.x*side>8 and v.co.y>22 and v.co.z>=-.001]
        bm=bmesh.new()
        for point in points:
            point.x-=side*1.8;point.y+=1.0;point.z+=1.4
            bm.verts.new(point)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
        bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
        loose=[v for v in bm.verts if not v.link_faces]
        if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
        me=bpy.data.meshes.new('Oreja V10 cerrada');bm.to_mesh(me);bm.free()
        ear=bpy.data.objects.new('Oreja V10 integrada',me);bpy.context.collection.objects.link(ear);c.recalc(ear)
        p=Vector((19.019122995,12.663508894,5.100002766));n=Vector((.829108979,.559087025,0))
        hit,loc,_,_=front.ray_cast(p+n*55,-n)
        if not hit:raise RuntimeError('Button surface missing')
        tip=(loc-p).dot(n)+1.1
        boolean(ear,g.rcyl('Acceso redondo boton superior',10.6,tip-.25,tip+6.2,p,n))
        bore(ear,53,-1,18);boolean(ear,slab(0,15),'INTERSECT');union(front,ear)
    bpy.data.objects.remove(old,do_unlink=True)
    REPORT['ear_source']={'file':'orejas_v10.stl','sha256':hashlib.sha256((ROOT/'referencias/orejas_v10.stl').read_bytes()).hexdigest(),'rigid_forward_shift_mm':1.4,'rigid_upward_shift_mm':1.0,'rigid_inward_shift_each_mm':1.8,'v10_silhouette_and_rounded_tips':True,'solid_hull_with_buried_root':True,'front_plane_trim_z':15}

def normalize(o):
    me=o.data;me.calc_loop_triangles();v=np.asarray([tuple(p.co)for p in me.vertices]);f=np.asarray([tuple(t.vertices)for t in me.loop_triangles],dtype=np.uint64)
    src=ROOT/'auditoria/input.npz';dst=ROOT/'auditoria/clean.npz';np.savez_compressed(src,vertices=v,faces=f)
    python=os.environ.get('PELUQO_PYTHON')or shutil.which('python')
    result=subprocess.run([python,str(ROOT/'limpiar_malla.py'),str(src),str(dst)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
    if result.returncode:raise RuntimeError(result.stderr)
    clean=np.load(dst);out=bpy.data.meshes.new(o.name+' valid');out.from_pydata(clean['vertices'].tolist(),[],clean['faces'].tolist());out.update();o.data=out

def head():
    front,source=original_front()
    # The original seat, internal throat, supports and screw centers are kept.
    # Only the exterior outside radius27.2 is added/trimmed to a common sphere.
    outer=g.ball('Piel redonda frontal',R);boolean(outer,slab(0,FRONT),'INTERSECT');bore(outer,54.4,-1,16)
    union(front,outer);boolean(front,g.ball('Contorno comun',R),'INTERSECT')
    add_v10_ears(front)
    male=cylinder('Labio interior',64.6,-1.4,.8);bore(male,62.6,-2,1);union(front,male)
    # Close the old single bore only in the button region; create the two
    # registered plunger guides without changing the screen's original seat.
    n=(math.cos(math.radians(35)),math.sin(math.radians(35)),0)
    patch=g.rcyl('Cierre paso antiguo',5.8,27,31,(0,0,5),n);boolean(patch,cylinder('Limite parche original',60,-1,16),'INTERSECT');union(front,patch)
    g.port(front,13,8.6,26.7,45,4.83,1.7);g.port(front,16.4,10.4,29,45,5.7,2.2)
    for yy in (10.958917046,-11.738123269):boolean(front,cylinder('Conducto micro',1.8,-45,-17,(yy,3.8),axis='X'))
    features=json.loads((ROOT/'referencias/medidas_waveshare.json').read_text(encoding='utf-8'))['features']
    buttons=[g.button(front,f,i+1)for i,f in enumerate([f for f in features if 'actuator_face_center_case_relative_mm'in f])]
    return front,buttons,source

def body():
    outer=g.ball('Limite exterior cuerpo',R);boolean(outer,slab(BOTTOM-1,0),'INTERSECT')
    back=dup(outer,'02 Cuerpo redondo');boolean(back,g.ball('Interior cuerpo',R-WALL))
    for xy in SCREWS:union(back,cylinder('Pilar cierre original',7,BOTTOM-1,0,xy))
    for xy in SEATS:
        union(back,cylinder('Asiento bandeja',5.6,BOTTOM-1,-6,xy));union(back,cylinder('Guia sin tornillo',2.4,-6.1,-4.4,xy))
    boolean(back,outer,'INTERSECT')
    boolean(back,halfspace(-100,LEVEL))
    floor=g.ball('Suelo integrado',R);boolean(floor,slab(BOTTOM-1,0),'INTERSECT');boolean(floor,halfspace(LEVEL,LEVEL+THICK),'INTERSECT');union(back,floor)
    groove=cylinder('Encaje hembra',65.2,-1.7,.1);bore(groove,61.6,-2,.2);boolean(back,groove)
    for xy in SCREWS:bore(back,2.4,BOTTOM-2,.1,xy);bore(back,4.4,BOTTOM-2,-4,xy)
    for xy in ((0,20.2),(-13.75,-14.79789),(13.75,-14.79789)):bore(back,4.8,-2.6,.1,xy)
    for yy in (-7,-3,1,5,9):boolean(back,cylinder('Salida sonido',1.8,-45,-17,(yy,-7),axis='X'))
    return back

def tray():
    o=rect('03 Bandeja unica',28.5,44,3,-19.3,-17.7,(1,-3.2))
    union(o,rect('Techo antena',31,31,3,-19.3,-17.7,(1,0)))
    rail=rect('Guia bateria',28.5,44,3,-17.9,-14.5,(1,-3.2));boolean(rail,rect('Reserva bateria',26.5,42,2,-20,-13,(1,-3.2)))
    boolean(rail,cube('Entrada longitudinal bateria',(27,9,7),(1,-24,-16)));boolean(rail,cube('Salida cables',(8,6,7),(1,18,-16)));union(o,rail)
    for x in (-12.25,14.25):boolean(o,rect('Paso cinta',2,7,.5,-21,-13,(x,-19.5)))
    gps=rect('Guias antena',30.4,30.4,2,-26.9,-19.1,(1,0));boolean(gps,rect('Reserva antena',28,28,.6,-28,-18,(1,0)))
    for x,y,w,h in [(1,-14.2,6,4),(1,14.2,6,4),(-13.2,0,4,6),(15.2,0,4,6)]:boolean(gps,cube('Salida coaxial',(w,h,4.3),(x,y,-21.25)))
    union(o,gps)
    for i,p in enumerate(STEMS):
        union(o,cylinder('Raiz columna',6 if i==2 else 8,-19.3,-17.6,p))
        union(o,bridge('Puente columna',p,(max(-10,min(12,p[0])),max(-16,min(16,p[1]))),6,-19.3,-17.7))
        union(o,cylinder('Columna integrada',5.6,-19.3,-4,p))
    speaker=rect('Suelo altavoz',36.5,26.5,3,-10,-8.8,(1,1));wall=rect('Borde altavoz',36.5,26.5,3,-9,-6.8,(1,1));boolean(wall,rect('Hueco altavoz',32.5,22.5,.3,-11,-6,(1,1)));union(speaker,wall)
    for p in STEMS[:2]:union(speaker,bridge('Union soporte altavoz',p,(max(-14,min(16,p[0])),p[1]),5.6,-10,-8.8))
    union(o,speaker)
    for p,q in zip(STEMS,SEATS):
        union(o,bridge('Brazo de retencion',p,q,5.6,-5.8,-4))
        union(o,cylinder('Apoyo aprisionado por frontal',4.8,-6,0,q));bore(o,3,-6.1,-4.1,q)
    for xy in SCREWS:bore(o,8,-40,1,xy)
    limit=g.ball('Holgura interior bandeja',R-WALL-.3);boolean(limit,halfspace(LEVEL+THICK+.3,100),'INTERSECT');boolean(o,limit,'INTERSECT')
    return o

def protected_surface(front,source):
    v=[front.matrix_world@p.co for p in front.data.vertices];f=[tuple(p.vertices)for p in front.data.polygons];tree=BVHTree.FromPolygons(v,f,all_triangles=True)
    r=np.hypot(source[:,0],source[:,1]);keep=((r<=26)&(source[:,2]>=8.5))|((r<=22)&(source[:,2]<=2.5))
    errors=[tree.find_nearest(Vector(p))[3]for p in source[keep]];maximum=max(errors)
    if maximum>.005:raise RuntimeError('Original screen interface altered: '+str(maximum))
    return {'original_vertices_checked':len(errors),'maximum_surface_difference_mm':maximum,'original_seat_and_oem_mounts_preserved':True,'seat_diameter_mm':49.5,'source_fit_confirmed_by_user':True}

def checks(front,back,rack,buttons):
    for a,b in itertools.combinations([front,back,rack,*buttons],2):g.clearance(a,b,'assembled parts')
    bat=rect('ENV battery',26.5,42,2,-17.7,-10.3,(1,-3.2));gps=cube('ENV complete GPS',(27,27,6.7),(1,0,-23.05));sp=rect('ENV speaker',32.5,22.5,.3,-8.8,-5,(1,1));adapter=cube('ENV adapter',(8,8,6),(-18,-3,-14.4))
    for env in (bat,gps,sp,adapter):
        for shell in (front,back,rack):g.clearance(env,shell,'component reserve')
        bpy.data.objects.remove(env,do_unlink=True)
    for t in (0,2,5,15):
        tmp=dup(rack,'ENV tray entry');tmp.location.z+=t;g.clearance(tmp,back,'tray drops into body, dz='+str(t));bpy.data.objects.remove(tmp,do_unlink=True)
    for t in (1,3):
        tmp=dup(front,'ENV front entry');tmp.location.z+=t;g.clearance(tmp,back,'front insertion, dz='+str(t));bpy.data.objects.remove(tmp,do_unlink=True)
    for b in buttons:
        tmp=dup(b,'ENV pressed');tmp.location-=Vector(b['axis_direction'])*.45
        for shell in (front,back,rack):g.clearance(tmp,shell,'single pressed position')
        bpy.data.objects.remove(tmp,do_unlink=True)
    upper=buttons[1];p=Vector(upper['axis_origin']);n=Vector(upper['axis_direction']);tip=max((upper.matrix_world@v.co-p).dot(n)for v in upper.data.vertices)
    access=g.rcyl('ENV button access D10',10,tip-.2,tip+6,p,n)
    # Exclude the normal spherical skin: this check concerns the ears.
    exposed=dup(front,'ENV external ears');boolean(exposed,g.ball('Main head skin',R+.02));g.clearance(access,exposed,'upper button vs ears');bpy.data.objects.remove(exposed,do_unlink=True);bpy.data.objects.remove(access,do_unlink=True)
    for xy in SCREWS:
        bolt=cylinder('ENV closing M2',2,-4,.55,xy);union(bolt,cylinder('ENV M2 head',3.8,-6,-4,xy))
        for part in (front,back,rack):g.clearance(bolt,part,'original rear closing screw free envelope')
        bpy.data.objects.remove(bolt,do_unlink=True)

def aim(o,target):
    f=(Vector(target)-o.location).normalized();r=f.cross(Vector((0,0,1))).normalized();u=r.cross(f);o.rotation_euler=Matrix((r,u,-f)).transposed().to_quaternion().to_euler()

def stability(back,parts):
    n=np.asarray(N);t=np.array([0,-n[2],n[1]])
    coords=np.asarray([list(back.matrix_world@v.co)for v in back.data.vertices]);foot=coords[abs(coords@n-LEVEL)<.0001]
    points=sorted(set(map(tuple,np.round(np.c_[foot[:,0],foot@t],6))))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];hi=[]
    for p in points:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(points):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    poly=np.asarray(lo[:-1]+hi[:-1]);edges=np.roll(poly,-1,axis=0)-poly;vc=[]
    for o in parts:
        me=o.data;me.calc_loop_triangles();v=np.asarray([list(o.matrix_world@p.co)for p in me.vertices]);f=np.asarray([t.vertices[:]for t in me.loop_triangles]);q=v[f]
        vol=np.einsum('ij,ij->i',q[:,0],np.cross(q[:,1],q[:,2]))/6;total=vol.sum();vc.append((abs(total),(vol[:,None]*(q[:,0]+q[:,1]+q[:,2])/4).sum(0)/total))
    margins=[]
    for density,screen_m,gps_m,speaker_m in itertools.product((1.,1.3),(15,35),(10,22),(2,8)):
        masses=[v*density/1000 for v,com in vc];mass=sum(masses);moment=sum((m*com for m,(v,com)in zip(masses,vc)),np.zeros(3))
        for m,pos in [(15,(1,-3.2,-14.75)),(screen_m,(0,0,8)),(gps_m,(1,0,-23.05)),(speaker_m,(1,1,-7.05)),(2,(0,0,-4))]:mass+=m;moment+=m*np.asarray(pos)
        com=moment/mass;offset=np.array([com[0],com@t])-poly;margins.append(float(np.min((edges[:,0]*offset[:,1]-edges[:,1]*offset[:,0])/np.linalg.norm(edges,axis=1))))
    if min(margins)<3:raise RuntimeError('Insufficient stability estimate')
    return {'face_angle_degrees':65,'minimum_estimated_margin_mm':min(margins),'scope':'Uniform plastic1.0..1.3g/cm3; screen15..35g, GPS10..22g, speaker2..8g, battery15g, hardware2g. Not a physical tilt test.'}

def main():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
    ivory=mat('Marfil',(.86,.8,.72),.42);pink=mat('Rosa suave',(.77,.35,.4),.4);dark=mat('Pantalla',(.008,.015,.025),.3)
    front,buttons,source=head();back=body();rack=tray();parts=[front,back,rack,*buttons]
    for o in parts:normalize(o);finish(o,pink if o in buttons else ivory)
    REPORT['original_screen_interface']=protected_surface(front,source)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'auditoria/pre_checks.blend'))
    checks(front,back,rack,buttons)
    if REPORT.get('failed_checks'):
        (ROOT/'auditoria/interferencias.json').write_text(json.dumps(REPORT['failed_checks'],indent=2),encoding='utf-8');raise RuntimeError('Unresolved interference')
    for o,name in [(front,'01_frontal_TamaPoke_gato.stl'),(back,'02_cuerpo_redondo.stl'),(rack,'03_bandeja_unica.stl')]:g.export(o,name,ivory,flip=o in (front,back))
    for o,name in zip(buttons,('04_boton_inferior.stl','05_boton_superior.stl')):g.export(o,name,pink,axis=(o['axis_origin'],o['axis_direction']))
    REPORT['stability']=stability(back,parts)
    REPORT.update({'pass':True,'validation_mode':'assembly','joint':P['joint'],'printed_pieces':5,'large_pieces':3,'closing_screws':3,'tray_screws':0,'front_visible_screws':0,'screen_fixings':'Unchanged original TamaPoke internal mounting; reuse original fixings.','source_files_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ('generar.py','base_geom.py','cad_base.py','parametros.json','limpiar_malla.py')},'stl_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))},'limitations':['No physical print/assembly test. Original screen interface preserved instead of substituting a new cage. GPS reference27x27x6.7 and speaker32x22x3.5 require actual part confirmation.']})
    (ROOT/'validacion.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    # Nominal references illustrate the unchanged source front seat; no
    # substitute display clamp or new front fastener is introduced.
    finish(cylinder('REF glass preview',48.96,13.9,14.9),dark)
    finish(cube('REF battery',(24.5,40,5.9),(1,-3.2,-14.75),.3),pink);finish(cube('REF GNSS27',(27,27,6.7),(1,0,-23.05),.2),ivory);finish(cube('REF speaker',(32,22,3.5),(1,1,-7.05),.3),dark)
    for x in (-7,7):
        eye=c.ellipse_prism('REF eyes',5.4,7.2,14.91,14.96);eye.location.x=x;eye.location.y=1.5;finish(eye,ivory)
    for x in (-12,12):
        cheek=c.ellipse_prism('REF cheeks',5,2,14.91,14.96);cheek.location.x=x;cheek.location.y=-4;finish(cheek,pink)
    root=bpy.data.objects.new('Montaje Peluqo',None);bpy.context.collection.objects.link(root)
    for o in list(bpy.data.objects):
        if o.type=='MESH':o.parent=root
    root.rotation_euler.x=math.radians(65);root.location.z=-LEVEL
    c.aim=aim;sc.render.engine='CYCLES';sc.cycles.samples=20;sc.cycles.use_denoising=True;sc.render.resolution_x=1200;sc.render.resolution_y=1200;sc.world.color=(.25,.24,.23)
    for loc,power in [((-90,-90,140),750000),((100,-20,130),500000),((0,100,100),500000)]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=110;aim(o,(0,0,32))
    bpy.ops.object.camera_add(location=(95,-160,100));cam=bpy.context.object;cam.name='Camara';cam.data.type='ORTHO';cam.data.ortho_scale=108;aim(cam,(0,0,33));sc.camera=cam
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Peluqo_V12_montaje.blend'))
    floor=cube('Suelo visual',(240,240,.2),(0,0,-.15));finish(floor,mat('Suelo',(.2,.22,.24),.7))
    render('01_Peluqo_simple.png',(95,-160,100),(0,0,33),108)
    render('02_perfil.png',(150,-35,65),(0,0,33),108)
    front.location.z+=20
    for o in buttons:o.location.z+=20
    for o in bpy.data.objects:
        if o.name.startswith(('REF glass','REF eyes','REF cheeks')):o.location.z+=20
    render('03_montaje_tres_piezas.png',(95,-160,125),(0,-6,38),132)
    front.hide_render=True
    for o in buttons:o.hide_render=True
    for o in bpy.data.objects:
        if o.name.startswith(('REF glass','REF eyes','REF cheeks')):o.hide_render=True
    rack.location.z+=22
    for o in bpy.data.objects:
        if o.name.startswith(('REF battery','REF GNSS','REF speaker')):o.location.z+=22
    render('04_bandeja_unica.png',(95,-160,125),(0,-3,39),132)
    print('PELUQO_V12_COMPLETE',flush=True)

if __name__=='__main__':main()
