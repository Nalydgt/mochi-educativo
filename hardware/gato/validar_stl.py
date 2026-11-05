"""Independently inspect the exported binary STL files (Python + NumPy)."""
from pathlib import Path
import hashlib
import json
import struct
import numpy as np

ROOT=Path(__file__).resolve().parent
DTYPE=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])

def inspect(path):
    raw=path.read_bytes()
    n=struct.unpack_from('<I',raw,80)[0]
    assert len(raw)==84+50*n,(path.name,'STL size mismatch')
    data=np.frombuffer(raw,dtype=DTYPE,count=n,offset=84)
    triangles=data['vertices'].astype(np.float64)
    assert np.isfinite(triangles).all(),path.name
    verts,idx=np.unique(triangles.reshape(-1,3),axis=0,return_inverse=True)
    faces=idx.reshape(-1,3)
    edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    sorted_edges=np.sort(edges,axis=1)
    ue,inv,counts=np.unique(sorted_edges,axis=0,return_inverse=True,return_counts=True)
    signs=np.where(edges[:,0]<edges[:,1],1,-1)
    direction=np.bincount(inv,weights=signs,minlength=len(ue))
    area=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)/2
    volume=np.einsum('ij,ij->i',triangles[:,0],np.cross(triangles[:,1],triangles[:,2])).sum()/6
    parent=np.arange(len(verts))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    for a,b in ue:
        ra,rb=find(a),find(b)
        if ra!=rb: parent[rb]=ra
    components=len({find(i) for i in range(len(verts))})
    duplicate_faces=len(faces)-len(np.unique(np.sort(faces,axis=1),axis=0))
    r={'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'triangles':n,
       'vertices':len(verts),'boundary_edges':int(np.sum(counts==1)),
       'non_manifold_edges':int(np.sum(counts!=2)),
       'orientation_mismatch_edges':int(np.sum(direction!=0)),
       'duplicate_faces':duplicate_faces,'degenerate_triangles':int(np.sum(area<1e-9)),
       'components':components,'volume_mm3':round(float(volume),3),
       'dimensions_mm':np.round(verts.max(axis=0)-verts.min(axis=0),3).tolist(),
       'minimum_z_mm':float(verts[:,2].min())}
    r['pass']=all(r[k]==0 for k in ['boundary_edges','non_manifold_edges','orientation_mismatch_edges','duplicate_faces','degenerate_triangles']) and components==1 and volume>0 and abs(r['minimum_z_mm'])<1e-6
    return r

if __name__=='__main__':
    rows=[inspect(p) for p in sorted((ROOT/'stl').glob('*.stl'))]
    report={'method':'Independent binary STL read; exact exported vertex welding; edge incidence and orientation; connected components; triangle areas; signed volume; SHA256. Not a physical assembly test.','parts':rows,'pass':len(rows)==6 and all(r['pass'] for r in rows)}
    (ROOT/'validacion_stl.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    for r in rows: print(r['file'], 'OK' if r['pass'] else 'FAIL', r['dimensions_mm'])
    if not report['pass']: raise SystemExit(1)
