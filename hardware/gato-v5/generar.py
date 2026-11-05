"""Mochi cat V5: continuous rounded head + measured STEP interfaces."""
from pathlib import Path
import sys,json,math,argparse,hashlib
import numpy as np
import bpy,bmesh
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cad_base as c
from cad_base import cube,cylinder,prism,boolean,union,dup,finish,mat,aim,render
ROOT=c.ROOT
for directory in ('stl','vistas','auditoria'):(ROOT/directory).mkdir(parents=True,exist_ok=True)
P=c.P
B,D,BAT=P['body'],P['display'],P['battery']
W,H,DEPTH,WALL=B['width'],B['height'],B['depth'],B['wall']
SPLIT,GAP=B['split'],B['seam_gap']
GLASS_Z=DEPTH-D['front_lip']
INSERT_Z=GLASS_Z-D['insert_depth_from_glass']
BRACKET_Z=INSERT_Z-2
OFFSET=GLASS_Z-2.76999804
SCREWS=P['case_screws']['centers']
POSTS=P['carrier']['mount_centers']
CENTER_Y=B['center_y']
BOTTOM=-B['rear_extension']
import modulos_v5 as v5
PARTS=c.PARTS
REPORT=c.REPORT
M=json.loads((ROOT/'auditoria/step_measurements_independent.json').read_text(encoding='utf-8'))
FEATURES=M['features']
BUTTONS=[f for f in FEATURES if 'actuator_face_center_native_mm' in f]
MIC_CAPS=M.get('microphone_cap_geometry',[])


def continuous_head():
    a,b=W/2,H/2
    r=B['radius']
    levels=[]
    for i in range(21):
        t=math.pi/2*i/20
        levels.append((BOTTOM+r-r*math.cos(t),r*math.sin(t)-r))
    for z in (SPLIT-0.4,SPLIT,SPLIT+1,SPLIT+2,SPLIT+4,SPLIT+7,DEPTH-r):
        if z>levels[-1][0]+1e-5:levels.append((z,0))
    for i in range(1,21):
        t=math.pi/2*i/20
        levels.append((DEPTH-r+r*math.sin(t),r*math.cos(t)-r))
    n=256
    verts=[]
    for z,off in levels:
        t=max(0,min(1,(z-SPLIT)/7))
        weight=t*t*(3-2*t)
        for j in range(n):
            theta=2*math.pi*j/n
            rad=1/math.sqrt((math.cos(theta)/(a+off))**2+(math.sin(theta)/(b+off))**2)
            ear=0
            for center in P['ears']['angle_degrees']:
                angle=math.atan2(math.sin(theta-math.radians(center)),math.cos(theta-math.radians(center)))
                ear+=P['ears']['radial_height_mm']*math.exp(-0.5*(angle/math.radians(P['ears']['width_degrees']))**2)
            rad+=weight*ear
            verts.append((rad*math.cos(theta),CENTER_Y+rad*math.sin(theta),z))
    faces=[tuple(reversed(range(n)))]
    for k in range(len(levels)-1):
        faces += [(k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j) for j in range(n)]
    faces.append(tuple((len(levels)-1)*n+j for j in range(n)))
    mesh=bpy.data.meshes.new('Cabeza continua analitica')
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    o=bpy.data.objects.new('Cabeza continua',mesh)
    bpy.context.collection.objects.link(o)
    bm=bmesh.new();bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    bm.to_mesh(mesh);bm.free()
    return o


def radial_transform(o,p,n):
    n=Vector(n).normalized()
    t=Vector((-n.y,n.x,0))
    z=Vector((0,0,1))
    rotation=Matrix((t,z,n)).transposed().to_4x4()
    rotation.translation=Vector(p)
    o.matrix_world=rotation @ o.matrix_world
    c.activate(o)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o


def radial_box(name,width,height,s0,s1,p,n,radius=0):
    return radial_transform(cube(name,(width,height,s1-s0),(0,0,(s0+s1)/2),radius),p,n)


def radial_cyl(name,diam,s0,s1,p,n):
    return radial_transform(cylinder(name,diam,s0,s1),p,n)


def side_nut_trap(obj,xy,af,z0,z1,bore,axis_angle=None):
    x,y=xy
    angle=math.atan2(y,x) if axis_angle is None else axis_angle
    pocket=cylinder('Tuerca hexagonal con hombro',af/math.cos(math.pi/6),z0,z1,(x,y),vertices=6)
    pocket.rotation_euler.z=angle
    boolean(obj,pocket)
    outward=Vector((math.cos(angle),math.sin(angle),0))
    length=8.5 if af>5 else 6.5
    slot=cube('Entrada lateral tuerca',(length,af,z1-z0),(x-outward.x*(length/2-0.4),y-outward.y*(length/2-0.4),(z0+z1)/2))
    slot.rotation_euler.z=angle
    boolean(obj,slot)


def bearing_rib(o,xy,z0,z1,outer):
    v=Vector((xy[0],xy[1],0)).normalized()
    angle=math.atan2(v.y,v.x)
    rib=cube('Nervio radial M3',(24,2.8,z1-z0),(0,0,(z0+z1)/2),0.8)
    rib.rotation_euler.z=angle
    rib.location.x=xy[0]+v.x*8
    rib.location.y=xy[1]+v.y*8
    c.activate(rib);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    boolean(rib,outer,'INTERSECT',discard=False)
    union(o,rib)


def bbox(o):
    pts=[o.matrix_world@Vector(v) for v in o.bound_box]
    return np.array([[min(v[i] for v in pts) for i in range(3)],[max(v[i] for v in pts) for i in range(3)]])


def overlaps(a,b,eps=1e-5):
    return bool(np.all(a[1]>b[0]+eps) and np.all(b[1]>a[0]+eps))


def collision(a,b,allowed=0.02,label=None):
    if not overlaps(bbox(a),bbox(b)):
        vol=0.0
    else:
        tmp=dup(a,'TEMP interseccion')
        boolean(tmp,b,'INTERSECT',discard=False)
        bm=bmesh.new();bm.from_mesh(tmp.data)
        vol=abs(bm.calc_volume()) if bm.faces else 0
        bm.free()
        if vol>allowed:print("COLLISION_BOUNDS",c.mesh_stats(tmp),flush=True)
        bpy.data.objects.remove(tmp,do_unlink=True)
    REPORT.setdefault('mechanical_checks',[]).append({'a':a.name,'b':b.name,'kind':label or 'clearance','intersection_mm3':round(vol,6),'allowed_mm3':allowed})
    if vol>allowed:
        REPORT.setdefault('failed_checks',[]).append({'a':a.name,'b':b.name,'volume_mm3':vol,'allowed_mm3':allowed})
    return vol


def export_part(o,filename,material,print_button=False):
    finish(o,material)
    if filename in ('12_adaptador_objetivo_20mm.stl','13_adaptador_objetivo_ciego.stl'):
        tmp=dup(o,o.name+' PRINT')
        tmp.matrix_world=Matrix.Rotation(math.pi,4,'X') @ tmp.matrix_world
        c.export(tmp,filename);PARTS.remove(tmp)
        bpy.data.objects.remove(tmp,do_unlink=True);PARTS.append(o)
        return o
    if not print_button:
        c.export(o,filename)
    else:
        # Axial outer head face on the bed, with the contact nose pointing up.
        tmp=dup(o,o.name+' PRINT')
        p=Vector(o['axis_origin']);n=Vector(o['axis_direction'])
        t=Vector((-n.y,n.x,0));z=Vector((0,0,1))
        basis=Matrix((t,z,n)).transposed().to_4x4();basis.translation=p
        tmp.matrix_world=Matrix.Rotation(math.pi,4,'X') @ basis.inverted()
        c.export(tmp,filename)
        PARTS.remove(tmp)
        bpy.data.objects.remove(tmp,do_unlink=True)
        PARTS.append(o)
    return o


def load_step_refs():
    if not (ROOT/"referencias/step_mesh_native.npz").exists():
        raise RuntimeError("Official STEP mesh is required for verification")
    data=np.load(ROOT/'referencias/step_mesh_native.npz')
    source=data['vertices']
    verts=np.column_stack((source[:,0],-source[:,2],source[:,1]+OFFSET))
    rows=json.loads((ROOT/'auditoria/step_parts.json').read_text(encoding='utf-8'))
    refs=[]
    for row in rows:
        faces=data['faces_'+str(row['tag'])]
        if not len(faces):continue
        unique,inverse=np.unique(faces.reshape(-1),return_inverse=True)
        co=verts[unique]
        mesh=bpy.data.meshes.new('CAD '+str(row['tag']))
        mesh.from_pydata(co.tolist(),[],inverse.reshape(-1,3).tolist());mesh.update()
        obj=bpy.data.objects.new('CAD '+str(row['tag'])+' '+row['name'].split('/')[-1],mesh)
        bpy.context.collection.objects.link(obj)
        obj['source']='Official Waveshare STEP; native X,-Z,Y+offset'
        obj['cad_tag']=row['tag']
        obj['cad_name']=row['name']
        refs.append(obj)
    return refs


def button_assembly(front,feature,index,pink):
    cap=Vector(feature['actuator_face_center_case_relative_mm']);cap.z+=OFFSET
    n=Vector(feature['outward_normal_case']);n.z=0;n.normalize()
    bp=P['buttons']
    # Determine the real exterior along this exact switch axis on the analytic shell.
    hit,location,normal,face=front.ray_cast(cap+n*80,-n)
    if not hit:raise RuntimeError('No exterior found on button axis')
    mouth=(location-cap).dot(n)
    tangent=Vector((-n.y,n.x,0))
    surface_stations=[]
    for u in np.linspace(-5,5,11):
        for v in np.linspace(-5,5,11):
            if u*u+v*v>25:continue
            hit,at,_,_=front.ray_cast(cap+n*80+tangent*float(u)+Vector((0,0,float(v))),-n)
            if hit:surface_stations.append((at-cap).dot(n))
    guide_end=max(surface_stations)+0.6
    start=bp['guide_start']
    guide=radial_cyl('Guia exterior redonda boton '+str(index),8.6,start,guide_end,cap,n)
    edge=guide.modifiers.new('Bordes suaves guia','BEVEL');edge.width=0.4;edge.segments=5;c.apply(guide,edge)
    union(front,guide)
    bore=radial_box('Paso antigiro boton',bp['bore_width'],bp['bore_width'],start-1.0,guide_end+4,cap,n,0.35)
    boolean(front,bore)
    # Head underside meets this flat annular end after exactly travel_stop.
    head_start=guide_end+bp['travel_stop']
    nose=radial_cyl('Punta contacto boton',bp['contact_nose_diameter'],bp['rest_gap'],1.5,cap,n)
    stem=radial_box('Vastago antigiro boton '+str(index),bp['stem_width'],bp['stem_width'],1.2,head_start+0.5,cap,n,0.30)
    union(stem,nose)
    head=cylinder('Cabeza boton',bp['head_diameter'],head_start,head_start+2.5)
    bevel=head.modifiers.new('Borde suave','BEVEL');bevel.width=0.6;bevel.segments=6;c.apply(head,bevel)
    radial_transform(head,cap,n);union(stem,head)
    # Tangential M2x4 retention screw; flat-keyed stem fixes its orientation.
    hole=cylinder('Taladro retencion M2',1.7,-4,4,(0,bp['retaining_screw_center']),axis='X',vertices=48)
    radial_transform(hole,cap,n);boolean(stem,hole)
    stem['axis_origin']=list(cap);stem['axis_direction']=list(n)
    stem['mouth_station']=mouth;stem['guide_end_station']=guide_end
    shaft=cylinder('REF Tornillo M2x4 boton',2.0,-1.8,2.2,(0,bp['retaining_screw_center']),axis='X',vertices=48)
    head_ref=cylinder('Cabeza M2 D3.8',3.8,-3.8,-1.8,(0,bp['retaining_screw_center']),axis='X',vertices=48)
    union(shaft,head_ref);radial_transform(shaft,cap,n)
    shaft['reference_hardware']=True
    REPORT.setdefault('buttons',[]).append({'id':index,'cap_center':list(cap),'outward_axis':list(n),'mouth_station':mouth,'guide_end_station':guide_end,'tip_gap_mm':bp['rest_gap'],'hard_stop_mm':bp['travel_stop'],'nominal_depression_mm':bp['travel_stop']-bp['rest_gap'],'stroke_certified':False,'source':'official STEP static geometry; TS24CA manufacturer reference 0.20 +/-0.05 mm, physical fit still required'})
    return stem,shaft


def bent_pipe(name,p,diameter,end_x,top):
    radius=2.0;zturn=40.3
    rings=[(Vector((p.x,p.y,top)),Vector((0,0,-1)))]
    for i in range(13):
        angle=math.pi/2*i/12
        pos=Vector((p.x-radius+radius*math.cos(angle),p.y,zturn-radius*math.sin(angle)))
        tangent=Vector((-math.sin(angle),0,-math.cos(angle)))
        rings.append((pos,tangent))
    rings.append((Vector((end_x,p.y,zturn-radius)),Vector((-1,0,0))))
    count=64;vertices=[]
    for pos,tangent in rings:
        u=Vector((0,1,0));v=tangent.cross(u)
        for j in range(count):
            angle=math.tau*j/count
            vertices.append(tuple(pos+(u*math.cos(angle)+v*math.sin(angle))*(diameter/2)))
    faces=[tuple(reversed(range(count)))]
    for k in range(len(rings)-1):
        for j in range(count):
            nxt=(j+1)%count
            faces.append((k*count+j,k*count+nxt,(k+1)*count+nxt,(k+1)*count+j))
    faces.append(tuple((len(rings)-1)*count+j for j in range(count)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(mesh);bm.free()
    return obj


def microphone_duct(front,cap,index):
    p=Vector(cap['rear_cap_center_case_relative_mm']);p.z+=OFFSET
    corners=[Vector(v) for v in cap['rear_cap_corners_case_relative_mm']]
    edge=max([(corners[(i+1)%4]-corners[i]) for i in range(4)],key=lambda e:e.length)
    rotation=math.atan2(edge.y,edge.x)
    outer=cube('Camara micro '+str(index),(5.6,4.8,1.8),(p.x,p.y,p.z-1.3),0.25)
    outer.rotation_euler.z=rotation
    hit,loc,_,_=front.ray_cast(Vector((-80,p.y,38.3)),Vector((1,0,0)))
    if not hit:raise RuntimeError('No wall for microphone duct')
    union(outer,bent_pipe('Conducto curvo micro',p,3.4,loc.x+0.3,p.z-1.6))
    union(front,outer)
    receiver=cube('Camara receptora micro',(4.0,3.2,2.2),(p.x,p.y,p.z-0.6),0.15)
    receiver.rotation_euler.z=rotation
    boolean(front,receiver)
    boolean(front,bent_pipe('Paso acustico curvo',p,1.8,-W/2-2,p.z-1.2))
    return p


def main(no_render=False):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=0.001
    ivory=mat('PLA marfil',(0.88,0.82,0.72),0.36)
    pink=mat('Rosa suave',(0.75,0.32,0.33),0.4)
    green=mat('PCB oficial',(0.025,0.12,0.09),0.65)
    dark=mat('Pantalla',(0.008,0.016,0.024),0.22)
    steel=mat('Tornilleria',(0.28,0.29,0.3),0.25,0.8)
    outer=continuous_head()
    front=dup(outer,'01 Frontal continuo con orejas')
    inner=c.pillow('Interior',W-2*WALL,H-2*WALL,DEPTH-BOTTOM-2*WALL,B['radius']-WALL,bottom=BOTTOM+WALL)
    inner.location.y=CENTER_Y
    boolean(front,inner)
    back=dup(front,'02 Tapa trasera')
    boolean(front,cube('Separar frontal',(230,230,SPLIT-BOTTOM+20),(0,0,(SPLIT+BOTTOM-20)/2)))
    boolean(back,cube('Separar tapa',(230,230,160),(0,0,SPLIT-GAP+80)))
    boolean(front,cylinder('Ventana AMOLED',45.0,25,DEPTH+2))
    boolean(front,cylinder('Asiento cristal D49.66',49.66,25,GLASS_Z))
    # Both structural halves bear on the same Z=27 datum, preserving the cosmetic seam.
    for x,y in SCREWS:
        union(front,cylinder('Torre frontal M3',10,SPLIT,DEPTH-9,(x,y)))
        union(back,cylinder('Torre trasera con tope',10,BOTTOM+9,SPLIT,(x,y)))
        bearing_rib(front,(x,y),SPLIT,SPLIT+8,outer)
        bearing_rib(back,(x,y),SPLIT-8,SPLIT-GAP,outer)
        boolean(front,cylinder('Paso M3 ciego',3.4,SPLIT-0.1,SPLIT+12.5,(x,y)))
        side_nut_trap(front,(x,y),5.8,SPLIT+2.0,SPLIT+4.8,3.4)
        boolean(back,cylinder('Paso M3 tapa',3.4,BOTTOM-2,SPLIT+0.1,(x,y)))
        boolean(back,cylinder('Alojamiento cabeza M3',6.8,BOTTOM-2,BOTTOM+9.4,(x,y)))
    flange=c.ellipse_ring('Base encaje',W-3.6,H-3.6,SPLIT-2.2,SPLIT-GAP,2.35)
    lip=c.ellipse_ring('Labio alineacion',W-5.5,H-5.5,SPLIT-0.9,SPLIT+2.5,1.4)
    flange.location.y=lip.location.y=CENTER_Y
    for x,y in SCREWS:
        boolean(lip,cylinder('Despeje de torre',10.9,SPLIT-4,SPLIT+4,(x,y)))
        normal=Vector((x,y,0)).normalized()
        relief=cube('Despeje nervio frontal',(26,3.4,5),(x+normal.x*8,y+normal.y*8,SPLIT+1.5),0.3)
        relief.rotation_euler.z=math.atan2(normal.y,normal.x)
        boolean(lip,relief)
    union(back,flange);union(back,lip)
    bracket=cylinder('03 Soporte placa',53.4,BRACKET_Z,INSERT_Z)
    boolean(bracket,cylinder('Acceso electronica',43.6,BRACKET_Z-1,INSERT_Z+1))
    for x,y in D['mounts_rear_view']:
        union(bracket,cylinder('Oreja OEM M2',7,BRACKET_Z,INSERT_Z,(x,y)))
        boolean(bracket,cylinder('Paso OEM M2',2.4,BRACKET_Z-1,INSERT_Z+1,(x,y)))
    for x,y in POSTS:
        union(bracket,cylinder('Oreja soporte M2',7.2,BRACKET_Z,INSERT_Z,(x,y)))
        normal=Vector((x,y,0)).normalized()
        bridge=cube('Nervio del soporte',(12,4,2),(normal.x*29,normal.y*29,BRACKET_Z+1),0.4)
        bridge.rotation_euler.z=math.atan2(normal.y,normal.x)
        union(bracket,bridge)
        boolean(bracket,cylinder('Paso M2 soporte',2.4,BRACKET_Z-1,INSERT_Z+1,(x,y)))
        union(front,cylinder('Torre tuerca M2',7,INSERT_Z,DEPTH-2,(x,y)))
        boolean(front,cylinder('Paso M2 ciego',2.4,INSERT_Z-0.1,DEPTH-5.2,(x,y)))
        side_nut_trap(front,(x,y),4.2,INSERT_Z+2.0,INSERT_Z+3.9,2.4)
    bw,bh=67.0,57.0;by,bz=BAT['center_y'],BAT['floor_z']
    tray=c.rounded_prism('Bandeja bateria',71,61,4,bz-2,bz);tray.location.y=by
    rails=c.ring('Borde bateria',71,61,2.7,bz-0.3,bz+3.4,2);rails.location.y=by;union(tray,rails)
    for sign in (-1,1):boolean(tray,cube('Paso cinta bateria',(9,3.4,12),(0,by+sign*(bh/2+0.4),bz+2)))
    boolean(tray,cube('Paso cable bateria',(10,12,10),(bw/2,by+15,bz+5),1))
    for sign in (-1,1):
        for yy in (-22,22):
            beam=cube('Puente lateral bateria',(30,6,3),(sign*46,yy,8.5),0.6)
            boolean(beam,outer,'INTERSECT',discard=False)
            union(back,beam)
    # The battery tray is exported separately so the boost can be serviced.
    for sy in (-1,1):union(back,cube('Guia altavoz',(10,2,16.5),(-44,sy*15,15.75),0.6))
    speaker_base=cube('Apoyo altavoz unido a pared',(18,34,2),(-51,0,7),0.6)
    boolean(speaker_base,outer,'INTERSECT',discard=False)
    union(back,speaker_base)
    for yy in (-7.2,-3.6,0,3.6,7.2):boolean(back,cube('Rejilla altavoz',(36,1.7,8),(-W/2,yy,17.4),0.6))
    ax,ay,az=P['gps_antenna']['center']
    for sx in (-1,1):union(back,cube('Guia GNSS',(2,9,10.8),(ax+sx*13.5,ay,18.5),0.6))
    union(back,cube('Apoyo GNSS',(29,9,2),(ax,ay,12.5),0.6))
    # Correct sides and exact depth planes, with a generous cable-housing well.
    boolean(front,cube('Pozo USB-C',(48,14.4,8.8),(-44,0.02,OFFSET-5.3),1.0))
    boolean(front,cube('Acceso microSD',(48,19.0,4.6),(44,0.25,OFFSET-2.305),0.65))
    buttons=[];retaining=[]
    for i,feature in enumerate(BUTTONS,1):
        button,screw=button_assembly(front,feature,i,pink);buttons.append(button);retaining.append(screw)
    # Circular receiving chambers cover the cap: the vendor STEP has no real mic hole.
    micpoints=[]
    for i,cap in enumerate(MIC_CAPS,1):micpoints.append(microphone_duct(front,cap,i))
    # Keep positive FDM clearance around the three actual OEM brass standoffs.
    for x,y in D['mounts_rear_view']:
        boolean(front,cylinder('Despeje inserto OEM',4.2,INSERT_Z-0.5,INSERT_Z+4.2,(x,y)))
    # Rear connectors protrude below the PCB: relieve only the inner carrier edge.
    cad_rows=json.loads((ROOT/'auditoria/step_parts.json').read_text(encoding='utf-8'))
    for component in cad_rows:
        if '/H2_ASM/' not in component['name'] and '/H3_ASM/' not in component['name'] and component['tag']!=653:continue
        lo,hi=np.asarray(component['mesh_bbox_native'])
        lower=np.array([lo[0],-hi[2],lo[1]+OFFSET])-0.30
        upper=np.array([hi[0],-lo[2],hi[1]+OFFSET])+0.30
        if lower[2]<INSERT_Z and upper[2]>BRACKET_Z:
            boolean(bracket,cube('Despeje conector medido',tuple(upper-lower),tuple((upper+lower)/2)))
    # Extra clearance for the retaining head at the maximum keyed-stem roll.
    for button in buttons:
        origin=Vector(button['axis_origin']);normal=Vector(button['axis_direction'])
        relief=cube('Holgura cabeza de retencion',(12,0.8,4.0),(0,-2.7,2.9))
        radial_transform(relief,origin,normal);boolean(bracket,relief)
    # Trim only the small interior-edge portions occupied by the vertical ducts.
    for p in micpoints:boolean(bracket,cylinder('Holgura micro en soporte',3.8,BRACKET_Z-1,INSERT_Z+1,(p.x,p.y)))
    added=v5.build(sys.modules[__name__],front,back,outer,tray,ivory,pink,steel)
    coupon=cylinder('06 Prueba pantalla',58,0,4)
    boolean(coupon,cylinder('Ventana prueba',45,-1,6))
    boolean(coupon,cylinder('Asiento prueba',49.66,-1,2.7))
    # A short keyed guide coupon avoids spending a full shell to tune FDM clearance.
    fit=cube('09 Prueba ajuste pulsador',(12,12,8),(0,0,4),1)
    boolean(fit,cube('Guia de prueba',(4.2,4.2,12),(0,0,4),0.35))
    nuts=cube('10 Prueba tuercas',(12,10,8),(-8,0,4),0.4)
    union(nuts,cube('Prueba M2',(10,10,8),(8,0,4),0.4))
    union(nuts,cube('Puente de probeta',(7,4,1),(0,0,0.5)))
    for xy,af,diam,height in [((-8,0),5.8,3.4,2.8),((8,0),4.2,2.4,1.9)]:
        boolean(nuts,cylinder('Paso tornillo probeta',diam,-1,9,xy))
        side_nut_trap(nuts,xy,af,2,2+height,diam,axis_angle=0)
    for o,name in [(front,'01_frontal_gato.stl'),(back,'02_tapa_trasera.stl'),(bracket,'03_soporte_waveshare.stl'),(coupon,'06_prueba_pantalla.stl'),(fit,'09_prueba_guia_botones.stl'),(nuts,'10_prueba_tuercas.stl')]:export_part(o,name,ivory)
    for obj,filename,material in added['parts']:export_part(obj,filename,material)
    for i,button in enumerate(buttons,1):export_part(button,'0'+str(i+6)+'_pulsador_'+('inferior' if i==1 else 'superior')+'.stl',pink,True)
    coupon.hide_render=fit.hide_render=nuts.hide_render=True;coupon.hide_set(True);fit.hide_set(True);nuts.hide_set(True)
    # Electronics proxies retain the documented allowances for unmeasured accessories.
    battery=finish(cube('REF Bateria 955565',(65,55,9.5),(0,by,bz+4.75),0.7),steel)
    envelope=cube('Holgura bateria',(67,57,11.5),(0,by,bz+5.75),0.7)
    antenna=finish(cube('REF Antena provisional',(25,4,25),(ax,ay,az),0.3),ivory)
    sp=P['speaker'];sx,sy,sz=sp['center']
    speaker=finish(cylinder('REF Altavoz provisional',sp['diameter'],sx-sp['depth']/2,sx+sp['depth']/2,(sy,sz),axis='X'),dark)
    adapter=finish(cube('REF Adaptador PH2 MX1.25',(8,16,7),(42,0,25),1),pink)
    for a,b in [(front,back),(front,bracket),(back,bracket),(front,envelope),(back,envelope),(bracket,envelope),(front,speaker),(back,speaker),(front,antenna),(back,antenna),(bracket,antenna),(front,adapter),(back,adapter),(bracket,adapter),(envelope,speaker),(envelope,adapter)]:collision(a,b)
    v5.check(self=sys.modules[__name__],added=added,front=front,back=back,bracket=bracket,battery=envelope,antenna=antenna,speaker=speaker,adapter=adapter)
    swept=[]
    for button,screw in zip(buttons,retaining):
        origin=Vector(button['axis_origin']);normal=Vector(button['axis_direction'])
        for distance in (0.0,0.25,0.5):
            for roll in (-10,0,10):
                transform=Matrix.Translation(-normal*distance) @ Matrix.Translation(origin) @ Matrix.Rotation(math.radians(roll),4,normal) @ Matrix.Translation(-origin)
                for obj in (button,screw):
                    moved=dup(obj,'REF Barrido '+obj.name)
                    moved.matrix_world=transform @ moved.matrix_world
                    collision(front,moved,label='button complete sweep')
                    collision(back,moved,label='button complete sweep')
                    collision(bracket,moved,label='button complete sweep')
                    swept.append((moved,button,obj==button,distance,roll))
    refs=load_step_refs()
    if len(refs)!=666:raise RuntimeError('Incomplete official CAD assembly')
    cad_collisions=[]
    for r in refs:
        # Tessellated individual vendor solids preserve the assembly transforms.
        r.data.materials.append(dark if r.get('cad_tag')==665 else green)
        for part in (front,back,bracket,*buttons,*retaining,*added['assembly'],*added['hardware']):
            if overlaps(bbox(part),bbox(r)):
                collision(part,r,allowed=0.025,label='official STEP solid')
    for moved,button,is_plunger,distance,roll in swept:
        for ref in refs:
            if not overlaps(bbox(moved),bbox(ref)):continue
            if is_plunger and distance>0 and ref.get('cad_tag') in (278,279):
                fixed=dup(ref,'REF Switch fixed housing')
                cap_clearance=radial_box('Contact cap allowance',2.2,1.4,-0.28,0.05,button['axis_origin'],button['axis_direction'])
                boolean(fixed,cap_clearance,solver='EXACT')
                collision(moved,fixed,allowed=0.025,label='pressed plunger vs fixed switch housing')
                bpy.data.objects.remove(fixed,do_unlink=True)
            else:collision(moved,ref,allowed=0.025,label='button swept vs official STEP')
        bpy.data.objects.remove(moved,do_unlink=True)
    for s in retaining:finish(s,steel)
    if REPORT.get('failed_checks'):
        (ROOT/'auditoria/interferencias_pendientes.json').write_text(json.dumps(REPORT['failed_checks'],indent=2),encoding='utf-8')
        raise RuntimeError('V5 unresolved intersections; see auditoria/interferencias_pendientes.json')
    REPORT['pass']=True
    REPORT['source_files_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('generar.py','modulos_v5.py','cad_base.py','parametros.json')}
    REPORT['source_step_sha256']=M['source_sha256']
    REPORT['source_step_solids']=len(refs)
    REPORT['button_sweep']={'travel_samples_mm':[0,0.25,0.5],'roll_samples_degrees':[-10,0,10],'objects':['printed plunger','transverse M2 screw'],'switch_contact_allowance_mm':[2.2,1.4,0.28],'stroke_certified':False}
    REPORT['screen_fit']={'glass_diameter':48.96,'seat_diameter':49.66,'radial_clearance':0.35,'active_diameter':44.16,'window_diameter':45,'insert_depth_verified':10.39999608,'native_to_case':'X,-Z,Y+GLASS_Z-2.76999804'}
    REPORT['closure']={'stop_plane_front':SPLIT,'stop_plane_back':SPLIT,'outer_seam_gap':GAP,'screw':'M3x45','head_seat_z':BOTTOM+9.4,'tip_z':BOTTOM+9.4+45,'nut_range_z':[29.0,31.8],'nut_retaining_shoulder_mm':2.0,'nut_loading':'radial side slot, not mating face','gusset_thickness':2.8}
    REPORT['nut_load_paths']={'M3_retaining_shoulder_mm':2.0,'M3_pocket_z':[29,31.8],'M2_retaining_shoulder_mm':2.0,'M2_pocket_z':[INSERT_Z+2,INSERT_Z+3.9],'M2x6_tip_z':BRACKET_Z+6,'loading':'side slots; axial clamp force bears on front-shell shoulders'}
    REPORT['hardware_status']=P['status']
    case_bounds=[bbox(front),bbox(back)]+[bbox(o) for o in added['assembly']]
    REPORT['new_modules']=added['metadata']
    REPORT['camera_direction']=[0,0,1]
    REPORT['screen_direction']=[0,0,1]
    REPORT['assembly_bounds_mm']=(np.max([x[1] for x in case_bounds],axis=0)-np.min([x[0] for x in case_bounds],axis=0)).tolist()
    (ROOT/'validacion_mecanica.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False),encoding='utf-8')
    bpy.data.objects.remove(envelope,do_unlink=True);bpy.data.objects.remove(outer,do_unlink=True)
    for o in added['keepouts']:bpy.data.objects.remove(o,do_unlink=True)
    scene.render.engine='CYCLES';scene.cycles.samples=40;scene.cycles.use_denoising=True
    scene.render.resolution_x=1500;scene.render.resolution_y=1500;scene.render.resolution_percentage=100
    scene.world.color=(0.25,0.23,0.23);scene.view_settings.view_transform='AgX'
    for loc,power,size in [((-90,90,180),900000,140),((100,30,150),500000,110),((0,-80,-50),350000,90)]:
        bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object
        light.data.energy=power;light.data.shape='DISK';light.data.size=size;aim(light,(0,8,27))
    scene.render.image_settings.file_format='PNG'
    bpy.ops.object.camera_add(location=(95,60,230));cam=bpy.context.object;cam.name='Camara';cam.data.type='ORTHO';cam.data.ortho_scale=155;aim(cam,(0,8,27));scene.camera=cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_location=(0,8,27);area.spaces.active.region_3d.view_distance=180;area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'gato_v5_montaje.blend'))
    if no_render:return
    for r in refs:r.hide_render=True
    battery.hide_render=antenna.hide_render=speaker.hide_render=adapter.hide_render=True
    for r in retaining:r.hide_render=True
    # Illustrative expression is separate from the printable body and firmware.
    glass=finish(cylinder('REF Cara ilustrativa',48.96,GLASS_Z-0.2,GLASS_Z),dark)
    for x in (-8,8):
        eye=c.ellipse_prism('REF Ojo',5,8.5,GLASS_Z+0.02,GLASS_Z+0.08);eye.location.x=x;eye.location.y=2;finish(eye,ivory)
    for x in (-14,14):
        cheek=c.ellipse_prism('REF Colorete',4.8,2.4,GLASS_Z+0.02,GLASS_Z+0.08);cheek.location.x=x;cheek.location.y=-4.5;finish(cheek,pink)
    arc=[]
    for j in range(25):
        angle=math.pi+math.pi*j/24;arc.append((3.4*math.cos(angle),-3.5+2.2*math.sin(angle)))
    for j in range(24,-1,-1):
        angle=math.pi+math.pi*j/24;arc.append((2.6*math.cos(angle),-3.5+1.4*math.sin(angle)))
    smile=prism('REF Sonrisa',arc,GLASS_Z+0.02,GLASS_Z+0.08);finish(smile,ivory)
    render('01_gato_v5.png',(105,65,260),(0,14,24),184)
    render('02_frontal_v5.png',(0,14,250),(0,14,27),175)
    render('05_camara_frontal.png',(55,95,200),(0,42,48),97)
    render('06_interruptor_y_ventilacion.png',(90,45,-200),(10,0,-8),166)
    render('03_botones_guiados.png',(150,-35,145),(35,0,43),105)
    front.hide_render=True;glass.hide_render=True
    for o in added['hide_for_interior']:o.hide_render=True
    for obj in bpy.data.objects:
        if obj.name.startswith('REF Ojo') or obj.name.startswith('REF Colorete') or obj.name.startswith('REF Sonrisa'):obj.hide_render=True
    for r in refs:r.hide_render=False
    battery.hide_render=False;speaker.hide_render=False;antenna.hide_render=False
    render('04_montaje_interior.png',(100,90,220),(0,14,24),176)
    print('V5 COMPLETE',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    main(args.no_render)
