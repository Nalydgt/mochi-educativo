"""Provision only the educational NVS namespace over the attached USB cable."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mochi=root.parent
sys.path.insert(0,str(mochi/'tools'))
from mochi_device import Device
s=json.loads((root/'.runtime/pilot-secrets.json').read_text())
endpoint='http://100.84.233.67:8778'
with Device('COM3') as board:
 print(board.command('@peluqo-config '+endpoint+' '+s['provision']+' '+s['adult_pin'],'@peluqo_config',timeout=15))
 print(board.command('@peluqo','@peluqo active=',timeout=15))
 print(board.command('@peluqo-status','@peluqo active=',timeout=15))
(root/'.runtime/ACCESO_DISPOSITIVO.txt').write_text('PELUQO: credenciales privadas del adulto\nPIN para volver a Mochi o renovar el vínculo: '+s['adult_pin']+'\nEnlace privado: '+endpoint+'\nWeb: https://peluqo-mundos.vercel.app/expedicion\nEn la placa, abre el engranaje, introduce el PIN y pulsa Volver a Mochi. Para regresar al aula, usa Aprender con Peluqo.\n',encoding='utf-8')
