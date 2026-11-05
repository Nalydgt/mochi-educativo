"""Reviewable joint and standing-base prototype; original screw access retained."""
from pathlib import Path
import sys,math,json
import bpy,bmesh
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'echoear-v8'))
import generar as g
import cad_base as c
c.ROOT=ROOT
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'base_v8.blend'))
front=bpy.data.objects['01 Frontal EchoEar adaptado'];back=bpy.data.objects['02 Trasera EchoEar adaptada']
ivory=front.data.materials[0]
# Female recess is open at the rim; .30 mm radial clearance to the male ring.
male=c.cylinder('Labio macho continuo',67.2,-2.0,.7)
c.boolean(male,c.cylinder('Interior labio',65.2,-3,2))
c.union(front,male)
female=c.cylinder('Alojamiento hembra',67.8,-2.3,.1)
c.boolean(female,c.cylinder('Proteccion interior',64.5,-3,2))
c.boolean(back,female)
# Ground normal in model coordinates: face plane is 65 degrees to horizontal.
# Crop only the lower rear spherical skin, retaining the rounded silhouette.
n=Vector((0,math.sin(math.radians(65)),math.cos(math.radians(65))))
cut=c.cube('Semiespacio base',(150,150,100),(0,0,0))
cut.rotation_euler=Vector((0,0,1)).rotation_difference(n).to_euler()
cut.location=n*(-31.5-50)
c.boolean(back,cut)
# Close the unnecessary rear openings of the ears with a solid inner layer.
source=g.source_front()
for side in (-1,1):
    pts=[tuple(v.co)for v in source.data.vertices if v.co.x*side>19 and v.co.y>20]
    bm=bmesh.new()
    for p in pts:bm.verts.new(p)
    bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
    loose=[v for v in bm.verts if not v.link_faces]
    if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
    me=bpy.data.meshes.new('Cubierta cerrada oreja');bm.to_mesh(me);bm.free()
    cover=bpy.data.objects.new('Cubierta oreja',me);bpy.context.collection.objects.link(cover)
    c.recalc(cover);c.union(front,cover)
bpy.data.objects.remove(source,do_unlink=True)
for o in (front,back):c.finish(o,ivory)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Peluqo_V9_union_base_BORRADOR.blend'))
report={'status':'draft','joint':{'radial_clearance_mm':.3,'axial_clearance_mm':.3,'overlap_mm':2},'standing_face_angle_degrees':65,'ear_covers_added':True,'not_verified':['external screw access redesign','electronic clearance at base','stability and center of gravity','printable mesh validation'],'note':'Original external screw holes remain accessible. Not a fabrication release.'}
(ROOT/'estado.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
c.render('union_base_borrador.png',(120,25,110),(0,0,-8),115)
