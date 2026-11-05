"""Normalize closed CSG meshes with a maximum one-micron surface tolerance."""
import sys,numpy as np,manifold3d as m
source=np.load(sys.argv[1]);solid=m.Manifold(m.Mesh64(source['vertices'],source['faces']))
if str(solid.status())!='Error.NoError':raise RuntimeError(str(solid.status()))
clean=solid.simplify(.001);mesh=clean.to_mesh64()
np.savez_compressed(sys.argv[2],vertices=np.asarray(mesh.vert_properties)[:,:3],faces=np.asarray(mesh.tri_verts),volume=clean.volume(),tolerance_mm=.001)
