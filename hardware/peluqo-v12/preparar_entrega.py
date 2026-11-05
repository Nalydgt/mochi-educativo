from pathlib import Path
import json
root=Path(__file__).resolve().parent
p=root/'parametros.json';q=json.loads(p.read_text(encoding='utf-8'))
q['display'].update({'window_diameter':49.5,'lower_throat_diameter':47.0,'mounts_rear_view':[[0,20.2],[-13.75,-14.79789],[13.75,-14.79789]]})
q['body'].update({'width':68,'height':68,'rear_bottom':-37,'seam_gap':0,'alignment':'Original TamaPoke case screw axes and added circular guide'})
q['gps_antenna']['center_xy']=[1,0]
q.pop('screen_cassette',None)
q['internal_stack']={'mount_centers':q['tray']['stems'],'note':'Integrated printed supports, no screws or separate spacers'}
q['source_scope']='Original supplied TamaPoke front screen interface and internal mounts preserved; spherical EchoEar style outside, plain rounded ears, one trapped tray, three original rear closure screws.'
p.write_text(json.dumps(q,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
s=(root.parent/'peluqo-v10/entregar.py').read_text(encoding='utf-8').replace('V10','V12').replace('v10','v12')
s=s.replace('len(files)==10','len(files)==5').replace(')==10',')==5').replace("'objects':9,'instances':10","'objects':5,'instances':5")
start=s.index('    items=');end=s.index('\n',start)
s=s[:start]+"    items=[('01_frontal_TamaPoke_gato.stl',(45,50)),('02_cuerpo_redondo.stl',(125,50)),('03_bandeja_unica.stl',(210,50)),('04_boton_inferior.stl',(45,135)),('05_boton_superior.stl',(60,135))]"+s[end:]
s=s.replace('Peluqo V12 - encaje circular, pantalla desmontable, base65','Peluqo V12 - frontal TamaPoke, cuerpo redondo, bandeja unica')
s=s.replace('10 print instances; two spacers. Screen cassette enters from front before separate bezel. Select printer, material and supports according to LEEME. No G-code or original printer profiles.','5 print instances: front, body, integrated tray and two buttons. Three rear closure screws; original screen fixings. Select printer, material and supports according to LEEME. No G-code.')
(root/'entregar.py').write_text(s,encoding='utf-8')
