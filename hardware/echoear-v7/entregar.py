"""Minimal serialized-mesh check, neutral 3MF export, and local delivery ZIPs."""
from pathlib import Path
import json,zipfile,hashlib,struct,xml.etree.ElementTree as ET
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ROOT=Path(__file__).resolve().parent
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',NS)
def tag(n):return '{'+NS+'}'+n
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_stl(p):
    raw=p.read_bytes();n=struct.unpack_from('<I',raw,80)[0];assert len(raw)==84+50*n
    dt=np.dtype([('n','<f4',(3,)),('v','<f4',(3,3)),('a','<u2')])
    v,inv=np.unique(np.frombuffer(raw,dt,count=n,offset=84)['v'].reshape(-1,3),axis=0,return_inverse=True)
    return v.astype(float),inv.reshape(-1,3)
def mesh_hash(v,f):return hashlib.sha256(v.astype('<f4').tobytes()+f.astype('<i4').tobytes()).hexdigest()
def mesh_checks():
    report=json.loads((ROOT/'validacion.json').read_text(encoding='utf-8'));assert report['pass']and report['validation_mode']=='quick'
    rows=[];files=sorted((ROOT/'stl').glob('*.stl'));assert len(files)==8
    for p in files:
        v,f=read_stl(p);q=v[f];n=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);area=np.linalg.norm(n,axis=1)/2
        e=np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]));u,inv,cnt=np.unique(np.sort(e,axis=1),axis=0,return_inverse=True,return_counts=True)
        signs=np.where(e[:,0]<e[:,1],1,-1);balance=np.bincount(inv,weights=signs)
        g=coo_matrix((np.ones(len(u)),(u[:,0],u[:,1])),shape=(len(v),len(v)));components=connected_components(g,directed=False,return_labels=False)
        volume=np.sum(np.einsum('ij,ij->i',q[:,0],np.cross(q[:,1],q[:,2])))/6
        assert np.all(cnt==2)and np.all(balance==0)and components==1 and np.all(area>1e-10)and volume>0
        assert abs(v[:,2].min())<1e-4
        assert sha(p)==report['stl_sha256'][p.name]
        rows.append({'file':p.name,'sha256':sha(p),'triangles':len(f),'closed':True,'oriented':True,'connected_components':int(components),'min_area_mm2':float(area.min()),'dimensions_mm':np.ptp(v,axis=0).tolist(),'volume_mm3':float(volume),'bed_z_min':float(v[:,2].min())})
    for n,h in report['source_files_sha256'].items():assert sha(ROOT/n)==h
    out={'pass':True,'mode':'minimal','checks':'Serialized STL closure, orientation, component count, area, volume and bed placement; not a physical or full hardware test.','files':rows}
    (ROOT/'validacion_stl.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');return rows

def project():
    names=[('01_frontal_gato_EchoEar.stl',(50,50)),('02_trasera_EchoEar.stl',(140,50)),('03_bandeja_bateria_GPS.stl',(219,50)),('04_soporte_altavoz.stl',(50,140)),('05_separador_7_7mm.stl',(100,130)),('05_separador_7_7mm.stl',(113,130)),('06_boton_inferior.stl',(145,130)),('07_boton_superior.stl',(160,130))]
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'es-ES'})
    ET.SubElement(model,tag('metadata'),{'name':'Title'}).text='EchoEar V7 - Waveshare1.75, EEMB500, GPS, dos botones'
    ET.SubElement(model,tag('metadata'),{'name':'Attribution'}).text='Exterior and ears from supplied EchoEar by ESP-Friends, BY-NC-SA. Private project adaptation; internal trays from previous TamaPoke adaptation, Jetto Hobby, Standard Digital File License.'
    ET.SubElement(model,tag('metadata'),{'name':'Description'}).text='Millimetres, 100 percent. Select printer/material/support settings. Rear open rim and front face on bed; two spacers. No firmware, original printer profiles or G-code.'
    resources=ET.SubElement(model,tag('resources'));build=ET.SubElement(model,tag('build'));ids={};expected={};placements=[];boxes=[]
    for name,center in names:
        v,f=read_stl(ROOT/'stl'/name)
        if name not in ids:
            i=len(ids)+1;ids[name]=i;expected[i]=mesh_hash(v,f)
            ob=ET.SubElement(resources,tag('object'),{'id':str(i),'type':'model','name':name[:-4]});me=ET.SubElement(ob,tag('mesh'));ve=ET.SubElement(me,tag('vertices'));tr=ET.SubElement(me,tag('triangles'))
            for a in v:ET.SubElement(ve,tag('vertex'),{k:format(float(x),'.9g')for k,x in zip(('x','y','z'),a)})
            for a in f:ET.SubElement(tr,tag('triangle'),{k:str(int(x))for k,x in zip(('v1','v2','v3'),a)})
        offset=np.r_[np.asarray(center)-(v.min(0)[:2]+v.max(0)[:2])/2,0]
        ET.SubElement(build,tag('item'),{'objectid':str(ids[name]),'transform':'1 0 0 0 1 0 0 0 1 '+' '.join(format(float(x),'.9g')for x in offset)})
        lo,hi=v.min(0)+offset,v.max(0)+offset;assert np.all(lo[:2]>0)and np.all(hi[:2]<256)
        boxes.append((lo,hi));placements.append({'stl':name,'sha256':sha(ROOT/'stl'/name),'translation':offset.tolist()})
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:assert not(np.all(a[1][:2]>b[0][:2])and np.all(b[1][:2]>a[0][:2]))
    p=ROOT/'EchoEar_V7_Impresion.3mf'
    types='<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED)as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels);z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True));z.writestr('Metadata/piezas.json',json.dumps(placements,indent=2))
    with zipfile.ZipFile(p)as z:
        assert z.testzip()is None;r=ET.fromstring(z.read('3D/3dmodel.model'))
        for ob in r.findall('./'+tag('resources')+'/'+tag('object')):
            v=np.asarray([[float(x.attrib[k])for k in ('x','y','z')]for x in ob.findall('.//'+tag('vertex'))]);f=np.asarray([[int(x.attrib[k])for k in ('v1','v2','v3')]for x in ob.findall('.//'+tag('triangle'))]);assert mesh_hash(v,f)==expected[int(ob.attrib['id'])]
    out={'pass':True,'file':p.name,'sha256':sha(p),'objects':7,'print_instances':8,'two_spacers':True,'mesh_roundtrip':True,'units':'mm','placements':placements}
    (ROOT/'validacion_3mf.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')

def package():
    minimal=[ROOT/'LEEME.md',ROOT/'parametros.json',ROOT/'validacion.json',ROOT/'validacion_stl.json',ROOT/'validacion_3mf.json',ROOT/'EchoEar_V7_Impresion.3mf',*sorted((ROOT/'stl').glob('*.stl')),*sorted((ROOT/'vistas').glob('0[1-4]_*.png'))]
    full=minimal+[ROOT/'EchoEar_V7_montaje.blend',ROOT/'generar.py',ROOT/'cad_base.py',ROOT/'entregar.py',ROOT/'auditoria/source.json',*[ROOT/'referencias'/n for n in ('EchoEar_original.3mf','canonical_source.npz','source_meshes.npz','sphere.npy','carrier.stl','speaker.stl','spacer.stl','guts_registration.json','medidas_waveshare.json','medidas_bateria_gps.json')]]
    result=[]
    for name,files in [('EchoEar_V7_STL_3MF.zip',minimal),('EchoEar_V7_Completo.zip',full)]:
        p=ROOT/name
        with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            for f in files:assert f.is_file(),f;z.write(f,str(f.relative_to(ROOT)).replace('\\','/'))
        with zipfile.ZipFile(p)as z:
            assert z.testzip()is None
            for f in files:assert hashlib.sha256(z.read(str(f.relative_to(ROOT)).replace('\\','/'))).hexdigest()==sha(f)
        result.append({'file':name,'bytes':p.stat().st_size,'sha256':sha(p)})
    out={'pass':True,'verification':'minimal','files':result};(ROOT/'entrega.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,indent=2))

if __name__=='__main__':mesh_checks();project();package()
