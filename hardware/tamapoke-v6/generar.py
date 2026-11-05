"""Personal 3MF-based TamaPoke V6: EEMB500, GPS, two buttons, cat/mochi."""
from pathlib import Path
import sys,json,math,argparse,hashlib,itertools
import numpy as np
import bpy,bmesh
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import cad_base as c
from cad_base import cube,cylinder,boolean,union,dup,finish,mat,aim,render
P=c.P;REPORT=c.REPORT;PARTS=c.PARTS
SCREWS=P['case_screws']['centers'];STACK=P['internal_stack']['mount_centers']
BOTTOM=float(P['body']['rear_bottom']);GLASS_Z=12.9;OFFSET=GLASS_Z-2.76999804
M=json.loads((ROOT/'auditoria/step_measurements_independent.json').read_text(encoding='utf-8'))
BUTTONS=[f for f in M['features'] if 'actuator_face_center_native_mm' in f]

def rect(name,w,h,r,z0,z1,xy=(0,0)):
    o=c.rounded_prism(name,w,h,r,z0,z1);o.location.x,o.location.y=xy;return o
def bore(obj,d,z0,z1,xy=(0,0)):return boolean(obj,cylinder('Paso '+str(d),d,z0,z1,xy))
def radial(o,p,n):
    n=Vector(n).normalized();t=Vector((-n.y,n.x,0));z=Vector((0,0,1))
    basis=Matrix((t,z,n)).transposed().to_4x4();basis.translation=Vector(p)
    o.matrix_world=basis@o.matrix_world;c.activate(o)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);return o
def rcyl(name,d,s0,s1,p,n):return radial(cylinder(name,d,s0,s1),p,n)
def rbox(name,w,h,s0,s1,p,n):return radial(cube(name,(w,h,s1-s0),(0,0,(s0+s1)/2)),p,n)
def original_front():
    data=np.load(ROOT/'referencias/mallas_originales.npz')
    mesh=bpy.data.meshes.new('Original TamaPoke HOUSING_1')
    mesh.from_pydata(data['vertices_1'].tolist(),[],data['faces_1'].tolist());mesh.update()
    o=bpy.data.objects.new('Frontal fuente',mesh);bpy.context.collection.objects.link(o);return o
def freeze_triangles(o):
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm,faces=list(bm.faces),ngon_method='EAR_CLIP')
    bm.to_mesh(o.data);bm.free();c.recalc(o)
def deform_front(o,cat):
    freeze_triangles(o)
    for v in o.data.vertices:
        x,y,z=v.co;r=math.hypot(x,y)
        if r<=25.4:continue
        q=min(1,max(0,(r-25.4)/2.8));q=q*q*(3-2*q)
        w=min(1,max(0,z/3));w=w*w*(3-2*w)
        bump=0.8
        if cat:
            theta=math.atan2(y,x)
            for angle in (58,122):
                delta=abs(math.degrees(math.atan2(math.sin(theta-math.radians(angle)),math.cos(theta-math.radians(angle)))))
                taper=min(1,max(0,(22-delta)/8));taper=taper*taper*(3-2*taper)
                bump+=14*math.exp(-0.5*(delta/8)**2)*taper
        scale=(r+bump*q*w)/r;v.co.x*=scale;v.co.y*=scale
    o.data.update();c.recalc(o)
def correct_oem_holes(o):
    # Move each existing circular interface with its surrounding vertices.
    # This avoids sliver faces from two almost coincident cylindrical cuts.
    freeze_triangles(o)
    for x,old_y,new_y in [(0,20.2,20.5),(-13.75,-14.79789,-14.7),(13.75,-14.79789,-14.7)]:
        for v in o.data.vertices:
            dx,dy=v.co.x-x,v.co.y-old_y;r=math.hypot(dx,dy)
            if r>2.25 or v.co.z>2.5001 or r<1e-8:continue
            t=min(1,max(0,(2.25-r)/(2.25-1.16)));t=t*t*(3-2*t)
            v.co.x+=t*dx*(1.2/1.15-1)
            v.co.y+=t*((new_y-old_y)+dy*(1.2/1.15-1))
    o.data.update();c.recalc(o)
def dome_profile(inner=False):
    """Continuous rounded rear with a small flat print landing.

    Offset the meridian along its normal; subtracting two from each radius
    would produce walls thinner than two on the sloping dome.
    """
    d=P['body']['dome'];R=d['max_radius'];center=d['equator_z']
    foot=d['landing_diameter']/2;power=d['exponent'];wall=P['body']['wall']
    height=(center-BOTTOM)/(1-(foot/R)**2)**(1/power)
    profile=[]
    for z in np.linspace(BOTTOM,center,129):
        t=(center-z)/height
        r=R*math.sqrt(max(0,1-t**power))
        dr=R*power*t**(power-1)/(2*height*math.sqrt(max(1e-12,1-t**power)))
        if inner:
            norm=math.sqrt(1+dr*dr);r-=wall/norm;z+=wall*dr/norm
            z=max(z,BOTTOM+wall)
        profile.append((float(z),float(r)))
    # Slightly fuller shoulder joins the original sixty millimetre seam.
    top=-P['body']['seam_gap'];span=top-center
    for j in range(1,33):
        t=j/32;z=center+t*span;r=30+(R-30)*(1+math.cos(math.pi*t))/2
        dr=-(R-30)*math.pi/(2*span)*math.sin(math.pi*t)
        if inner:
            norm=math.sqrt(1+dr*dr);r-=wall/norm;z+=wall*dr/norm
        profile.append((float(z),float(r)))
    if inner:profile.append((2.0,28.0))
    return profile

def rounded_back(name,inner=False,limit=False):
    rings=dome_profile(inner);N=256
    if limit:rings.append((.01,30))
    verts=[(r*math.cos(math.tau*j/N),r*math.sin(math.tau*j/N),z)for z,r in rings for j in range(N)]
    faces=[tuple(reversed(range(N)))]
    for k in range(len(rings)-1):
        for j in range(N):faces.append((k*N+j,k*N+(j+1)%N,(k+1)*N+(j+1)%N,(k+1)*N+j))
    faces.append(tuple((len(rings)-1)*N+j for j in range(N)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);c.recalc(o);return o
def nut_slot(o,xy,z0,z1):
    x,y=xy;a=math.atan2(y,x);n=Vector((math.cos(a),math.sin(a),0))
    # Blender's 6-sided cylinder starts with a 30-degree phase. Cancel that
    # phase so a vertex points along the entry axis and its tangent width is AF.
    h=cylinder('Tuerca M2 lateral',4.2/math.cos(math.pi/6),z0,z1,xy,vertices=6);h.rotation_euler.z=a-math.pi/6;boolean(o,h)
    slot=cube('Entrada lateral M2',(6.5,4.3,z1-z0),(x-n.x*2.85,y-n.y*2.85,(z0+z1)/2));slot.rotation_euler.z=a;boolean(o,slot)
def bbox(o):
    pts=[o.matrix_world@Vector(v)for v in o.bound_box]
    return np.array([[min(v[i]for v in pts)for i in range(3)],[max(v[i]for v in pts)for i in range(3)]])
def collision(a,b,label='clearance',allowed=0.025):
    aa,bb=bbox(a),bbox(b);vol=0
    if np.all(aa[1]>bb[0]+1e-5)and np.all(bb[1]>aa[0]+1e-5):
        tmp=dup(a,'TEMP intersection');boolean(tmp,b,'INTERSECT',discard=False,solver='EXACT')
        bm=bmesh.new();bm.from_mesh(tmp.data);vol=abs(bm.calc_volume())if bm.faces else 0;bm.free();bpy.data.objects.remove(tmp,do_unlink=True)
    row={'a':a.name,'b':b.name,'kind':label,'intersection_mm3':round(vol,6),'allowed_mm3':allowed}
    REPORT.setdefault('mechanical_checks',[]).append(row)
    if vol>allowed:REPORT.setdefault('failed_checks',[]).append(row);print('COLLISION',json.dumps(row),flush=True)
    return vol
def export(o,name,material,axis=None):
    bm=bmesh.new();bm.from_mesh(o.data);bad=[e for e in bm.edges if not e.is_manifold]
    if bad:print('RAW_BAD',name,[(len(e.link_faces),e.calc_length())for e in bad[:8]],flush=True)
    bm.free()
    if name=='03_cuerpo_sin_carga_magnetica.stl':
        bm=bmesh.new();bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000002)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.000002)
        bm.to_mesh(o.data);bm.free()
    finish(o,material)
    if axis is None:c.export(o,name);return
    p,n=map(Vector,axis);t=Vector((-n.y,n.x,0));z=Vector((0,0,1))
    basis=Matrix((t,z,n)).transposed().to_4x4();basis.translation=p
    tmp=dup(o,o.name+' PRINT');tmp.matrix_world=Matrix.Rotation(math.pi,4,'X')@basis.inverted()
    c.export(tmp,name);PARTS.remove(tmp);bpy.data.objects.remove(tmp,do_unlink=True);PARTS.append(o)
def step_refs():
    d=np.load(ROOT/'referencias/step_mesh_native.npz');src=d['vertices'];v=np.c_[src[:,0],-src[:,2],src[:,1]+OFFSET]
    rows=json.loads((ROOT/'auditoria/step_parts.json').read_text(encoding='utf-8'));refs=[]
    for row in rows:
        f=d['faces_'+str(row['tag'])];ids,inv=np.unique(f.reshape(-1),return_inverse=True)
        mesh=bpy.data.meshes.new('CAD '+str(row['tag']));mesh.from_pydata(v[ids].tolist(),[],inv.reshape(-1,3).tolist());mesh.update()
        o=bpy.data.objects.new('CAD '+str(row['tag'])+' '+row['name'].split('/')[-1],mesh);bpy.context.collection.objects.link(o);o['cad_tag']=row['tag'];refs.append(o)
    return refs
def make_button(fronts,feature,i):
    p=Vector(feature['actuator_face_center_case_relative_mm']);p.z+=OFFSET
    n=Vector(feature['outward_normal_case']);n.normalize()
    hit,loc,_,_=fronts[0].ray_cast(p+n*50,-n)
    if not hit:raise RuntimeError('Button ray missed source housing')
    mouth=(loc-p).dot(n)
    for f in fronts:
        union(f,rcyl('Guia interior boton '+str(i),5.4,4.8,mouth-0.2,p,n))
        boolean(f,rcyl('Camara collar boton '+str(i),5.0,-0.6,4.8,p,n))
        boolean(f,rcyl('Paso boton '+str(i),3.2,4.7,mouth+4,p,n))
    collar=rcyl('Pulsador '+str(i),4.4,1.2,4.8,p,n)
    nose=rcyl('Punta boton',1.6,0.25,1.4,p,n)
    boolean(nose,rbox('Limite vertical punta',2.0,1.0,0.2,1.5,p,n),'INTERSECT')
    union(collar,nose)
    union(collar,rcyl('Vastago boton',2.5,4.4,mouth+1.1,p,n))
    collar['axis_origin']=list(p);collar['axis_direction']=list(n)
    REPORT.setdefault('buttons',[]).append({'id':i,'cap_center':list(p),'outward_axis':list(n),'mouth_station':mouth,'outward_retention_face':4.8,'gap_at_outward_stop':0.25,'tested_press':0.45,'hard_inward_stop':False})
    return collar

def make_rear():
    back=rounded_back('03 Cuerpo sin carga magnetica')
    boolean(back,rounded_back('Interior cuerpo offset normal 2mm',inner=True))
    limit=rounded_back('Limite torres domo',limit=True)
    for xy in SCREWS:
        tower=cylinder('Torre cierre original',7,BOTTOM+1,0,xy)
        union(back,tower)
    for xy in STACK:
        tower=cylinder('Pilar soporte interior',8,BOTTOM+1,-19.3,xy)
        union(back,tower)
        bore(back,2.4,-25,-19.2,xy);nut_slot(back,xy,-23.2,-21.3)
    boolean(back,limit,'INTERSECT')
    for xy in SCREWS:
        bore(back,2.4,BOTTOM-2,.1,xy);bore(back,4.4,BOTTOM-2,-4,xy)
    for xy in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):bore(back,4.4,-2.5,.2,xy)
    for yy in (-7,-3,1,5,9):boolean(back,cylinder('Salida sonido',1.8,-34,-20,(yy,-7),axis='X'))
    return back

def main(no_render=False):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.001
    ivory=mat('Marfil',(0.88,0.82,0.73),.4);pink=mat('Rosa suave',(.76,.34,.39),.4)
    dark=mat('Pantalla y componentes',(.009,.016,.022),.28);green=mat('PCB',(.02,.16,.09),.6);steel=mat('Metal',(.27,.29,.30),.35,.6)
    base=original_front()
    # Close the original 35-degree hole before drilling the two measured axes.
    normal=(math.cos(math.radians(35)),math.sin(math.radians(35)),0)
    plug=rcyl('Relleno paso antiguo',5.8,27,31,(0,0,5),normal)
    boolean(plug,cylinder('Limite original',60,-1,16),'INTERSECT');union(base,plug)
    cat=dup(base,'01 Frontal gato');mochi=dup(base,'02 Frontal mochi');bpy.data.objects.remove(base,do_unlink=True)
    fronts=[cat,mochi]
    for f,is_cat in zip(fronts,[True,False]):
        deform_front(f,is_cat)
        bore(f,49.66,10,17)
        correct_oem_holes(f)
        for yy in (10.958917046,-11.738123269):boolean(f,cylinder('Respiracion micro',1.8,-34,-18,(yy,3.8),axis='X'))
    buttons=[make_button(fronts,f,i+1)for i,f in enumerate(BUTTONS)]
    back=make_rear()

    carrier=rect('04 Bandeja bateria GPS',28.5,44,3,-19.3,-17.7,(1,-2))
    union(carrier,rect('Techo GPS',32,32,4,-19.3,-17.7,(1,1)))
    rail=rect('Guia bateria',28.5,44,3,-17.9,-14.5,(1,-2))
    boolean(rail,rect('Reserva bateria',26.5,42,2,-20,-13,(1,-2)));union(carrier,rail)
    boolean(carrier,cube('Salida cable bateria',(8,5,6),(1,19.5,-16)))
    for xx in (-12.25,14.25):boolean(carrier,rect('Paso cinta bateria',2,7,.5,-21,-13,(xx,-19.5)))
    gpswall=rect('Alojamiento antena completa',31,31,2,-26.9,-19.1,(1,1))
    boolean(gpswall,rect('Reserva antena completa',28,28,.6,-28,-18,(1,1)))
    for x,y,wx,hy in [(1,-13.75,6,5),(1,15.75,6,5),(-13.75,1,5,6),(15.75,1,5,6)]:boolean(gpswall,cube('Paso coaxial',(wx,hy,4.3),(x,y,-21.25)))
    for x in (-13.75,15.75):
        for y in (-13.75,15.75):boolean(gpswall,cube('Alivio conector coaxial esquina',(6,6,4.3),(x,y,-21.25)))
    union(carrier,gpswall)
    speaker_tray=rect('05 Soporte altavoz',36.5,26.5,3,-10,-8.8,(1,1))
    spwall=rect('Borde altavoz',36.5,26.5,3,-9,-6.8,(1,1))
    boolean(spwall,rect('Reserva altavoz',32.5,22.5,.3,-11,-6,(1,1)));union(speaker_tray,spwall)
    for obj,z0,z1 in [(carrier,-19.3,-17.7),(speaker_tray,-10,-8.8)]:
        for x,y in STACK:
            union(obj,cylinder('Oreja montaje interior',8,z0,z1,(x,y)))
            bridge=cube('Puente montaje interior',(9,6,z1-z0),(x+(3 if x<0 else -3),y,(z0+z1)/2));union(obj,bridge)
            bore(obj,2.4,z0-1,z1+1,(x,y))
        for xy in SCREWS:bore(obj,8,BOTTOM-2,2,xy)
        limit=c.ellipse_prism('Holgura pared',55.2,55.2,BOTTOM-2,2);boolean(obj,limit,'INTERSECT')
    for xy in STACK:bore(speaker_tray,5.4,-8.8,-6,xy)
    spacers=[]
    for i,xy in enumerate(STACK):
        o=cylinder('06 Separador interior '+str(i),6,-17.7,-10,xy);bore(o,2.6,-19,-9,xy);spacers.append(o)
    gauge=cylinder('09 Prueba pantalla',56,0,3);bore(gauge,49.66,-1,4)
    guide=cylinder('10 Prueba pulsadores',8,0,7);bore(guide,3.2,-1,8)
    nut=cube('11 Prueba tuerca M2',(12,10,6),(0,0,3),.4)
    bore(nut,2.4,-1,9);nut_slot(nut,(0,0),2.1,4)
    specifications=[(cat,'01_frontal_gato.stl',ivory),(mochi,'02_frontal_mochi.stl',ivory),(back,'03_cuerpo_sin_carga_magnetica.stl',ivory),(carrier,'04_bandeja_bateria_y_GPS.stl',ivory),(speaker_tray,'05_soporte_altavoz.stl',ivory),(spacers[0],'06_separador_interno_7_7mm.stl',pink),(gauge,'09_prueba_pantalla.stl',ivory),(guide,'10_prueba_pulsadores.stl',pink),(nut,'11_prueba_tuerca_M2.stl',ivory)]
    for o,name,material in specifications:export(o,name,material)
    for i,b in enumerate(buttons):export(b,'07_pulsador_inferior.stl'if i==0 else'08_pulsador_superior.stl',pink,(b['axis_origin'],b['axis_direction']))
    finish(spacers[1],pink)
    for o in (gauge,guide,nut):o.hide_render=True;o.hide_set(True)
    mochi.hide_render=True;mochi.hide_set(True)

    bat=rect('ENV Reserva EEMB500 R2',26.5,42,2,-17.7,-10.3,(1,-2));gpspcb=cube('ENV Antena completa',(27,27,6.7),(1,1,-23.05));gpsceramic=cube('ENV Ceramica antena',(25,25,5.7),(1,1,-23.55))
    sp=rect('ENV Altavoz referencia',32.5,22.5,.3,-8.8,-5,(1,1))
    adapter=cube('ENV Adaptador PH2 MX1.25',(8,8,6),(-18,-3,-14.4))
    refs=step_refs();assert len(refs)==666
    for r in refs:r.data.materials.append(dark if r['cad_tag']==665 else green)
    internal=[back,carrier,speaker_tray,*spacers,*buttons]
    for a,b in itertools.combinations(internal,2):collision(a,b)
    for f in fronts:
        for o in internal:collision(f,o)
    for proxy in (bat,gpspcb,gpsceramic,sp,adapter):
        for o in [*fronts,*internal]:collision(o,proxy,'component clearance')
    for a,b in [(bat,gpspcb),(bat,gpsceramic),(bat,sp),(bat,adapter),(gpspcb,adapter),(gpsceramic,adapter)]:collision(a,b,'component separation')
    for part in [*fronts,*internal]:
        for r in refs:
            aa,bb=bbox(part),bbox(r)
            if np.all(aa[1]>bb[0]+1e-5)and np.all(bb[1]>aa[0]+1e-5):collision(part,r,'official Waveshare STEP')
    for b in buttons:
        p=Vector(b['axis_origin']);n=Vector(b['axis_direction'])
        tangent=Vector((-n.y,n.x,0))
        for travel in (0,.225,.45):
            for sideways,vertical in ((0,0),(-.25,0),(.25,0),(0,-.25),(0,.25)):
                tmp=dup(b,'TEMP button travel');tmp.location-=n*travel;tmp.location+=tangent*sideways+Vector((0,0,vertical))
                for o in [*fronts,back,carrier,speaker_tray,*spacers]:collision(tmp,o,'button travel and lateral play')
                for r in refs:
                    aa,bb=bbox(tmp),bbox(r)
                    if not(np.all(aa[1]>bb[0])and np.all(bb[1]>aa[0])):continue
                    if travel>0 and r['cad_tag']in(278,279):
                        fixed=dup(r,'TEMP fixed switch');boolean(fixed,rbox('Mobile cap allowance',2.2,1.4,-.28,.05,p,n),solver='EXACT');collision(tmp,fixed,'pressed plunger vs fixed switch');bpy.data.objects.remove(fixed,do_unlink=True)
                    else:collision(tmp,r,'button vs official STEP')
                bpy.data.objects.remove(tmp,do_unlink=True)
    if REPORT.get('failed_checks'):
        (ROOT/'auditoria/interferencias_pendientes.json').write_text(json.dumps(REPORT['failed_checks'],indent=2),encoding='utf-8');raise RuntimeError('Unresolved V6 collisions')
    REPORT['pass']=True;REPORT['source_3mf_sha256']=json.loads((ROOT/'auditoria/original.json').read_text(encoding='utf-8'))['source_sha256'];REPORT['official_step_solids']=len(refs)
    REPORT['module_scope']=P['source_scope'];REPORT['glass_front_z']=GLASS_Z;REPORT['screen_seat']={'diameter':49.66,'relief_start_z':10,'radial_clearance':.35,'oem_mounts':[[0,20.5],[-13.75,-14.7],[13.75,-14.7]]}
    REPORT['button_sweep']={'travel_mm':[0,.225,.45],'lateral_mm':.25,'lateral_samples':['center','left','right','back','front'],'hard_inward_stop':False}
    REPORT['rear_dome']={'outer_profile_z_r_mm':dome_profile(),'inner_profile_z_r_mm':dome_profile(True),'normal_offset_mm':P['body']['wall'],'flat_landing_diameter_mm':P['body']['dome']['landing_diameter'],'external_supports_required':True,'reference_inspiration':P['body']['dome']['reference']}
    REPORT['internal_nuts']={'centers':STACK,'pocket_z':[-23.2,-21.3],'continuous_shoulder_z':[-21.3,-19.3],'shoulder_above_nut':True,'thickness_mm':2}
    REPORT['source_files_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ('generar.py','cad_base.py','parametros.json')}
    REPORT['stl_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))}
    for name,f in [('cat',cat),('mochi',mochi)]:
        bounds=[bbox(f),bbox(back),*[bbox(o)for o in buttons]]
        REPORT['assembly_'+name+'_dimensions_mm']=(np.max([x[1]for x in bounds],axis=0)-np.min([x[0]for x in bounds],axis=0)).tolist()
    (ROOT/'validacion_mecanica.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    for o in (bat,gpspcb,gpsceramic,sp,adapter):bpy.data.objects.remove(o,do_unlink=True)
    # Nominal component references for a readable editable assembly.
    battery=finish(cube('REF EEMB 562438',(24.5,40,5.9),(1,-2,-14.75),.4),steel)
    antenna=finish(cube('REF GNSS assembly',(27,27,6.7),(1,1,-23.05),.2),ivory)
    speaker=finish(cube('REF Altavoz segun alojamiento',(32,22,3.5),(1,1,-7.05),.7),dark)
    scene.render.engine='CYCLES';scene.cycles.samples=40;scene.cycles.use_denoising=True;scene.render.resolution_x=1500;scene.render.resolution_y=1500;scene.render.resolution_percentage=100;scene.world.color=(.25,.23,.23);scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
    for loc,power,size in [((-70,70,140),650000,110),((100,30,120),420000,100),((0,-80,-100),400000,100)]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;aim(o,(0,3,-6))
    bpy.ops.object.camera_add(location=(75,45,150));cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=100;aim(cam,(0,4,-6));scene.camera=cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                view=area.spaces.active.region_3d;view.view_location=(0,4,-6);view.view_distance=115;view.view_rotation=cam.rotation_euler.to_quaternion()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'tamapoke_v6_montaje.blend'))
    if no_render:return
    for r in refs:r.hide_render=True
    face=finish(cylinder('REF Cara ilustrativa',48.96,12.7,12.9),dark)
    for x in (-7,7):
        eye=c.ellipse_prism('REF Ojo',4.2,7,12.92,12.98);eye.location.x=x;eye.location.y=2;finish(eye,ivory)
    for x in (-13,13):
        cheek=c.ellipse_prism('REF Colorete',4.3,2.0,12.92,12.98);cheek.location.x=x;cheek.location.y=-4;finish(cheek,pink)
    pts=[]
    for j in range(25):a=math.pi+math.pi*j/24;pts.append((3*math.cos(a),-3+1.9*math.sin(a)))
    for j in range(24,-1,-1):a=math.pi+math.pi*j/24;pts.append((2.3*math.cos(a),-3+1.2*math.sin(a)))
    finish(c.prism('REF Sonrisa',pts,12.92,12.98),ivory)
    render('01_gato.png',(75,45,150),(0,4,-6),103)
    render('02_gato_frontal.png',(0,4,160),(0,4,-6),88)
    cat.hide_render=True;mochi.hide_render=False
    render('03_mochi.png',(75,45,150),(0,0,-6),99)
    mochi.hide_render=True;cat.hide_render=False
    render('04_trasera_sin_imanes.png',(75,35,-160),(0,0,-10),102)
    render('07_perfil_redondo.png',(150,0,30),(0,2,-10),100)
    cat.hide_render=True;face.hide_render=True
    for o in bpy.data.objects:
        if o.name.startswith(('REF Ojo','REF Colorete','REF Sonrisa')):o.hide_render=True
    for r in refs:r.hide_render=False
    back.hide_render=True
    render('05_distribucion_interior.png',(85,-50,-140),(0,0,-6),104)
    print('V6 COMPLETE',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]if'--'in sys.argv else[]);main(args.no_render)
