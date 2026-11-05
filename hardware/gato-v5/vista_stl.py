"""Preview the actual exported front STL as one unadorned printed part."""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import generar as g
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.wm.stl_import(filepath=str(ROOT/'stl'/'01_frontal_gato.stl'))
front=bpy.context.object
front.name='Frontal real STL con ambas orejas integradas'
g.finish(front,g.mat('PLA marfil',(0.86,0.81,0.73),0.4))
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.samples=32
scene.cycles.use_denoising=True
scene.render.resolution_x=1500
scene.render.resolution_y=1500
scene.render.resolution_percentage=100
scene.world.color=(0.2,0.2,0.2)
scene.view_settings.view_transform='AgX'
for loc,power,size in [((-90,90,160),900000,140),((90,25,130),450000,110)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    lamp=bpy.context.object
    lamp.data.energy=power
    lamp.data.shape='DISK'
    lamp.data.size=size
    g.aim(lamp,(0,15,15))
scene.render.image_settings.file_format='PNG'
g.render('06_frontal_stl_una_pieza.png',(0,14,250),(0,14,13.5),178)
print('Preview generated directly from the exported STL.')
