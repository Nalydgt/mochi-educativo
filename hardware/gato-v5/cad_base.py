"""Generate the actual printable cat enclosure and CAD previews in Blender 5.x.

Run from any directory:
  blender --background --factory-startup --python generar.py
  blender --background --factory-startup --python generar.py -- --no-render

All coordinates and exported STL coordinates are millimetres. The modelling
coordinates use the V4 right-handed front view: X right, Y toward the ears, Z
toward the display (native STEP transform X,-Z,Y+offset). Exported parts are independently placed on Z=0 for the print bed.
Electronic proxy objects are for clearance checks and previews, never exported.
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
P = json.loads((ROOT / "parametros.json").read_text(encoding="utf-8"))
B, D, BAT = P["body"], P["display"], P["battery"]
W, H, DEPTH, WALL = B["width"], B["height"], B["depth"], B["wall"]
SPLIT, GAP = B["split"], B["seam_gap"]
GLASS_Z = DEPTH - D["front_lip"]
INSERT_Z = GLASS_Z - D["insert_depth_from_glass"]
BRACKET_Z = INSERT_Z - 2.0
SCREWS = P["case_screws"]["centers"]
POSTS = [(-28.8, 0.0), (28.8, 0.0), (0.0, -28.8)]
PARTS, PROXIES, REPORT = [], [], {"revision": P["revision"], "units": "mm", "parts": [], "clearances": []}


def activate(o):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def apply(o, mod):
    activate(o)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def cube(name, size, at, radius=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=at)
    o = bpy.context.object
    o.name = name
    o.dimensions = size
    activate(o)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if radius:
        mod = o.modifiers.new("Radio mecanico", "BEVEL")
        mod.width = radius
        mod.segments = 12
        apply(o, mod)
    return o


def cylinder(name, diameter, z0, z1, xy=(0, 0), vertices=128, axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=diameter / 2, depth=z1 - z0)
    o = bpy.context.object
    o.name = name
    if axis == "Z":
        o.location = (xy[0], xy[1], (z0 + z1) / 2)
    elif axis == "X":
        o.rotation_euler[1] = math.pi / 2
        o.location = ((z0 + z1) / 2, xy[0], xy[1])
    activate(o)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o


def prism(name, points, z0, z1, bevel=0):
    n = len(points)
    verts = [(x, y, z) for z in (z0, z1) for x, y in points]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    recalc(o)
    if bevel:
        m = o.modifiers.new("Bordes suaves", "BEVEL")
        m.width, m.segments = bevel, 8
        apply(o, m)
    return o


def recalc(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()


def boolean(o,cutter,operation="DIFFERENCE",discard=True,solver="MANIFOLD"):
    mod = o.modifiers.new(operation, "BOOLEAN")
    mod.solver,mod.operation,mod.object=solver,operation,cutter
    apply(o, mod)
    if discard:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return o


def union(o, add):
    return boolean(o, add, "UNION")


def dup(o, name):
    new = o.copy()
    new.data = o.data.copy()
    new.name = name
    bpy.context.collection.objects.link(new)
    return new


def ring(name, width, height, radius, z0, z1, thickness):
    outer = cube(name, (width, height, z1 - z0), (0, 0, (z0 + z1) / 2))
    # Round only the XY perimeter; do not dome the mating surfaces.
    m = outer.modifiers.new("Contorno XY", "BEVEL")
    m.width, m.segments, m.affect = radius, 12, "EDGES"
    # A 2D bevel via extruded rounded-rectangle outline avoids height clamping.
    bpy.data.objects.remove(outer, do_unlink=True)
    outer = rounded_prism(name, width, height, radius, z0, z1)
    inner = rounded_prism("Interior aro", width - 2 * thickness, height - 2 * thickness,
                          max(radius - thickness, 0.5), z0 - 1, z1 + 1)
    return boolean(outer, inner)


def rounded_prism(name, width, height, radius, z0, z1):
    points = []
    for cx, cy, start in [(width/2-radius, height/2-radius, 0),
                          (-width/2+radius, height/2-radius, 90),
                          (-width/2+radius, -height/2+radius, 180),
                          (width/2-radius, -height/2+radius, 270)]:
        for i in range(17):
            a = math.radians(start + i * 90 / 16)
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return prism(name, points, z0, z1)


def pillow(name, width, height, depth, radius, bottom=0):
    """True elliptical silhouette with a continuous rounded front/back rim."""
    a,b = width/2,height/2
    r=radius
    rings=[]
    steps=20
    for i in range(steps+1):
        angle=(math.pi/2)*i/steps
        rings.append((bottom+r-r*math.cos(angle), r*math.sin(angle)-r))
    rings.append((bottom+depth-r,0))
    for i in range(1,steps+1):
        angle=(math.pi/2)*i/steps
        rings.append((bottom+depth-r+r*math.sin(angle),r*math.cos(angle)-r))
    count=192
    verts=[((a+offset)*math.cos(2*math.pi*j/count),
            (b+offset)*math.sin(2*math.pi*j/count),z)
           for z,offset in rings for j in range(count)]
    faces=[tuple(reversed(range(count)))]
    for k in range(len(rings)-1):
        for j in range(count):
            n=(j+1)%count
            faces.append((k*count+j,k*count+n,(k+1)*count+n,(k+1)*count+j))
    faces.append(tuple((len(rings)-1)*count+j for j in range(count)))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    recalc(obj)
    return obj


def ellipse_prism(name,width,height,z0,z1):
    points=[(width/2*math.cos(2*math.pi*i/192),
             height/2*math.sin(2*math.pi*i/192)) for i in range(192)]
    return prism(name,points,z0,z1)


def ellipse_ring(name,width,height,z0,z1,thickness):
    outer=ellipse_prism(name,width,height,z0,z1)
    return boolean(outer,ellipse_prism("Hueco eliptico",width-2*thickness,
                                     height-2*thickness,z0-1,z1+1))


def union_clipped(obj,feature,envelope):
    boolean(feature,envelope,"INTERSECT",discard=False)
    return union(obj,feature)


def rounded_triangle(points,trim=1.7):
    result=[]
    for i,p in enumerate(points):
        v=Vector(p)
        before=v+(Vector(points[i-1])-v).normalized()*trim
        after=v+(Vector(points[(i+1)%len(points)])-v).normalized()*trim
        for j in range(9):
            t=j/8
            q=(1-t)**2*before+2*t*(1-t)*v+t*t*after
            result.append(tuple(q))
    return result


def fuse_ears(outer):
    """Build one continuous exterior and round the broad ear/body junctions."""
    body_reference=dup(outer,"Referencia contorno exacto")
    for side in (-1,1):
        pts=[(side*x,y) for x,y in P["ears"]["root_points_right_xy"]]
        union(outer,prism("Oreja integrada",pts,SPLIT+0.3,DEPTH-3,5.0))
    remesh=outer.modifiers.new("Fusion volumetrica de orejas","REMESH")
    remesh.mode="VOXEL"
    remesh.voxel_size=P["ears"]["voxel_size"]
    remesh.use_smooth_shade=True
    apply(outer,remesh)
    smooth=outer.modifiers.new("Transicion suave en raices","SMOOTH")
    smooth.factor=0.8
    smooth.iterations=P["ears"]["smoothing_iterations"]
    apply(outer,smooth)
    # Keep the original precise body surface away from the ear-root blends.
    depsgraph=bpy.context.evaluated_depsgraph_get()
    bvh=BVHTree.FromObject(body_reference,depsgraph)
    for v in outer.data.vertices:
        x,y,z=v.co
        weight=min(max((y-28)/7,0),1)*min(max((abs(x)-12)/6,0),1)
        if weight<1:
            result=bvh.find_nearest(v.co)
            if result[0] is not None:
                v.co=result[0].lerp(v.co,weight)
    outer.data.update()
    bpy.data.objects.remove(body_reference,do_unlink=True)
    recalc(outer)
    # Reduce redundant flat facets without changing the join or mounting faces.
    dec=outer.modifiers.new("Simplificar superficie plana","DECIMATE")
    dec.decimate_type="DISSOLVE"
    dec.angle_limit=math.radians(0.8)
    apply(outer,dec)
    bm=bmesh.new()
    bm.from_mesh(outer.data)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bm.to_mesh(outer.data)
    bm.free()
    recalc(outer)
    return outer


def mat(name, color, roughness=0.35, metallic=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metallic
    return m


def finish(o, material):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.0001)
    # Sub-micron CSG slivers can collapse into wire edges. They carry no
    # surface and no volume; remove these remnants before freezing STL faces.
    wires=[e for e in bm.edges if not e.link_faces]
    if wires:bmesh.ops.delete(bm,geom=wires,context='EDGES')
    loose=[v for v in bm.verts if not v.link_faces]
    if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
    # Freeze the validated triangulation; STL must not re-tessellate n-gons.
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    # Boolean intersections can leave a collinear triangle on an otherwise
    # closed patch. Rotate its diagonal rather than removing a surface face.
    for _ in range(4):
        tiny=[f for f in bm.faces if f.calc_area()<1e-9]
        if not tiny:
            break
        for face in tiny:
            if not face.is_valid:
                continue
            edge=max(face.edges,key=lambda e:e.calc_length())
            if len(edge.link_faces)==2 and all(len(f.verts)==3 for f in edge.link_faces):
                bmesh.ops.rotate_edges(bm,edges=[edge],use_ccw=False)

    bm.to_mesh(o.data)
    bm.free()
    recalc(o)
    o.data.materials.clear()
    o.data.materials.append(material)
    # Smooth only the already curved faces, preserving the mechanical planes.
    for poly in o.data.polygons:
        n = poly.normal
        poly.use_smooth = not any(abs(v) > 0.99999 for v in n)
    return o


def mesh_stats(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bad_edges = sum(not e.is_manifold for e in bm.edges)
    if bad_edges:
        print("BAD_EDGES", o.name, [[tuple(o.matrix_world @ v.co) for v in e.verts]
                                     for e in bm.edges if not e.is_manifold][:8], flush=True)
    degenerate = sum(f.calc_area() < 1e-9 for f in bm.faces)
    volume = bm.calc_volume(signed=True)
    # Count edge-connected components. A printable STL must be one solid.
    seen, components = set(), 0
    for vertex in bm.verts:
        if vertex in seen:
            continue
        components += 1
        stack = [vertex]
        seen.add(vertex)
        while stack:
            for edge in stack.pop().link_edges:
                for other in edge.verts:
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
    coords = [o.matrix_world @ v.co for v in bm.verts]
    low = [min(v[i] for v in coords) for i in range(3)]
    high = [max(v[i] for v in coords) for i in range(3)]
    stats = {"name": o.name, "triangles": len(bm.faces), "non_manifold_edges": bad_edges,
             "degenerate_triangles": degenerate, "components": components,
             "volume_mm3": round(volume, 3), "bounds_mm": [low, high],
             "dimensions_mm": [round(high[i] - low[i], 3) for i in range(3)]}
    bm.free()
    return stats


def export(o, name):
    stats = mesh_stats(o)
    REPORT["parts"].append(stats)
    if stats["non_manifold_edges"] or stats["components"] != 1 or stats["degenerate_triangles"] or stats["volume_mm3"] <= 0:
        raise RuntimeError("Pieza no valida: " + json.dumps(stats))
    # Write binary STL directly, guaranteeing mm without scene-unit ambiguity.
    mesh = o.data.copy()
    mesh.calc_loop_triangles()
    zmin = min((o.matrix_world @ v.co).z for v in mesh.vertices)
    with (ROOT / "stl" / name).open("wb") as f:
        f.write(b"Mochi gato v5 frontal camera | mm | pieza orientada sobre cama".ljust(80, b" "))
        f.write(struct.pack("<I", len(mesh.loop_triangles)))
        for tri in mesh.loop_triangles:
            points = [o.matrix_world @ mesh.vertices[i].co for i in tri.vertices]
            points = [Vector((p.x, p.y, p.z - zmin)) for p in points]
            normal = (points[1] - points[0]).cross(points[2] - points[0]).normalized()
            f.write(struct.pack("<12fH", *normal, *(c for p in points for c in p), 0))
    bpy.data.meshes.remove(mesh)
    stats["stl"] = name
    PARTS.append(o)
    print("STL_OK", name, json.dumps(stats), flush=True)


def clearance(a, b):
    test = dup(a, "Test temporal")
    boolean(test, b, "INTERSECT", discard=False)
    bm = bmesh.new()
    bm.from_mesh(test.data)
    volume = abs(bm.calc_volume()) if bm.faces else 0
    if volume > 0.02:
        print("INTERFERENCE_BOUNDS", mesh_stats(test), flush=True)
    bm.free()
    bpy.data.objects.remove(test, do_unlink=True)
    REPORT["clearances"].append({"a": a.name, "b": b.name, "intersection_mm3": round(volume, 6)})
    if volume > 0.02:
        raise RuntimeError(f"Interferencia {a.name} / {b.name}: {volume:.3f} mm3")


def proxy(o, material):
    finish(o, material)
    o["solo_referencia_no_imprimir"] = True
    PROXIES.append(o)
    return o


def aim(o, target):
    forward = (Vector(target) - o.location).normalized()
    right = forward.cross(Vector((0,1,0))).normalized()
    up = right.cross(forward).normalized()
    o.rotation_euler = Matrix((right,up,-forward)).transposed().to_quaternion().to_euler()


def render(path, camera_at, target, scale=150):
    cam = bpy.data.objects.get("Camara")
    if not cam:
        bpy.ops.object.camera_add()
        cam = bpy.context.object
        cam.name = "Camara"
        cam.data.type = "ORTHO"
        bpy.context.scene.camera = cam
    cam.location, cam.data.ortho_scale = camera_at, scale
    aim(cam, target)
    bpy.context.scene.render.filepath = str(ROOT / "vistas" / path)
    bpy.ops.render.render(write_still=True)

