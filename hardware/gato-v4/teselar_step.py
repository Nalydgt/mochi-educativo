from pathlib import Path
import sys,json,time
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'.runtime/cad-step'))
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE,TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
print('OCP read start',flush=True)
reader=STEPControl_Reader()
reader.ReadFile(str(ROOT/'referencias/waveshare-ESP32-S3-Touch-AMOLED-1_75.stp'))
reader.TransferRoots()
shape=reader.OneShape()
print('OCP read complete; triangulating at 0.03 mm',flush=True)
BRepMesh_IncrementalMesh(shape,0.03,False,0.12,True).Perform()
rows=json.loads((ROOT/'auditoria/step_parts.json').read_text(encoding='utf-8'))
centers=np.asarray([r['center_native'] for r in rows]);tree=cKDTree(centers)
used=set();vertices=[];arrays={};cursor=0
solid_exp=TopExp_Explorer(shape,TopAbs_SOLID)
count=0
while solid_exp.More():
    solid=TopoDS.Solid(solid_exp.Current())
    prop=GProp_GProps();BRepGProp.VolumeProperties_s(solid,prop)
    center=prop.CentreOfMass();com=np.array([center.X(),center.Y(),center.Z()]);mass=abs(prop.Mass())
    distances,indices=tree.query(com,k=8)
    candidates=[(float(d)+0.1*abs(mass-rows[int(i)]['volume'])/max(mass,0.001),int(i)) for d,i in zip(np.atleast_1d(distances),np.atleast_1d(indices)) if int(i) not in used]
    if not candidates:raise RuntimeError('No unmatched CAD label')
    _,idx=min(candidates);used.add(idx);row=rows[idx]
    vs=[];fs=[];start=0
    face_exp=TopExp_Explorer(solid,TopAbs_FACE)
    while face_exp.More():
        face=TopoDS.Face(face_exp.Current());loc=TopLoc_Location()
        tri=BRep_Tool.Triangulation_s(face,loc)
        if tri is not None:
            tr=loc.Transformation()
            for i in range(1,tri.NbNodes()+1):
                pt=tri.Node(i).Transformed(tr);vs.append((pt.X(),pt.Y(),pt.Z()))
            for i in range(1,tri.NbTriangles()+1):
                a,b,c=tri.Triangle(i).Get()
                if face.Orientation()==TopAbs_REVERSED:b,c=c,b
                fs.append((start+a-1,start+b-1,start+c-1))
            start+=tri.NbNodes()
        face_exp.Next()
    co=np.asarray(vs,dtype=float)
    co_unique,inv=np.unique(np.round(co,7),axis=0,return_inverse=True)
    f=inv[np.asarray(fs,dtype=int)]
    vol=float(np.einsum('ij,ij->i',co_unique[f[:,0]],np.cross(co_unique[f[:,1]],co_unique[f[:,2]])).sum()/6)
    if vol<0:f=f[:,[0,2,1]];vol=-vol
    arrays['faces_'+str(row['tag'])]=(f+cursor).astype(np.int32)
    vertices.append(co_unique);cursor+=len(co_unique)
    row['triangles']=len(f);row['tessellated_volume']=vol
    row['mesh_bbox_native']=[co_unique.min(axis=0).tolist(),co_unique.max(axis=0).tolist()]
    row['label_com_error']=float(np.linalg.norm(com-centers[idx]))
    count+=1
    if count%150==0:print('CAD solids tessellated',count,flush=True)
    solid_exp.Next()
arrays['vertices']=np.concatenate(vertices)
np.savez_compressed(ROOT/'referencias/step_mesh_native.npz',**arrays)
(ROOT/'auditoria/step_parts.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
print('OCP COMPLETE',count,'solids',cursor,'vertices',sum(r.get('triangles',0) for r in rows),'triangles',flush=True)
print('Max label match error:',max(r.get('label_com_error',0) for r in rows),flush=True)
