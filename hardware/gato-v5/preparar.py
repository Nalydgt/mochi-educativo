"""Create V5 source from the preserved V4; no firmware changes."""
from pathlib import Path
import json, shutil

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'gato-v4'
for directory,names in {
    'referencias':['step_mesh_native.npz','plano-oficial.png','waveshare-ESP32-S3-Touch-AMOLED-1_75.stp','bateria-955565.jpg'],
    'auditoria':['step_parts.json','step_measurements_independent.json'],
}.items():
    (ROOT/directory).mkdir(parents=True,exist_ok=True)
    for name in names:shutil.copy2(OLD/directory/name,ROOT/directory/name)
for name in ['cad_base.py','validar_stl.py','vista_stl.py','teselar_step.py']:
    shutil.copy2(OLD/name,ROOT/name)

p=json.loads((OLD/'parametros.json').read_text(encoding='utf-8'))
p['revision']='gato-v5-camara-frontal'
p['body'].update(width=118.0,height=118.0,depth=60.0,center_y=10.0,rear_extension=18.0)
p['case_screws'].update(screw='M3 x 45 mm',head_seat_z=-8.6,screw_tip_z=36.4)
p['carrier']['mount_centers']=[[-24,23],[-25.5,-13.8],[16,-24.8]]
p['carrier']['bottom_z']=46.30000392;p['carrier']['top_z']=48.30000392
p['carrier']['nut_pocket_z']=[50.30000392,52.20000392]
p['gps_antenna']['center']=[0,61.5,26.5]
for key in ['usb_center','sd_center']:p['ports'][key][2]+=6
p['ports']['position_source']='Official STEP right-handed transform X,-Z,Y+55.93000196'
p['camera']={'model':'diymore ESP32-S3-CAM N16R8 OV2640 compact','direction':[0,0,1],'nominal_pcb_xy':[40,27],'mechanical_drawing_available':False,'center_xy':[0,44],'pcb_rear_z':47.4,'design_bay_xyz':[48,29,31],'design_bay_z':[27.4,58.4],'tray_slide_x_mm':[-3,3],'optic_adapter_aperture':20,'optic_adapter_outer_xy':[36,28],'sensor_alignment':'Adjustable tray and replaceable aperture; actual flex, optical axis and vignetting require physical fitting.'}
p['boost']={'model':'MT3608 module','nominal_reference_pcb_xy':[36,17],'design_bay_xyz':[38,20,17],'center_xy':[0,-5],'design_bay_z':[-9,8],'wire_reserve_length_x':48,'actual_module_dimensions_confirmed':False}
p['switch']={'model':'SS12D00','nominal_reference_body_xyz':[8.5,3.6,3.5],'pocket_xyz':[9.5,5,4.5],'center_xy':[32,-5],'actuator_direction':[0,0,-1],'slider_direction':[1,0,0],'actuator_slot_xy':[6.6,3],'actual_suffix_confirmed':False}
p['status']='V5 front camera, screen and buttons +Z. Waveshare static CAD verified; new module bays are explicitly provisional design allowances, not measured replicas. Fit camera flex/optical axis, module height, switch suffix, antenna and speaker physically before final use.'
(ROOT/'parametros.json').write_text(json.dumps(p,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
s=(OLD/'generar.py').read_text(encoding='utf-8')
def patch(old,new):
    global s
    assert old in s,old
    s=s.replace(old,new)
patch('Mochi cat V4:','Mochi cat V5:')
patch("POSTS=[(-5.0,29.0),(-25.5,-13.8),(16.0,-24.8)]","POSTS=P['carrier']['mount_centers']\nCENTER_Y=B['center_y']\nBOTTOM=-B['rear_extension']\nimport modulos_v5 as v5")
patch('levels.append((r-r*math.cos(t),r*math.sin(t)-r))','levels.append((BOTTOM+r-r*math.cos(t),r*math.sin(t)-r))')
patch('verts.append((rad*math.cos(theta),rad*math.sin(theta),z))','verts.append((rad*math.cos(theta),CENTER_Y+rad*math.sin(theta),z))')
patch("rib=cube('Nervio radial M3',(11,2.8,z1-z0)","rib=cube('Nervio radial M3',(24,2.8,z1-z0)")
patch('rib.location.x=xy[0]+v.x*3','rib.location.x=xy[0]+v.x*8')
patch('rib.location.y=xy[1]+v.y*3','rib.location.y=xy[1]+v.y*8')
patch("boolean(front,c.pillow('Interior',W-2*WALL,H-2*WALL,DEPTH-2*WALL,B['radius']-WALL,bottom=WALL))","inner=c.pillow('Interior',W-2*WALL,H-2*WALL,DEPTH-BOTTOM-2*WALL,B['radius']-WALL,bottom=BOTTOM+WALL)\n    inner.location.y=CENTER_Y\n    boolean(front,inner)")
patch("boolean(front,cube('Separar frontal',(230,230,SPLIT+20),(0,0,(SPLIT-20)/2)))","boolean(front,cube('Separar frontal',(230,230,SPLIT-BOTTOM+20),(0,0,(SPLIT+BOTTOM-20)/2)))")
patch("10,9,SPLIT,(x,y)","10,BOTTOM+9,SPLIT,(x,y)")
patch("3.4,-2,SPLIT+0.1,(x,y)","3.4,BOTTOM-2,SPLIT+0.1,(x,y)")
patch("6.8,-2,9.4,(x,y)","6.8,BOTTOM-2,BOTTOM+9.4,(x,y)")
patch("for x,y in SCREWS:\n        boolean(lip", "flange.location.y=lip.location.y=CENTER_Y\n    for x,y in SCREWS:\n        boolean(lip")
patch("(12,3.4,5),(x+normal.x*3,y+normal.y*3", "(26,3.4,5),(x+normal.x*8,y+normal.y*8")
patch("(8,4,2),(normal.x*27,normal.y*27", "(12,4,2),(normal.x*29,normal.y*29")
patch("for x in (-24,-10,10,24):union(back,cube('Nervio bandeja',(10,bh-8,bz-2),(x,by,(bz-2)/2+1.8)))", "for sign in (-1,1):\n        for yy in (-22,22):\n            beam=cube('Puente lateral bateria',(30,6,4),(sign*46,yy,9),0.6)\n            boolean(beam,outer,'INTERSECT',discard=False)\n            union(back,beam)")
patch("(10,2,13.5),(-44,sy*15,16.8)","(10,2,16.5),(-44,sy*15,15.75)")
patch("union(back,cube('Apoyo altavoz',(9,28,2),(-43.5,0,7),0.6))", "speaker_base=cube('Apoyo altavoz unido a pared',(18,34,2),(-51,0,7),0.6)\n    boolean(speaker_base,outer,'INTERSECT',discard=False)\n    union(back,speaker_base)")
patch("(ax+sx*13.5,37,18.5)","(ax+sx*13.5,ay,18.5)")
patch("(ax,37,12.5)","(ax,ay,12.5)")
patch("coupon=cylinder('06 Prueba pantalla'", "added=v5.build(sys.modules[__name__],front,back,outer,ivory,pink,steel)\n    coupon=cylinder('06 Prueba pantalla'")
patch("for i,button in enumerate(buttons,1):export_part", "for obj,filename,material in added['parts']:export_part(obj,filename,material)\n    for i,button in enumerate(buttons,1):export_part")
patch("swept=[]", "v5.check(self=sys.modules[__name__],added=added,front=front,back=back,bracket=bracket,battery=envelope,antenna=antenna,speaker=speaker,adapter=adapter)\n    swept=[]")
patch("'screw':'M3x25','head_seat_z':9.4,'tip_z':34.4", "'screw':'M3x45','head_seat_z':BOTTOM+9.4,'tip_z':BOTTOM+9.4+45")
patch("case_bounds=[bbox(front),bbox(back)]", "case_bounds=[bbox(front),bbox(back)]+[bbox(o) for o in added['assembly']]\n    REPORT['new_modules']=added['metadata']\n    REPORT['camera_direction']=[0,0,1]\n    REPORT['screen_direction']=[0,0,1]")
patch("bpy.data.objects.remove(envelope,do_unlink=True);bpy.data.objects.remove(outer,do_unlink=True)", "bpy.data.objects.remove(envelope,do_unlink=True);bpy.data.objects.remove(outer,do_unlink=True)\n    for o in added['keepouts']:bpy.data.objects.remove(o,do_unlink=True)")
patch("gato_v4_montaje.blend","gato_v5_montaje.blend")
patch("01_gato_v4.png","01_gato_v5.png")
patch("02_frontal_v4.png","02_frontal_v5.png")
patch("render('01_gato_v5.png',(95,60,230),(0,8,27),155)", "render('01_gato_v5.png',(105,65,260),(0,14,24),184)")
patch("render('02_frontal_v5.png',(0,7,220),(0,7,27),149)", "render('02_frontal_v5.png',(0,14,250),(0,14,27),175)\n    render('05_camara_frontal.png',(55,95,200),(0,42,48),97)\n    render('06_interruptor_y_ventilacion.png',(90,45,-200),(10,0,-8),166)")
patch("front.hide_render=True;glass.hide_render=True", "front.hide_render=True;glass.hide_render=True\n    for o in added['hide_for_interior']:o.hide_render=True")
patch("render('04_montaje_interior.png',(100,90,180),(0,0,30),151)", "render('04_montaje_interior.png',(100,90,220),(0,14,24),176)")
patch("V4 COMPLETE","V5 COMPLETE")
(ROOT/'generar.py').write_text(s,encoding='utf-8')
vp=ROOT/'vista_stl.py';v=vp.read_text(encoding='utf-8').replace("(0,7,220),(0,7,13.5),144", "(0,14,250),(0,14,13.5),178");vp.write_text(v,encoding='utf-8')
print('V5 source prepared; front camera, provisional bays, original V4 preserved.')
