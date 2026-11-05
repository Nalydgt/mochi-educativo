"""Read-back mesh validation, neutral print project and local release packages."""
from pathlib import Path
import json,zipfile,hashlib,struct,xml.etree.ElementTree as ET
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ROOT=Path(__file__).resolve().parent
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',NS)
def tag(n):return '{'+NS+'}'+n
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stl(p):
    raw=p.read_bytes();n=struct.unpack_from('<I',raw,80)[0];assert len(raw)==84+50*n
    dt=np.dtype([('n','<f4',(3,)),('v','<f4',(3,3)),('a','<u2')])
    v,inv=np.unique(np.frombuffer(raw,dt,count=n,offset=84)['v'].reshape(-1,3),axis=0,return_inverse=True)
    return v.astype(float),inv.reshape(-1,3)
def mh(v,f):return hashlib.sha256(v.astype('<f4').tobytes()+f.astype('<i4').tobytes()).hexdigest()

def validate():
    r=json.loads((ROOT/'validacion.json').read_text(encoding='utf-8'));assert r['pass']and r['validation_mode']=='assembly'
    rows=[];files=sorted((ROOT/'stl').glob('*.stl'));assert len(files)==5
    for p in files:
        v,f=stl(p);q=v[f];area=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)/2
        edges=np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]));u,inv,cnt=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
        balance=np.bincount(inv,weights=np.where(edges[:,0]<edges[:,1],1,-1));graph=coo_matrix((np.ones(len(u)),(u[:,0],u[:,1])),shape=(len(v),len(v)))
        components=connected_components(graph,directed=False,return_labels=False)
        volume=np.einsum('ij,ij->i',q[:,0],np.cross(q[:,1],q[:,2])).sum()/6
        assert np.all(cnt==2)and np.all(balance==0)and components==1 and np.all(area>1e-12)and volume>0,p.name
        assert abs(v[:,2].min())<1e-4,p.name
        assert sha(p)==r['stl_sha256'][p.name]
        rows.append({'file':p.name,'sha256':sha(p),'triangles':len(f),'closed':True,'oriented':True,'components':int(components),'min_area_mm2':float(area.min()),'volume_mm3':float(volume),'dimensions_mm':np.ptp(v,axis=0).tolist(),'bed_z':float(v[:,2].min())})
    for n,h in r['source_files_sha256'].items():assert sha(ROOT/n)==h,n
    (ROOT/'validacion_stl.json').write_text(json.dumps({'pass':True,'files':rows,'scope':'Serialized topology, dimensions and bed placement; not a physical print test.'},indent=2)+'\n',encoding='utf-8')

def project():
    items=[('01_frontal_TamaPoke_gato.stl',(45,50)),('02_cuerpo_redondo.stl',(125,50)),('03_bandeja_unica.stl',(210,50)),('04_boton_inferior.stl',(45,135)),('05_boton_superior.stl',(60,135))]
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'es-ES'})
    ET.SubElement(model,tag('metadata'),{'name':'Title'}).text='Peluqo V12 - frontal TamaPoke, cuerpo redondo, bandeja unica'
    ET.SubElement(model,tag('metadata'),{'name':'Attribution'}).text='Personal project adaptation. Original functional front from supplied TamaPoke by Jetto Hobby, Standard Digital File License; rounded style and V10 ears derived from supplied EchoEar by ESP-Friends, BY-NC-SA.'
    ET.SubElement(model,tag('metadata'),{'name':'Description'}).text='5 print instances: front, body, integrated tray and two buttons. Three rear closure screws; original screen fixings. Select printer, material and supports according to LEEME. No G-code.'
    resources=ET.SubElement(model,tag('resources'));build=ET.SubElement(model,tag('build'));ids={};expected={};placements=[];bounds=[]
    for name,xy in items:
        v,f=stl(ROOT/'stl'/name)
        if name not in ids:
            i=len(ids)+1;ids[name]=i;expected[i]=mh(v,f)
            ob=ET.SubElement(resources,tag('object'),{'id':str(i),'type':'model','name':name[:-4]});me=ET.SubElement(ob,tag('mesh'));ve=ET.SubElement(me,tag('vertices'));tr=ET.SubElement(me,tag('triangles'))
            for p in v:ET.SubElement(ve,tag('vertex'),{k:format(float(a),'.9g')for k,a in zip(('x','y','z'),p)})
            for p in f:ET.SubElement(tr,tag('triangle'),{k:str(int(a))for k,a in zip(('v1','v2','v3'),p)})
        offset=np.r_[np.asarray(xy)-(v.min(0)[:2]+v.max(0)[:2])/2,0]
        ET.SubElement(build,tag('item'),{'objectid':str(ids[name]),'transform':'1 0 0 0 1 0 0 0 1 '+' '.join(format(float(a),'.9g')for a in offset)})
        lo,hi=v.min(0)+offset,v.max(0)+offset;assert np.all(lo[:2]>0)and np.all(hi[:2]<256)
        bounds.append((lo,hi));placements.append({'stl':name,'sha256':sha(ROOT/'stl'/name),'translation_mm':offset.tolist()})
    for i,a in enumerate(bounds):
        for b in bounds[i+1:]:assert not(np.all(a[1][:2]>b[0][:2])and np.all(b[1][:2]>a[0][:2]))
    types='<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    path=ROOT/'Peluqo_V12_Impresion.3mf'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED)as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels);z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True));z.writestr('Metadata/piezas.json',json.dumps(placements,indent=2))
    with zipfile.ZipFile(path)as z:
        assert z.testzip()is None;r=ET.fromstring(z.read('3D/3dmodel.model'))
        for ob in r.findall('./'+tag('resources')+'/'+tag('object')):
            v=np.asarray([[float(p.attrib[k])for k in ('x','y','z')]for p in ob.findall('.//'+tag('vertex'))]);f=np.asarray([[int(p.attrib[k])for k in ('v1','v2','v3')]for p in ob.findall('.//'+tag('triangle'))]);assert mh(v,f)==expected[int(ob.attrib['id'])]
        assert len(r.findall('./'+tag('build')+'/'+tag('item')))==5
    (ROOT/'validacion_3mf.json').write_text(json.dumps({'pass':True,'file':path.name,'sha256':sha(path),'objects':5,'instances':5,'mesh_roundtrip':True,'placements':placements},indent=2)+'\n',encoding='utf-8')

def package():
    common=[ROOT/n for n in ('LEEME.md','parametros.json','validacion.json','validacion_stl.json','validacion_3mf.json','Peluqo_V12_Impresion.3mf')]+sorted((ROOT/'stl').glob('*.stl'))+sorted((ROOT/'vistas').glob('0[1-4]_*.png'))
    full=common+[ROOT/n for n in ('Peluqo_V12_montaje.blend','generar.py','base_geom.py','cad_base.py','limpiar_malla.py','entregar.py','requirements.txt')]+sorted((ROOT/'referencias').iterdir())
    rows=[]
    for name,files in [('Peluqo_V12_STL_3MF.zip',common),('Peluqo_V12_Completo.zip',full)]:
        path=ROOT/name
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            for p in files:assert p.is_file(),p;z.write(p,p.relative_to(ROOT).as_posix())
        with zipfile.ZipFile(path)as z:
            assert z.testzip()is None
            for p in files:assert hashlib.sha256(z.read(p.relative_to(ROOT).as_posix())).hexdigest()==sha(p)
        rows.append({'file':name,'sha256':sha(path),'bytes':path.stat().st_size})
    out={'pass':True,'files':rows};(ROOT/'entrega.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out,indent=2))

if __name__=='__main__':validate();project();package()
