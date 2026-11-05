from pathlib import Path
import sys,json
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]/'.runtime/cad-step'))
import gmsh
gmsh.initialize()
gmsh.option.setNumber('General.Terminal',0)
gmsh.option.setNumber('Geometry.OCCImportLabels',1)
gmsh.open(str(root/'referencias/waveshare-ESP32-S3-Touch-AMOLED-1_75.stp'))
rows=[]
for dim,tag in gmsh.model.getEntities(3):
    bbox=list(gmsh.model.occ.getBoundingBox(dim,tag))
    rows.append({'tag':tag,'name':gmsh.model.getEntityName(dim,tag),'bbox_native':bbox,'center_native':list(gmsh.model.occ.getCenterOfMass(dim,tag)),'volume':gmsh.model.occ.getMass(dim,tag)})
p=root/'auditoria/step_parts.json'
p.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')

print('CAD imported:',len(rows),'solids',flush=True)
import numpy as np
gmsh.option.setNumber('Mesh.MeshSizeMin',0.25)
gmsh.option.setNumber('Mesh.MeshSizeMax',0.9)
gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',18)
gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0)
gmsh.model.mesh.generate(2)
tags,coords,_=gmsh.model.mesh.getNodes()
coords=np.array(coords).reshape(-1,3)
lookup=np.full(int(max(tags))+1,-1,dtype=np.int64)
lookup[np.asarray(tags,dtype=np.int64)]=np.arange(len(tags))
arrays={'vertices':coords}
for row in rows:
    faces=[]
    for dim,stag in gmsh.model.getBoundary([(3,row['tag'])],oriented=True):
        types,elementTags,nodeTags=gmsh.model.mesh.getElements(2,abs(stag))
        for typ,nodes in zip(types,nodeTags):
            if typ!=2:continue
            f=lookup[np.asarray(nodes,dtype=np.int64)].reshape(-1,3)
            if stag<0:f=f[:,[0,2,1]]
            faces.append(f)
    f=np.concatenate(faces).astype(np.int32) if faces else np.empty((0,3),dtype=np.int32)
    arrays['faces_'+str(row['tag'])]=f
    row['triangles']=len(f)
    row['tessellated_volume']=float(np.einsum('ij,ij->i',coords[f[:,0]],np.cross(coords[f[:,1]],coords[f[:,2]])).sum()/6) if len(f) else 0
np.savez_compressed(root/'referencias/step_mesh_native.npz',**arrays)
p.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('CAD mesh ready:',len(coords),'nodes;',sum(r['triangles'] for r in rows),'triangles',flush=True)
print('Board mass CAD / mesh:',rows[0]['volume'],rows[0]['tessellated_volume'],flush=True)
gmsh.finalize()
