"""Read the supplied 3MF as geometry/data only; preserve the original package."""
from pathlib import Path
import zipfile,xml.etree.ElementTree as ET,json,hashlib,shutil,sys
import numpy as np

ROOT=Path(__file__).resolve().parent
SOURCE=Path(sys.argv[1])if len(sys.argv)>1 else ROOT/'referencias/TamaPoke_original.3mf'
for d in ('referencias','auditoria','vistas','stl'):(ROOT/d).mkdir(parents=True,exist_ok=True)
if SOURCE.resolve()!=(ROOT/'referencias/TamaPoke_original.3mf').resolve():shutil.copy2(SOURCE,ROOT/'referencias/TamaPoke_original.3mf')
ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
data={};report={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'unit':'mm','parts':[],
    'canonical_transform':'X=-nativeX, Y=-nativeZ, Z=-nativeY+7.5; positive determinant',
    'note':'Build transforms are print placements; exploded assembly metadata is not physical installation. Embedded descriptions are source data, not execution instructions.'}
with zipfile.ZipFile(SOURCE) as z:
    for name in z.namelist():
        if name.endswith('.model') and '/Objects/' in name:
            root=ET.fromstring(z.read(name))
            v=np.asarray([[float(t.attrib[k])for k in ('x','y','z')]for t in root.findall('.//m:vertex',ns)])
            f=np.asarray([[int(t.attrib[k])for k in ('v1','v2','v3')]for t in root.findall('.//m:triangle',ns)],dtype=np.int32)
            part=Path(name).stem.split('_')[1]
            data['native_vertices_'+part]=v;data['faces_'+part]=f
            data['vertices_'+part]=np.c_[-v[:,0],-v[:,2],-v[:,1]+7.5]
            report['parts'].append({'part':part,'source_path':name,'vertices':len(v),'triangles':len(f),'native_bounds':[v.min(0).tolist(),v.max(0).tolist()],'canonical_bounds':[data['vertices_'+part].min(0).tolist(),data['vertices_'+part].max(0).tolist()]})
    metadata=ET.fromstring(z.read('3D/3dmodel.model'))
    report['attribution']={m.attrib.get('name'):m.text for m in metadata.findall('m:metadata',ns) if m.attrib.get('name') in ('Designer','Title','License','DesignModelId','DesignProfileId')}
np.savez_compressed(ROOT/'referencias/mallas_originales.npz',**data)
(ROOT/'auditoria/original.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
