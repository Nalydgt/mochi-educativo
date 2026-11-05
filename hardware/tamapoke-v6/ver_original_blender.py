from pathlib import Path
import sys
import numpy as np
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'gato-v5'))
import cad_base as c
c.ROOT=ROOT
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
data=np.load(ROOT/'referencias/mallas_originales.npz')
ivory=c.mat('Original',(0.72,0.81,0.84),0.5)
objects=[]
for i in range(1,7):
    mesh=bpy.data.meshes.new('Original '+str(i));mesh.from_pydata(data['vertices_'+str(i)].tolist(),[],data['faces_'+str(i)].tolist());mesh.update()
    o=bpy.data.objects.new('HOUSING_'+str(i),mesh);bpy.context.collection.objects.link(o);o.data.materials.append(ivory);objects.append(o)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1300;scene.render.resolution_y=1300;scene.render.resolution_percentage=100
scene.world.color=(0.25,0.25,0.25);scene.view_settings.view_transform='AgX'
for loc,power,size in [((0,0,150),450000,120),((0,0,-150),450000,120),((100,-40,80),250000,100)]:
    bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;c.aim(o,(0,0,7))
scene.render.image_settings.file_format='PNG'
for i in (1,3,4):
    for o in objects:o.hide_render=o.name!='HOUSING_'+str(i)
    c.render('original_'+str(i)+'_frente.png',(85,55,150),(0,0,7),82)
    c.render('original_'+str(i)+'_interior.png',(45,45,-160),(0,0,7),82)
print('Original source views ready')
