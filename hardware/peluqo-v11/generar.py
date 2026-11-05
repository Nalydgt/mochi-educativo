"""Peluqo: serviceable front display cassette, overlapping joint and 65deg base.

The registered V8 components retain their functional coordinates. Mechanical
checks concern assembly geometry; no physical manufacturing test is implied.
"""
from pathlib import Path
import sys,json,math,itertools,hashlib,subprocess,shutil,os
import bpy,bmesh,numpy as np
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import base_geom as g
import cad_base as c
from cad_base import cylinder,cube,boolean,union,dup,finish,mat,render
P=c.P;REPORT=c.REPORT;J=P['joint'];B=P['base'];D=P['screen_cassette']
N=Vector(B['normal_model']);LEVEL=B['plane_offset'];THICK=B['floor_thickness']
SIDE=g.SCREWS[:2];TOP=g.SCREWS[2]
MOUNTS=[(D['mount_radius']*math.cos(math.radians(a)),D['mount_radius']*math.sin(math.radians(a)))for a in D['mount_angles']]

def bore(o,d,z0,z1,xy=(0,0)):boolean(o,cylinder('Paso '+str(d),d,z0,z1,xy))
def cone(name,d0,d1,z0,z1,xy=(0,0)):
    bpy.ops.mesh.primitive_cone_add(vertices=128,radius1=d0/2,radius2=d1/2,depth=z1-z0,location=(xy[0],xy[1],(z0+z1)/2))
    o=bpy.context.object;o.name=name;return o
def radial_box(name,r0,r1,width,z0,z1,angle):
    a=math.radians(angle);r=(r0+r1)/2
    o=cube(name,(r1-r0,width,z1-z0),(r*math.cos(a),r*math.sin(a),(z0+z1)/2));o.rotation_euler.z=a;return o
def axis_angle(xy):return math.degrees(math.atan2(xy[1],xy[0]))
def halfspace(name,start,end):
    o=cube(name,(160,160,end-start),(0,0,0));o.rotation_euler=Vector((0,0,1)).rotation_difference(N).to_euler();o.location=N*((start+end)/2);return o
def outside(name):
    o=g.ball(name,g.R);boolean(o,g.slab('Limite exterior original',g.BOTTOM,0),'INTERSECT');return o
def hex_nut(name,xy,z0,z1,af=4):
    o=cylinder(name,af/math.cos(math.pi/6),z0,z1,xy,vertices=6);o.rotation_euler.z=math.atan2(xy[1],xy[0])-math.pi/6
    bore(o,2,z0-.1,z1+.1,xy);return o
def nut_slot(o,xy):
    x,y=xy;a=math.atan2(y,x)
    h=cylinder('Cajera tuerca M2',4.2/math.cos(math.pi/6),-11,-9.1,xy,vertices=6);h.rotation_euler.z=a-math.pi/6;boolean(o,h)
    slot=cube('Entrada interior tuerca',(6.5,4.3,1.9),(x-2.85*math.cos(a),y-2.85*math.sin(a),-10.05));slot.rotation_euler.z=a;boolean(o,slot)

def cover_ears(front):
    # Remove all old protrusions, including the stretched microphone pockets.
    # The spherical shell and all internal mounting features remain intact.
    boolean(front,g.ball('Contorno limpio de cabeza',g.R+.01),'INTERSECT')
    features=[]
    for side in (-1,1):
        pts=[(side*x,y)for x,y in P['ears']['right_points_xy']]
        if side<0:pts.reverse()
        o=c.prism('Oreja lisa redondeada',pts,*P['ears']['z'])
        bevel=o.modifiers.new('Redondeo continuo oreja','BEVEL');bevel.width=P['ears']['edge_rounding_mm'];bevel.segments=10
        c.apply(o,bevel);c.recalc(o)
        features.append(dup(o,'ENV cubierta oreja'));union(front,o)
    return features

def modify_head(front):
    covers=cover_ears(front)
    # Remove the trapped fixed cage. The complete screen cassette can now enter
    # from the front; neither the glass nor its connectors must cross a small lip.
    bore(front,D['case_aperture'],-.02,15)
    bore(front,D['flange_recess_diameter'],D['flange_bottom'],15)
    male=cylinder('Encaje macho circular',67.2,-2.1,1.6)
    union(male,cone('Entrada biselada macho',66.6,67.2,-2.4,-2.1))
    bore(male,64.8,-3,2);union(front,male)
    # Two hidden mounting tabs rest on the blind rear posts at Z=-7.
    for xy in SIDE:
        a=axis_angle(xy);r=math.hypot(*xy)
        union(front,cylinder('Apoyo lateral oculto',6.4,-7,-5,xy))
        union(front,radial_box('Brazo lateral interior',r,32.2,6,-7,-5,a))
        union(front,radial_box('Nervio vertical lateral',30.8,32.4,6,-7,.7,a))
        union(front,radial_box('Raiz en solape',31.0,33.5,6,-1,.7,a))
        bore(front,2.4,-7.1,-4.9,xy)
    # The third original rear screw remains functional. A narrower post and a
    # matching cassette slot retain its original axis without trapping the PCB.
    union(front,cylinder('Pilar cierre superior',4.0,0,5.8,TOP))
    union(front,radial_box('Brazo cierre superior',22.5,33.7,3.8,0,2.5,axis_angle(TOP)))
    bore(front,1.8,.6,6.1,TOP);bore(front,2.4,-.1,.6,TOP)
    for xy,a in zip(MOUNTS,D['mount_angles']):
        union(front,cylinder('Receptor casete',5.8,-7.5,-1,xy))
        union(front,radial_box('Brazo receptor casete',D['mount_radius'],33.5,5.8,-2.6,-1,a))
        bore(front,1.7,-7.1,-.9,xy)
        boolean(front,radial_box('Paso columna casete',26.1,30.1,4.6,-.99,15,a))
    # A concealed indexing key prevents a rotated assembly. Its notch has
    # .30 mm lateral/radial and .35 mm axial clearance.
    boolean(front,radial_box('Muesca de orientacion',31.7,33.8,2.6,-2.45,-.2,180))
    # Keep the original USB cable envelope clear of the raised overlap root.
    g.port(front,13.0,8.6,21.8,45,4.83,1.7);g.port(front,16.4,10.4,26.5,45,5.7,2.2)
    return covers

def modify_body(back):
    for xy in SIDE:
        plug=cylinder('Cierre permanente salida lateral',4.6,g.BOTTOM-1,.1,xy)
        boolean(plug,outside('Piel original para cierre'),'INTERSECT');union(back,plug)
        bore(back,7.4,-7,.1,xy)
        post=cylinder('Poste lateral ciego conservado',7,g.BOTTOM,-7,xy)
        boolean(post,outside('Limite poste ciego'),'INTERSECT');union(back,post)
        bore(back,2.4,-13.8,-6.9,xy);nut_slot(back,xy)
    # Integrated closed sole, not an open cut through the hollow hemisphere.
    boolean(back,halfspace('Recorte de apoyo a65',-100,LEVEL))
    floor=outside('Suelo integrado 2.4mm')
    boolean(floor,halfspace('Espesor suelo',LEVEL,LEVEL+THICK),'INTERSECT');union(back,floor)
    female=cylinder('Rebaje hembra circular',67.8,-2.75,.1)
    bore(female,64.0,-3,.2);boolean(back,female)
    union(back,radial_box('Raiz guia de orientacion',31.5,34.4,4,-4.2,-2.8,180))
    union(back,radial_box('Llave de orientacion',32.0,33.5,2,-2.9,-.55,180))

def make_cassette():
    o=cylinder('03 Casete pantalla desmontable',D['tube_outer_diameter'],0,10.8)
    bore(o,D['pcb_throat_diameter'],-.1,11)
    for x,y in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):
        union(o,cylinder('Apoyo OEM original',5.8,0,2.5,(x,y)))
        a=math.atan2(y,x);r=math.hypot(x,y);end=25.8
        bridge=cube('Puente OEM',((end-r)+1,5,2.5),((r+end)/2*math.cos(a),(r+end)/2*math.sin(a),1.25));bridge.rotation_euler.z=a;union(o,bridge)
    union(o,cylinder('Brida casete',D['flange_diameter'],10.5,12.95))
    bore(o,D['glass_seat_diameter'],9.8,14)
    # Continuous assembly channels, rather than pockets valid only at the
    # final screen position. Preserve the intact front flange above Z=10.5.
    boolean(o,cube('Paso USB durante insercion',(12,12.6,10.0),(-25,0,4.8)))
    for b in BUTTONS:
        a=axis_angle(b['axis_direction'][:2])
        boolean(o,radial_box('Paso collar durante insercion',21.8,28.0,6.4,-.1,9.8,a))
    bore(o,4.6,-.1,6.2,TOP)
    boolean(o,radial_box('Paso brazo superior durante insercion',22,27.2,4.6,-.1,3.0,axis_angle(TOP)))
    for xy in MOUNTS:
        union(o,cylinder('Columna montaje casete',4,-1,10.8,xy))
        bore(o,2.4,-1.1,13.1,xy)
        boolean(o,cone('Asiento avellanado compartido',2.4,4.4,12.72,13.72,xy))
    # Reopen OEM holes after the tube unions, maintaining all original centers.
    for xy in ((0,20.5),(-13.75,-14.7),(13.75,-14.7)):bore(o,2.4,-.1,2.6,xy)
    return o

def make_bezel():
    o=cylinder('04 Marco frontal desmontable',61,12.95,13.7)
    bore(o,45.5,12.8,14)
    for xy in MOUNTS:
        bore(o,2.4,12.8,14,xy)
        boolean(o,cone('Avellanado marco',2.4,4.4,12.72,13.72,xy))
    return o

def add_bolt(name,xy,z0,z1,h0,h1):
    o=cylinder(name,2,z0,z1,xy)
    union(o,cylinder('Cabeza M2D3.8',3.8,h0,h1,xy));return o

def normalize_mesh(o):
    # A one-micron surface tolerance removes collapsed CSG wedges without
    # voxel remeshing or changing the functional clearances.
    me=o.data;me.calc_loop_triangles()
    v=np.asarray([tuple(p.co)for p in me.vertices],dtype=np.float64)
    f=np.asarray([tuple(t.vertices)for t in me.loop_triangles],dtype=np.uint64)
    source=ROOT/'auditoria/mesh_input.npz';target=ROOT/'auditoria/mesh_clean.npz'
    np.savez_compressed(source,vertices=v,faces=f)
    python=os.environ.get('PELUQO_PYTHON')or shutil.which('python')
    if not python:raise RuntimeError('Set PELUQO_PYTHON to Python with numpy and manifold3d')
    result=subprocess.run([python,str(ROOT/'limpiar_malla.py'),str(source),str(target)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
    if result.returncode:raise RuntimeError('Mesh normalization failed: '+result.stderr)
    cleaned=np.load(target)
    out=bpy.data.meshes.new(o.name+' clean')
    out.from_pydata(cleaned['vertices'].tolist(),[],cleaned['faces'].tolist());out.update()
    o.data=out

def static_checks(front,back,cassette,bezel,guts,buttons,covers):
    plastics=[front,back,cassette,bezel,*guts,*buttons]
    for a,b in itertools.combinations([front,back,cassette,bezel],2):g.clearance(a,b,'assembled case interfaces')
    for shell in (front,back,cassette,bezel):
        for o in [*guts,*buttons]:g.clearance(shell,o,'retained internal parts')
    bat=g.rect('ENV battery reserve',26.5,42,2,-17.7,-10.3,(1,-2))
    gps=cube('ENV GNSS27',(27,27,6.7),(1,1,-23.05))
    sp=g.rect('ENV speaker',32.5,22.5,.3,-8.8,-5,(1,1))
    adapter=cube('ENV adapter',(8,8,6),(-18,-3,-14.4))
    for shell in (front,back,cassette,bezel):
        for env in (bat,gps,sp,adapter):g.clearance(shell,env,'component reserve')
    for env in (bat,gps,sp,adapter):bpy.data.objects.remove(env,do_unlink=True)
    # Verify a route into the cassette, not just a static glass seat.
    screen=[cylinder('ENV glass48.96',48.96,11.8,12.9),cylinder('ENV lower display46.4',46.4,7.1,11.8),cylinder('ENV PCB46.1',46.1,6.0,7.2),cube('ENV USB complete',(8.1,10,4.6),(-19.94,-.02,4.83))]
    for env in screen:
        for travel in (0,3,8,16):
            tmp=dup(env,'ENV screen insertion');tmp.location.z+=travel
            g.clearance(tmp,cassette,'screen enters cassette from front, dz='+str(travel))
            bpy.data.objects.remove(tmp,do_unlink=True)
        for shell in (front,back,bezel):g.clearance(env,shell,'screen final position')
        bpy.data.objects.remove(env,do_unlink=True)
    for travel in (0,3,8,16):
        tmp=dup(cassette,'ENV cassette insertion');tmp.location.z+=travel
        for shell in (front,back):g.clearance(tmp,shell,'cassette enters assembled case, dz='+str(travel))
        bpy.data.objects.remove(tmp,do_unlink=True)
    for travel in (1,3):
        tmp=dup(front,'ENV joint insertion');tmp.location.z+=travel;g.clearance(tmp,back,'male joint insertion, dz='+str(travel));bpy.data.objects.remove(tmp,do_unlink=True)
    # A short inward sample of each existing plunger, retaining its axis.
    for b in buttons:
        tmp=dup(b,'ENV pressed button');tmp.location-=Vector(b['axis_direction'])*.45
        for shell in (front,back,cassette):g.clearance(tmp,shell,'single button pressed position')
        bpy.data.objects.remove(tmp,do_unlink=True)
    upper=buttons[1];p=Vector(upper['axis_origin']);n=Vector(upper['axis_direction'])
    tip=max((upper.matrix_world@v.co-p).dot(n)for v in upper.data.vertices)
    access=g.rcyl('ENV fingertip D10',10,tip-.2,tip+6,p,n)
    for cover in covers:
        boolean(cover,g.ball('Exclude spherical skin',g.R+.02))
        g.clearance(access,cover,'ear cover leaves upper button access')
        bpy.data.objects.remove(cover,do_unlink=True)
    bpy.data.objects.remove(access,do_unlink=True)
    # Six OEM/case mounting screws, plus the new cassette fasteners. Threads
    # deliberately engaged in printed pilots are excluded from free envelopes.
    fasteners=[]
    for xy in SIDE:fasteners.append(add_bolt('ENV hidden M2x8',xy,-13,-5,-5,-3))
    fasteners.append(add_bolt('ENV retained rear M2x8',TOP,-4,.55,-6,-4))
    oem=((0,20.5),(-13.75,-14.7),(13.75,-14.7))
    for xy in oem:
        fasteners.append(add_bolt('ENV OEM M2x5',xy,0,2.45,-2,0))
        swept=cylinder('ENV OEM head insertion',3.8,-2,18,xy)
        for shell in (front,back):g.clearance(swept,shell,'OEM heads pass through case during insertion')
        bpy.data.objects.remove(swept,do_unlink=True)
    for xy in MOUNTS:
        bolt=cylinder('ENV cassette M2x20 free shaft',2,-.95,12.52,xy)
        union(bolt,cone('ENV countersunk head',2,4,12.52,13.52,xy));fasteners.append(bolt)
    for bolt in fasteners:
        for part in plastics:g.clearance(bolt,part,'free mounting screw envelope')
        bpy.data.objects.remove(bolt,do_unlink=True)
    for xy in SIDE:
        nut=hex_nut('ENV captured nut',xy,-10.701,-9.101)
        g.clearance(nut,back,'captured internal nut')
        inward=Vector((xy[0],xy[1],0)).normalized()
        tmp=dup(nut,'ENV nut loading');tmp.location-=inward*4;tmp.location.z-=.05;g.clearance(tmp,back,'nut access from case interior');bpy.data.objects.remove(tmp,do_unlink=True)
        bpy.data.objects.remove(nut,do_unlink=True)

def center_of_volume(o):
    me=o.data;me.calc_loop_triangles();v=np.asarray([list(o.matrix_world@p.co)for p in me.vertices]);f=np.asarray([t.vertices[:]for t in me.loop_triangles]);q=v[f]
    vol=np.einsum('ij,ij->i',q[:,0],np.cross(q[:,1],q[:,2]))/6
    total=vol.sum();return abs(total),(vol[:,None]*(q[:,0]+q[:,1]+q[:,2])/4).sum(0)/total

def aim_world(o,target):
    forward=(Vector(target)-o.location).normalized()
    right=forward.cross(Vector((0,0,1))).normalized();up=right.cross(forward).normalized()
    o.rotation_euler=Matrix((right,up,-forward)).transposed().to_quaternion().to_euler()

def stability(back,parts):
    n=np.asarray(N);u=np.array([1.,0,0]);t=np.array([0,-n[2],n[1]])
    pts=np.asarray([list(back.matrix_world@v.co)for v in back.data.vertices]);foot=pts[abs(pts@n-LEVEL)<.0001]
    xy=np.c_[foot@u,foot@t]
    points=sorted(set(map(tuple,np.round(xy,6))))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    polygon=np.asarray(lower[:-1]+upper[:-1]);edges=np.roll(polygon,-1,axis=0)-polygon
    area=abs(np.sum(polygon[:,0]*np.roll(polygon[:,1],-1)-polygon[:,1]*np.roll(polygon[:,0],-1)))/2
    vc=[center_of_volume(o)for o in parts]
    cases=[]
    for density,screen_m,antenna_m,speaker_m in itertools.product((1.0,1.3),(15,35),(10,22),(2,8)):
        masses=[vol*density/1000 for vol,com in vc];moment=sum((m*com for m,(vol,com)in zip(masses,vc)),np.zeros(3));mass=sum(masses)
        for m,pos in [(15,(1,-2,-14.75)),(screen_m,(0,0,7)),(antenna_m,(1,1,-23.05)),(speaker_m,(1,1,-7.05)),(3,(0,0,-5))]:moment+=m*np.asarray(pos);mass+=m
        com=moment/mass;project=np.array([com@u,com@t]);offset=project-polygon
        margin=float(np.min((edges[:,0]*offset[:,1]-edges[:,1]*offset[:,0])/np.linalg.norm(edges,axis=1)))
        cases.append({'plastic_density_g_cm3':density,'screen_mass_g':screen_m,'antenna_mass_g':antenna_m,'speaker_mass_g':speaker_m,'margin_mm':margin})
    minimum=min(x['margin_mm']for x in cases)
    if minimum<3:raise RuntimeError('Insufficient estimated stability margin')
    return {'face_to_horizontal_degrees':65,'ground_plane_model':[*N,LEVEL],'floor_thickness_mm':THICK,'support_polygon_area_mm2':float(area),'minimum_estimated_margin_mm':minimum,'assumption':'Uniform plastic density1.0..1.3; screen15..35g, antenna10..22g, speaker2..8g, battery15g, hardware3g. No physical tip/impact test.','mass_cases':cases}

def main():
    global BUTTONS
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'referencias/base_v8.blend'))
    front=bpy.data.objects['01 Frontal EchoEar adaptado'];back=bpy.data.objects['02 Trasera EchoEar adaptada']
    carrier=bpy.data.objects['03 Bandeja bateria GPS'];speaker=bpy.data.objects['04 Soporte altavoz']
    spacers=[bpy.data.objects['05 Separador 7.7mm'],bpy.data.objects['05 Separador segundo']]
    buttons=[bpy.data.objects['Pulsador 1'],bpy.data.objects['Pulsador 2']]
    BUTTONS=[{'axis_direction':b['axis_direction']}for b in buttons]
    for o in list(bpy.data.objects):
        if o.name.startswith('08 Prueba'):bpy.data.objects.remove(o,do_unlink=True)
    ivory=front.data.materials[0];pink=buttons[0].data.materials[0]
    covers=modify_head(front);modify_body(back);cassette=make_cassette();bezel=make_bezel()
    front.name='01 Cabeza Peluqo';back.name='02 Cuerpo Peluqo'
    parts=[front,back,cassette,bezel,carrier,speaker,*spacers,*buttons]
    for o in parts:normalize_mesh(o);finish(o,pink if o in buttons or o in spacers else ivory)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'auditoria/pre_checks.blend'))
    static_checks(front,back,cassette,bezel,[carrier,speaker,*spacers],buttons,covers)
    if REPORT.get('failed_checks'):
        (ROOT/'auditoria/interferencias.json').write_text(json.dumps(REPORT['failed_checks'],indent=2),encoding='utf-8');raise RuntimeError('Unresolved assembly interference')
    st=stability(back,parts)
    for ob,name,flip in [(front,'01_cabeza_Peluqo.stl',True),(back,'02_cuerpo_Peluqo.stl',True),(cassette,'03_casete_pantalla.stl',True),(bezel,'04_marco_pantalla.stl',True),(carrier,'05_bandeja_bateria_GPS.stl',False),(speaker,'06_soporte_altavoz.stl',False),(spacers[0],'07_separador_7_7mm.stl',False)]:g.export(ob,name,ivory,flip=flip)
    for ob,name in zip(buttons,('08_boton_inferior.stl','09_boton_superior.stl')):g.export(ob,name,pink,axis=(ob['axis_origin'],ob['axis_direction']))
    gauge=cylinder('10 Prueba entrada pantalla',56,0,3);bore(gauge,50.2,-1,4);g.export(gauge,'10_prueba_pantalla_50_2.stl',ivory);gauge.hide_render=True;gauge.hide_set(True)
    # Ray intervals confirm that both formerly open wells now have a closed
    # exterior and substantial solid material below their new blind bores.
    closed=[]
    for xy in SIDE:
        origin=Vector((xy[0],xy[1],-60));inverse=back.matrix_world.inverted()
        hit,p,no,idx=back.ray_cast(inverse@origin,(inverse.to_3x3()@Vector((0,0,1))).normalized())
        if not hit:raise RuntimeError('Missing external skin')
        p=back.matrix_world@p;thickness=-13.8-p.z
        if thickness<2:raise RuntimeError('Blind post floor too thin')
        closed.append({'xy':xy,'outer_skin_z':p.z,'blind_bore_bottom_z':-13.8,'solid_axial_length_mm':thickness,'nut_shoulder_mm':2.1})
    bounds=[g.bounds(o)for o in parts]
    REPORT.update({'pass':True,'validation_mode':'assembly','joint':J,'screen_cassette':D,'closed_side_wells':closed,'stability':st,'screen_insertion_offsets_checked_mm':[0,3,8,16],'joint_insertion_offsets_checked_mm':[0,1,3],
      'assembly_dimensions_model_mm':(np.max([b[1]for b in bounds],axis=0)-np.min([b[0]for b in bounds],axis=0)).tolist(),
      'stl_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'stl').glob('*.stl'))},
      'source_files_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in ('generar.py','base_geom.py','cad_base.py','parametros.json','limpiar_malla.py')},
      'limitations':['Waveshare envelope derived from registered1.75 CAD; not a measurement of the user specimen or all1.75-G additions.','No physical fit, torque, drop or tilt test.','Original upper rear closing screw remains accessible; the two lateral exits are permanently sealed.']})
    (ROOT/'validacion.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    metal=mat('Referencia tornillos',(.36,.37,.38),.3,.65)
    for xy in MOUNTS:finish(cone('REF Cabeza M2 avellanada',2,4,12.52,13.52,xy),metal)
    finish(cylinder('REF Cabeza cierre posterior',3.8,-6,-4,TOP),metal)
    # Save a standing assembly: the real integrated sole lies on world Z=0.
    meshes=[o for o in bpy.data.objects if o.type=='MESH'and not o.name.startswith('10 Prueba')]
    root=bpy.data.objects.new('Peluqo montaje a65grados',None);bpy.context.collection.objects.link(root)
    for o in meshes:o.parent=root
    root.rotation_euler=(math.radians(65),0,0);root.location.z=-LEVEL
    for o in list(bpy.data.objects):
        if o.type in ('LIGHT','CAMERA'):bpy.data.objects.remove(o,do_unlink=True)
    c.aim=aim_world
    sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=24;sc.cycles.use_denoising=True;sc.render.resolution_x=1300;sc.render.resolution_y=1300
    for loc,power,size in [((-90,-90,140),800000,110),((100,-20,130),500000,100),((0,90,90),500000,90)]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=size;c.aim(o,(0,0,32))
    bpy.ops.object.camera_add(location=(100,-160,105));cam=bpy.context.object;cam.name='Camara';cam.data.type='ORTHO';cam.data.ortho_scale=112;c.aim(cam,(0,0,34));sc.camera=cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion();area.spaces.active.region_3d.view_distance=130;area.spaces.active.region_3d.view_location=(0,0,32)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Peluqo_V11_montaje.blend'))
    for x in (-7,7):
        eye=c.ellipse_prism('REF Ojos ilustrativos',5.4,7.2,12.91,12.96);eye.location.x=x;eye.location.y=1.5;finish(eye,ivory);eye.parent=root
    for x in (-12,12):
        cheek=c.ellipse_prism('REF Colorete ilustrativo',5,2,12.91,12.96);cheek.location.x=x;cheek.location.y=-4;finish(cheek,pink);cheek.parent=root
    floor=cube('Suelo visual',(250,250,.2),(0,0,-.15));finish(floor,mat('Suelo',(.2,.22,.24),.7))
    render('01_Peluqo_montado.png',(100,-160,105),(0,0,34),112)
    render('02_perfil_base65.png',(150,-35,65),(0,0,33),110)
    render('03_cuerpo_laterales_cerrados.png',(85,140,105),(0,0,33),112)
    # Exploded display service view while keeping the established axes visible.
    cassette.location.z+=18;bezel.location.z+=34
    for o in bpy.data.objects:
        if o.name.startswith(('REF Pantalla','REF Ojos','REF Colorete')):o.location.z+=18
    render('04_pantalla_desmontable.png',(90,-170,135),(0,-8,43),140)
    print('PELUQO_V11_COMPLETE',flush=True)

if __name__=='__main__':main()
