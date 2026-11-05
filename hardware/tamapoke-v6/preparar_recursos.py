from pathlib import Path
import shutil,json
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'gato-v5'
for d in ('stl','vistas','auditoria','referencias'):(ROOT/d).mkdir(parents=True,exist_ok=True)
text=(OLD/'cad_base.py').read_text(encoding='utf-8').replace('Mochi gato v5 frontal camera','TamaPoke V6 personal adaptation')
(ROOT/'cad_base.py').write_text(text,encoding='utf-8')
for src,dst in [(OLD/'referencias/step_mesh_native.npz',ROOT/'referencias/step_mesh_native.npz'),(OLD/'auditoria/step_parts.json',ROOT/'auditoria/step_parts.json'),(OLD/'auditoria/step_measurements_independent.json',ROOT/'auditoria/step_measurements_independent.json')]:shutil.copy2(src,dst)
p=json.loads((OLD/'parametros.json').read_text(encoding='utf-8'))
p['revision']='tamapoke-v6-eemb500-gps-dos-botones'
p['body']={'width':60,'height':60,'depth':15,'wall':2,'radius':6,'split':0,'seam_gap':0.3,'rear_bottom':-30,'outer_bulge':0.8}
p['display'].update(glass_front_z=12.9,seat_diameter=49.66,seat_cut_start_z=10.0,front_lip=2.1)
p['case_screws']={'centers':[[21.61293,-7.86646],[-17.61902,-14.78411],[-3.99391,22.65058]],'screw':'M2x8','head_seat_z':-4,'tip_z':4,'retention':'Original printed pilot D1.8 retained; no magnetic charging parts'}
p['battery']={'model':'EEMB LP562438 500 mAh','width':24.5,'height':40,'thickness':5.9,'bay':[26.5,42,7.4],'center_xy':[1,-2],'floor_z':-17.7,'connector':'User JST2.0 / PH2.0, board MX1.25; adapter bay reserved'}
p['gps_antenna']={'model':'Waveshare GNSS ceramic antenna complete assembly reference','dimensions':[27,27,6.7],'bay':[28,28,7.6],'center_xy':[1,1],'bounds_z':[-26.4,-19.7],'radiating_face':'rear -Z','cable_length_reference':35,'identity_confirmed_on_user_part':False}
p['speaker']={'source':'Original HOUSING_3 recess measured 32x22x3.5; actual speaker not measured','bay':[32.5,22.5,3.8],'center_xy':[1,1],'floor_z':-8.8}
p['internal_stack']={'mount_centers':[[-18.5,5],[20.5,5]],'spacer_height':7.7,'screws':'2 x M2x16 plus 0.5 mm washer','nut_pocket_z':[-23.2,-21.3],'retaining_lip_z':[-21.3,-19.3],'head_z':-8.3,'tip_z':-24.3}
p['ears']={'method':'Continuous radial deformation of original front exterior only','angles':[58,122],'amplitude':14,'sigma_degrees':8,'taper_degrees':[14,22],'protected_radius':25.4,'full_weight_radius':28.2}
p['buttons']={'stem_diameter':2.5,'bore_diameter':3.2,'collar_diameter':4.4,'contact_nose_diameter':1.6,'rest_gap':0.25,'outward_retention_stop':4.8,'tested_inward_travel':0.45,'hard_inward_stop':False,'source':'Official STEP axes; inward travel is a verification sample, not a mechanical stop'}
p['source_scope']='Personal adaptation of supplied TamaPoke.3mf: preserve original front and case screw pattern, correct screen relief/OEM screw slots, add second button, replace rear internals with small battery and complete GPS antenna; cat and mochi alternative fronts.'
(ROOT/'parametros.json').write_text(json.dumps(p,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print('V6 resources ready')
