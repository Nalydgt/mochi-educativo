"""Create neutral millimetre 3MF print layouts from the verified STL files.

No original machine, filament, temperatures, G-code or embedded instructions
are copied. The two alternatives contain one front each and two spacers.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import json,zipfile,hashlib,struct
import numpy as np
ROOT=Path(__file__).resolve().parent
CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',CORE)
def tag(n):return '{'+CORE+'}'+n
def stl(path):
    raw=path.read_bytes();n=struct.unpack_from('<I',raw,80)[0]
    dt=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    triangles=np.frombuffer(raw,dtype=dt,count=n,offset=84)['vertices']
    v,inv=np.unique(triangles.reshape(-1,3),axis=0,return_inverse=True)
    return v,inv.reshape(-1,3)
def meshhash(v,f):return hashlib.sha256(v.astype('<f4').tobytes()+f.astype('<i4').tobytes()).hexdigest()

def build(style,front):
    items=[(front,(43,50)),('03_cuerpo_sin_carga_magnetica.stl',(120,50)),('04_bandeja_bateria_y_GPS.stl',(199,50)),('05_soporte_altavoz.stl',(43,137)),('06_separador_interno_7_7mm.stl',(95,125)),('06_separador_interno_7_7mm.stl',(108,125)),('07_pulsador_inferior.stl',(134,125)),('08_pulsador_superior.stl',(147,125))]
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'es-ES'})
    ET.SubElement(model,tag('metadata'),{'name':'Title'}).text='TamaPoke V6 '+style+' - EEMB500, GPS, dos botones'
    ET.SubElement(model,tag('metadata'),{'name':'Description'}).text='Adaptacion personal del 3MF aportado. Una alternativa frontal; separador interno por duplicado. Seleccionar perfil de impresora y soportes segun LEEME.'
    ET.SubElement(model,tag('metadata'),{'name':'Attribution'}).text='Original supplied TamaPoke design: Jetto Hobby; Standard Digital File License. Personal adaptation.'
    resources=ET.SubElement(model,tag('resources'));assembly=ET.SubElement(model,tag('build'))
    ids={};expected={};bounds=[];manifest=[]
    for filename,center in items:
        v,f=stl(ROOT/'stl'/filename)
        if filename not in ids:
            object_id=len(ids)+1;ids[filename]=object_id
            o=ET.SubElement(resources,tag('object'),{'id':str(object_id),'type':'model','name':filename[:-4]})
            mesh=ET.SubElement(o,tag('mesh'));vertices=ET.SubElement(mesh,tag('vertices'));triangles=ET.SubElement(mesh,tag('triangles'))
            for x,y,z in v:ET.SubElement(vertices,tag('vertex'),{'x':format(float(x),'.9g'),'y':format(float(y),'.9g'),'z':format(float(z),'.9g')})
            for a,b,c in f:ET.SubElement(triangles,tag('triangle'),{'v1':str(int(a)),'v2':str(int(b)),'v3':str(int(c))})
            expected[object_id]=meshhash(v,f)
        offset=np.r_[np.asarray(center)-(v.min(0)[:2]+v.max(0)[:2])/2,0]
        ET.SubElement(assembly,tag('item'),{'objectid':str(ids[filename]),'transform':'1 0 0 0 1 0 0 0 1 '+' '.join(format(float(x),'.9g')for x in offset)})
        lo,hi=v.min(0)+offset,v.max(0)+offset
        assert np.all(lo[:2]>=0)and np.all(hi[:2]<=256)and abs(lo[2])<1e-5
        bounds.append((lo,hi));manifest.append({'stl':filename,'translation_mm':offset.tolist(),'stl_sha256':hashlib.sha256((ROOT/'stl'/filename).read_bytes()).hexdigest()})
    for i,a in enumerate(bounds):
        for b in bounds[i+1:]:assert not(np.all(a[1][:2]>b[0][:2])and np.all(b[1][:2]>a[0][:2])),'Overlapping print placements'
    types='<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    path=ROOT/('TamaPoke_'+style+'_V6_Impresion.3mf')
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels);z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
        z.writestr('Metadata/piezas_y_huellas.json',json.dumps({'style':style,'instances':manifest},indent=2)+'\n')
    with zipfile.ZipFile(path)as z:
        assert z.testzip()is None;r=ET.fromstring(z.read('3D/3dmodel.model'));assert r.attrib['unit']=='millimeter'
        for o in r.findall('./'+tag('resources')+'/'+tag('object')):
            v=np.asarray([[float(p.attrib[k])for k in ('x','y','z')]for p in o.findall('.//'+tag('vertex'))],dtype='<f4')
            f=np.asarray([[int(p.attrib[k])for k in ('v1','v2','v3')]for p in o.findall('.//'+tag('triangle'))],dtype='<i4')
            assert meshhash(v,f)==expected[int(o.attrib['id'])]
        assert len(r.findall('./'+tag('build')+'/'+tag('item')))==8
    return {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pass':True,'objects':7,'print_instances':8,'duplicate_spacers':2,'units':'mm','verified_mesh_roundtrip':True,'source_stls':manifest}

if __name__=='__main__':
    rows=[build('Gato','01_frontal_gato.stl'),build('Mochi','02_frontal_mochi.stl')]
    (ROOT/'validacion_3mf.json').write_text(json.dumps({'pass':all(x['pass']for x in rows),'projects':rows},indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items()if k!='source_stls'}for r in rows],indent=2))
