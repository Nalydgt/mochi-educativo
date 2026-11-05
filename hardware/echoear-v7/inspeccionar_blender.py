from pathlib import Path
import sys,json,math
import bpy,numpy as np
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'tamapoke-v6'))
import cad_base as c
c.ROOT=ROOT
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
d=np.load(ROOT/'referencias/source_meshes.npz')
offsets={'object_2':[22.9588074684,29.5555543257,32.0000009537],'object_3':[39.4999833107,29.4032077789,32.0000029057]}
a=math.radians(20);C=math.cos(a);S=math.sin(a)
T=np.array([[-S,-C,0],[0,0,1],[-C,S,0]])
save={}
for i,k in enumerate(offsets):
    v=(d[k+'_v']+np.array(offsets[k])-np.array([32,32,32]))@T.T
    f=d[k+'_f'];save[k+'_v']=v;save[k+'_f']=f
    mesh=bpy.data.meshes.new(k);mesh.from_pydata(v.tolist(),[],f.tolist());mesh.update()
    o=bpy.data.objects.new(k,mesh);bpy.context.collection.objects.link(o)
    m=c.mat('Front'if i==0 else'Back',(.56,.72,.8)if i==0 else(.84,.78,.68),.45)
    o.data.materials.append(m)
    for p in o.data.polygons:p.use_smooth=True
    print(k,v.min(0),v.max(0),flush=True)
np.savez_compressed(ROOT/'referencias/canonical_source.npz',**save)
sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
sc.render.engine='CYCLES';sc.cycles.samples=12;sc.render.resolution_x=1100;sc.render.resolution_y=1100;sc.world.color=(.3,.3,.3)
for loc,power in [((-80,90,120),750000),((100,40,100),550000),((20,-80,-100),500000)]:
    bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=100;c.aim(o,(0,0,0))
c.render('origen_frente.png',(70,35,140),(0,0,0),100)
c.render('origen_trasera.png',(75,35,-140),(0,0,-4),105)
c.render('origen_perfil.png',(140,0,0),(0,0,-4),105)
bpy.data.objects['object_2'].hide_render=True
c.render('origen_interior.png',(70,20,140),(0,0,-4),105)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'auditoria/source.blend'))
