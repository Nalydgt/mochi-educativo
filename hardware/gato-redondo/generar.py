"""Generate the actual printable cat enclosure and CAD previews in Blender 5.x.

Run from any directory:
  blender --background --factory-startup --python generar.py
  blender --background --factory-startup --python generar.py -- --no-render

All coordinates and exported STL coordinates are millimetres. The modelling
coordinates follow the manufacturer's REAR view: X to its right, Y up, Z toward
the display. Exported parts are independently placed on Z=0 for the print bed.
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


def boolean(o, cutter, operation="DIFFERENCE", discard=True):
    mod = o.modifiers.new(operation, "BOOLEAN")
    mod.solver, mod.operation, mod.object = "MANIFOLD", operation, cutter
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
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00002)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.00002)
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
        f.write(b"Mochi gato v2 round | mm | pieza orientada sobre cama".ljust(80, b" "))
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


def main(no_render):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 0.001
    ivory = mat("PLA marfil", (0.88, 0.83, 0.73), 0.3)
    pink = mat("Interior de orejas", (0.75, 0.29, 0.27), 0.4)
    dark = mat("Pantalla negra", (0.008, 0.014, 0.02), 0.23)
    green = mat("PCB de referencia", (0.018, 0.15, 0.10), 0.5)
    battery_mat = mat("Bateria 955565", (0.40, 0.47, 0.52), 0.33, 0.65)
    ceramic = mat("Antena ceramica provisional", (0.70, 0.61, 0.47), 0.6)
    speaker_mat = mat("Altavoz provisional", (0.04, 0.04, 0.05), 0.8)
    face_mat = mat("Ojos en pantalla - ilustrativos", (0.49, 0.82, 0.76), 0.4)

    outer = pillow("Envolvente mecanica",W,H,DEPTH,B["radius"])
    shell = dup(outer, "Cuerpo hueco")
    boolean(shell, pillow("Hueco",W-2*WALL,H-2*WALL,DEPTH-2*WALL,
                          B["radius"]-WALL,bottom=WALL))
    front = dup(shell, "01 Frontal gato")
    boolean(front, cube("Corte frontal", (220, 220, SPLIT+20), (0, 0, (SPLIT-20)/2)))
    back = dup(shell, "02 Tapa trasera")
    boolean(back, cube("Corte trasero", (220, 220, 160), (0, 0, SPLIT-GAP+80)))
    bpy.data.objects.remove(shell, do_unlink=True)

    # Solid rounded ears belong to the front half only.
    for side in (-1, 1):
        ear_pts = [(side*19, 36), (side*44, 34), (side*36, 63)]
        ear = prism("Oreja exterior",ear_pts,SPLIT+0.3,DEPTH-3,5.0)
        union(outer, dup(ear, "Envolvente oreja"))
        union(front, ear)
        pts = [(side*26,41.5),(side*36.8,40.5),(side*34.7,53.0)]
        boolean(front, prism("Alojamiento oreja", pts, DEPTH-4.3, DEPTH+2, 1.2))
        # Matching decorative insert, inset 0.3 mm on each profile edge.
        cx, cy = sum(p[0] for p in pts)/3, sum(p[1] for p in pts)/3
        shrunk = [(cx+(x-cx)*0.88, cy+(y-cy)*0.88) for x,y in pts]
        ins = finish(prism("04 Oreja " + ("izquierda" if side<0 else "derecha"),
                           shrunk, DEPTH-4.25, DEPTH-3.15, 0.65), pink)
        export(ins, "04_oreja_izquierda.stl" if side<0 else "05_oreja_derecha.stl")

    # Hollow the portion of the ear roots that extends into the electronics bay.
    boolean(front,pillow("Despeje interior de orejas",W-2*WALL,H-2*WALL,
                          DEPTH-2*WALL,B["radius"]-WALL,bottom=WALL))
    boolean(front, cylinder("Ventana AMOLED", D["window_diameter"], 20, 60))
    boolean(front, cylinder("Asiento del cristal", D["glass_diameter"] + D["seat_diametral_clearance"],
                            20, GLASS_Z))

    for x,y in SCREWS:
        union(front,cylinder("Torre tuerca M3",10.0,SPLIT,DEPTH-9.0,(x,y)))
        boolean(front, cylinder("Paso M3 ciego", 3.4, SPLIT-1, SPLIT+12.5, (x,y)))
        nut = cylinder("Hexagono tuerca M3", P["case_screws"]["nut_across_flats"] / math.cos(math.pi/6),
                       SPLIT-0.2, SPLIT+P["case_screws"]["nut_pocket_depth"], (x,y), 6)
        boolean(front, nut)
        union(back,cylinder("Columna posterior M3",10.0,9.0,SPLIT-GAP,(x,y)))
    # Ear roots are solid: relieve their inside lower edge for the rear lip.
    boolean(front,ellipse_prism("Holgura labio bajo orejas",W-2*WALL,H-2*WALL,
                                 SPLIT-0.2,SPLIT+3.0))

    # Rear alignment step: 0.35 mm per side; relief around all four bosses.
    flange = ellipse_ring("Base de encaje",W-3.6,H-3.6,SPLIT-2.2,SPLIT-GAP,2.35)
    lip = ellipse_ring("Labio de alineacion",W-5.5,H-5.5,SPLIT-0.9,SPLIT+2.5,1.4)
    for x,y in SCREWS:
        boolean(lip, cylinder("Holgura de torre", 10.9, SPLIT-4, SPLIT+4, (x,y)))
    union(back, flange)
    union(back, lip)

    # Reversible display retainer, using the OEM M2 mounting pattern.
    bracket = cylinder("03 Soporte placa Waveshare", 53.4, BRACKET_Z, INSERT_Z)
    boolean(bracket, cylinder("Acceso a electronica", 43.6, BRACKET_Z-1, INSERT_Z+1))
    for x,y in D["mounts_rear_view"]:
        union(bracket, cylinder("Lengueta M2 OEM", 7.0, BRACKET_Z, INSERT_Z, (x,y)))
        boolean(bracket, cylinder("M2 OEM", 2.4, BRACKET_Z-1, INSERT_Z+1, (x,y)))
    for x,y in POSTS:
        union(bracket, cylinder("Lengueta de fijacion", 7.2, BRACKET_Z, INSERT_Z, (x,y)))
        boolean(bracket, cylinder("M2 del soporte", 2.4, BRACKET_Z-1, INSERT_Z+1, (x,y)))
        union(front, cylinder("Pilar soporte", 7.0, INSERT_Z, DEPTH-2.0, (x,y)))
        boolean(front, cylinder("Piloto M2", 1.7, INSERT_Z-1, DEPTH-5.5, (x,y)))

    # Battery cradle with a slack fit, low side rails, and two strap slots.
    bw = BAT["width"] + 2*BAT["clearance_xy_each_side"]
    bh = BAT["height"] + 2*BAT["clearance_xy_each_side"]
    by, bz = BAT["center_y"], BAT["floor_z"]
    tray = rounded_prism("Bandeja bateria 955565", bw+4, bh+4, 4.0, bz-2, bz)
    tray.location.y = by
    for x in (-22, 22):
        for y in (-20, 20):
            union(back, cube("Pie de bandeja", (7,7,bz-2.0), (x,by+y,(bz-2.0)/2+1.8)))
    # Short bridges, while keeping a clear central path for the soft strap.
    for rx in (-24,-10,10,24):
        union(back, cube("Nervio bajo bandeja", (10,bh-8,bz-2), (rx,by,(bz-2)/2+1.8)))
    rails = ring("Bordes de bandeja", bw+4, bh+4, 2.7, bz-0.3, bz+3.4, 2)
    rails.location.y = by
    union(tray, rails)
    # Slots traverse the supporting plate and its rim, but never the outer skin.
    for sy in (-1,1):
        boolean(tray, cube("Ranura cincha", (9,3.4,12), (0,by+sy*(bh/2+0.4),bz+2)))
    # Low-radius exits for battery lead and PH2-to-MX1.25 adapter lead.
    boolean(tray, cube("Salida cables bateria", (10,12,10), (bw/2,by+15,bz+5), 1.0))
    union(back,tray)

    # GNSS antenna slides into a loose cradle facing upward (+Y), away from
    # the battery and display. This is an explicitly provisional 25x25x4 part.
    ax, ay, az = P["gps_antenna"]["center"]
    for sx in (-1,1):
        union(back, cube("Guia antena GPS", (2.0, 9.0, 10.8),
                         (ax+sx*13.5,37.0,18.5), 0.6))
    union(back, cube("Repisa antena GPS", (29.0,9.0,2.0), (ax,37.0,12.5), 0.6))

    # Side speaker cradle: the cell fills the rear, so sound exits at the side.
    for sy in (-1,1):
        union(back,cube("Guia altavoz lateral",(10.0,2.0,13.5),(-44,sy*15.0,16.8),0.6))
    speaker_base = cube("Apoyo altavoz lateral",(9.0,28.0,2.0),(-43.5,0,7.0),0.6)
    union(back, speaker_base)

    # Cable-sized access wells. Port Z and controls must be checked on-board.
    boolean(front, cube("Acceso USB-C", (48,16,10),(44,0,P["ports"]["usb_center_z"]), 1.3))
    boolean(front, cube("Acceso microSD", (48,17,4),(-44,0,44), 0.7))
    for y in P["ports"]["button_y"]:
        boolean(front, cube("Acceso boton", (48,8,7),(-44,y,45), 1.1))
    for y in P["ports"]["microphone_y"]:
        for dz in (-1.8,1.8):
            boolean(front, cylinder("Respiradero microfono", 2.2,25,W/2+3,
                                    (y,P["ports"]["microphone_center_z"]+dz), axis="X", vertices=40))
    # Side grille follows the split, preserving material around the case lip.
    for yy in (-7.2,-3.6,0,3.6,7.2):
        boolean(back, cube("Ranura altavoz", (36,1.7,8.0),(-W/2,yy,17.4), 0.6))
    for x,y in SCREWS:
        boolean(back, cylinder("Paso tornillo tapa", 3.4,-2,SPLIT+1,(x,y)))
        boolean(back, cylinder("Asiento cabeza M3", 6.8, -2, P["case_screws"]["head_seat_z"], (x,y)))

    # Test coupon repeats the real window, glass clearance and lip depth.
    coupon = cylinder("06 Prueba asiento pantalla", 58, 0, 4)
    boolean(coupon, cylinder("Ventana muestra", D["window_diameter"], -1, 6))
    boolean(coupon, cylinder("Asiento muestra", D["glass_diameter"]+D["seat_diametral_clearance"], -1, 4-D["front_lip"]))
    for o in (front, back, bracket, coupon):
        finish(o, ivory)
    export(front, "01_frontal_gato.stl")
    export(back, "02_tapa_trasera.stl")
    export(bracket, "03_soporte_waveshare.stl")
    export(coupon, "06_prueba_pantalla.stl")
    coupon.hide_render = True
    coupon.hide_set(True)
    bpy.data.objects.remove(outer, do_unlink=True)

    battery = proxy(cube("REF Bateria 65 x 55 x 9.5", (BAT["width"],BAT["height"],BAT["thickness"]),
                         (0,by,bz+BAT["thickness"]/2), 0.7), battery_mat)
    battery_envelope = cube("Holgura bateria 67 x 57 x 11.5", (bw,bh,BAT["thickness"]+BAT["clearance_above"]),
                            (0,by,bz+(BAT["thickness"]+BAT["clearance_above"])/2), 0.7)
    antenna = proxy(cube("REF Antena GPS 25 x 25 x 4 POR CONFIRMAR", (25,4,25), (ax,ay,az), 0.3), ceramic)
    sp = P["speaker"]
    sx,sy,sz = sp["center"]
    speaker = proxy(cylinder("REF Altavoz D28 x 7 POR CONFIRMAR", sp["diameter"], sx-sp["depth"]/2, sx+sp["depth"]/2, (sy,sz), axis="X"), speaker_mat)
    glass = proxy(cylinder("REF Cristal AMOLED D48.96", D["glass_diameter"], GLASS_Z-2.05, GLASS_Z), dark)
    pcb = proxy(cylinder("REF PCB D46", 46, GLASS_Z-6.9, GLASS_Z-5.3), green)
    adapter = proxy(cube("REF Reserva adaptador PH2 a MX1.25", (8,16,7),(42,5,25), 1), pink)
    for a,b in [(front,back),(front,bracket),(back,bracket),
                (front,battery_envelope),(back,battery_envelope),(bracket,battery_envelope),
                (front,glass),(back,glass),(front,pcb),(back,pcb),
                (front,antenna),(back,antenna),(bracket,antenna),
                (front,speaker),(back,speaker),(bracket,speaker),
                (battery_envelope,speaker),(battery_envelope,antenna),
                (front,adapter),(back,adapter),(bracket,adapter),
                (battery_envelope,adapter)]:
        clearance(a,b)
    bpy.data.objects.remove(battery_envelope, do_unlink=True)

    # Illustrative expression only; no changes to the real Mochi firmware.
    face_decor=[]
    for x in (-8,8):
        eye=ellipse_prism("REF Ojos suaves ilustrativos",5.0,8.6,GLASS_Z+0.02,GLASS_Z+0.12)
        eye.location.x,eye.location.y=x,2.0
        finish(eye,face_mat)
        face_decor.append(eye)
    for x in (-14,14):
        cheek=ellipse_prism("REF Colorete en pantalla",4.8,2.4,GLASS_Z+0.02,GLASS_Z+0.1)
        cheek.location.x,cheek.location.y=x,-4.3
        finish(cheek,pink)
        face_decor.append(cheek)
    arc=[]
    for i in range(25):
        a=math.pi+math.pi*i/24
        arc.append((3.4*math.cos(a),-3.5+2.2*math.sin(a)))
    for i in range(24,-1,-1):
        a=math.pi+math.pi*i/24
        arc.append((2.6*math.cos(a),-3.5+1.4*math.sin(a)))
    smile=prism("REF Sonrisa ilustrativa",arc,GLASS_Z+0.02,GLASS_Z+0.13)
    finish(smile,face_mat)
    face_decor.append(smile)

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 40
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1500,1500,100
    scene.world.color = (0.24,0.24,0.24)
    scene.view_settings.view_transform = "AgX"
    for name, loc, power, size in [("Luz principal",(-100,100,200),1000000,140),
                                    ("Luz relleno",(110,30,100),550000,110),
                                    ("Luz borde",(0,-70,-80),450000,90)]:
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name, light.data.energy, light.data.shape, light.data.size = name,power,"DISK",size
        aim(light,(0,6,24))
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    REPORT["hardware_status"] = P["status"]
    REPORT["battery_source"] = BAT["source"]
    REPORT["assembly_bounds_mm"] = [W, max(v[1] for o in (front,back) for v in [(o.matrix_world@Vector(c)) for c in o.bound_box])+H/2, DEPTH]
    REPORT["notes"] = ["Las intersecciones validan los volumenes nominales modelados, no una medicion de la placa fisica.",
                       "STL binario en mm, una sola componente conexa por pieza, colocado en Z=0.",
                       "El soporte utiliza insert_depth_from_glass=10.4 como hipotesis a verificar con el hardware.",
                       "Antena y altavoz provisionales; puertos aproximados a partir del plano oficial."]
    (ROOT/"validacion.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding="utf-8")
    # Open the editable file with the complete product framed and a usable camera.
    bpy.ops.object.camera_add(location=(90,60,220))
    cam = bpy.context.object
    cam.name, cam.data.type, cam.data.ortho_scale = "Camara", "ORTHO", 156
    aim(cam,(0,9,24))
    scene.camera = cam
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                region = area.spaces.active.region_3d
                region.view_location, region.view_distance = (0,9,27),180
                region.view_rotation = cam.rotation_euler.to_quaternion()
    activate(front)
    # Save the assembled, editable model before changing visibility/positions.
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"gato_montaje.blend"))
    if no_render:
        return
    for o in PROXIES:
        o.hide_render = o not in (glass,)
    render("01_gato_perspectiva.png", (90,60,220), (0,8,27),156)
    render("02_gato_frontal.png", (0,8,220), (0,8,27),149)
    # Real exploded view, moving the exported geometry and actual proxy shapes.
    for o in face_decor:
        o.hide_render = True
    for o in PROXIES:
        o.hide_render = False
    for o in (front, glass, pcb):
        o.location.z += 65
    for o in PARTS:
        if "Oreja" in o.name:
            o.location.z += 65
    bracket.location.z += 40
    battery.location.z += 19
    render("03_gato_despiece.png", (-170,155,250), (0,9,55), 230)
    # Interior rear view with front, ring, screen hidden, battery moved aside.
    front.hide_render = bracket.hide_render = glass.hide_render = pcb.hide_render = True
    for o in PARTS:
        if "Oreja" in o.name:
            o.hide_render = True
    battery.hide_render = True
    render("04_tapa_interior.png", (110,100,180), (0,0,15),150)
    print("CAD_COMPLETO", str(ROOT), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    main(args.no_render)
