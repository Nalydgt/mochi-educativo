"""Inspect actual exported binary STL files, independently of Blender.

Run without arguments to inspect every STL in this revision's stl/ directory,
or pass explicit STL paths. Requires Python and NumPy. Writes validacion_stl.json
even when a file is invalid. The front-ear check assumes the documented case
coordinates (XY preserved; each exported part translated only to bed Z=0).
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

import numpy as np


ROOT = Path(__file__).resolve().parent
DTYPE = np.dtype([
    ("normal", "<f4", (3,)),
    ("vertices", "<f4", (3, 3)),
    ("attribute", "<u2"),
])
AREA_EPSILON_MM2 = 1e-9
BED_EPSILON_MM = 1e-6
END_SECTION_EPSILON_MM = 1e-4
EXPECTED_V5_FILES = {
    "01_frontal_gato.stl", "02_tapa_trasera.stl", "03_soporte_waveshare.stl",
    "06_prueba_pantalla.stl", "07_pulsador_inferior.stl",
    "08_pulsador_superior.stl", "09_prueba_guia_botones.stl",
    "10_prueba_tuercas.stl",
    "11_bandeja_camara_frontal.stl", "12_adaptador_objetivo_20mm.stl",
    "13_adaptador_objetivo_ciego.stl", "14_bandeja_MT3608.stl",
    "15_cassette_SS12D00.stl", "16_retenedor_SS12D00.stl",
    "17_bandeja_bateria.stl",
}


class UnionFind:
    def __init__(self, size):
        self.parent = np.arange(size, dtype=np.int64)

    def find(self, i):
        i = int(i)
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = int(self.parent[i])
        return i

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a



class VerticalSections:
    """Exact vertical-line intersections with the serialized STL triangles."""
    def __init__(self, triangles):
        self.a = triangles[:, 0]
        self.b = triangles[:, 1] - self.a
        self.c = triangles[:, 2] - self.a
        self.det = self.b[:, 0] * self.c[:, 1] - self.b[:, 1] * self.c[:, 0]
        self.minimum = triangles[:, :, :2].min(axis=1)
        self.maximum = triangles[:, :, :2].max(axis=1)

    def intersections(self, xy):
        x, y = xy
        use = (abs(self.det) > 1e-12)
        use &= (self.minimum[:, 0] <= x + 1e-8) & (self.maximum[:, 0] >= x - 1e-8)
        use &= (self.minimum[:, 1] <= y + 1e-8) & (self.maximum[:, 1] >= y - 1e-8)
        a, b, c, det = self.a[use], self.b[use], self.c[use], self.det[use]
        dx, dy = x - a[:, 0], y - a[:, 1]
        u = (dx * c[:, 1] - dy * c[:, 0]) / det
        v = (b[:, 0] * dy - b[:, 1] * dx) / det
        inside = (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1 + 1e-8)
        values = np.sort((a[:, 2] + u * b[:, 2] + v * c[:, 2])[inside])
        if not len(values):
            return values
        return values[np.r_[True, np.diff(values) > 1e-4]]

    def is_material(self, xy, z):
        values = self.intersections(xy)
        return bool(np.sum(values < z) % 2)


def shoulder_check(sections, label, xy, bore, across_flats, lip, pocket):
    """Sample a load-bearing annulus beside a side-entry nut pocket.

    Three radial bands and 36 angular stations test the actual binary mesh,
    rather than trusting a Boolean or a claimed pocket height. The central
    screw clearance must remain void through the same lip. Explicit lip
    bounds support shoulders above or below the nut, for either clamp direction.
    """
    epsilon = 0.005
    radii = np.linspace(bore / 2 + 0.12, across_flats / 2 - 0.12, 3)
    failures, thicknesses = [], []
    for radius in radii:
        for station in range(36):
            angle = np.deg2rad(station * 10 + 0.137)
            point = (xy[0] + radius * np.cos(angle), xy[1] + radius * np.sin(angle))
            cuts = sections.intersections(point)
            solid = list(zip(cuts[::2], cuts[1::2]))
            covering = [(lo, hi) for lo, hi in solid
                        if lo <= lip[0] + epsilon and hi >= lip[1] - epsilon]
            pocket_is_void = not bool(np.sum(cuts < (pocket[0] + pocket[1]) / 2) % 2)
            if covering:
                thicknesses.append(float(covering[0][1] - covering[0][0]))
            if not covering or not pocket_is_void:
                failures.append({"xy": list(point), "intersections_z_mm": cuts.tolist(),
                                 "lip_solid": bool(covering), "pocket_void": pocket_is_void})
    axis_cuts = sections.intersections(xy)
    axis_solids = list(zip(axis_cuts[::2], axis_cuts[1::2]))
    axis_void = not any(lo < lip[1] - epsilon and hi > lip[0] + epsilon
                        for lo, hi in axis_solids)
    return {
        "label": label,
        "center_xy_mm": list(xy),
        "sample_count": 108,
        "radial_bands_mm": radii.tolist(),
        "expected_lip_z_mm": list(lip),
        "expected_lip_thickness_mm": lip[1] - lip[0],
        "expected_pocket_z_mm": list(pocket),
        "lip_side": "above_pocket" if lip[0] >= pocket[1] - epsilon else "below_pocket",
        "minimum_sampled_solid_interval_mm": min(thicknesses) if thicknesses else None,
        "screw_axis_void_through_lip": axis_void,
        "failed_samples": failures,
        "pass": not failures and axis_void,
    }

def inspect(path):
    path = Path(path)
    raw = path.read_bytes()
    result = {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "pass": False,
    }
    if len(raw) < 84:
        return dict(result, error="Binary STL header is truncated")
    count = struct.unpack_from("<I", raw, 80)[0]
    result["triangles"] = count
    if len(raw) != 84 + 50 * count:
        return dict(result, error="Binary STL length does not match its triangle count")
    if not count:
        return dict(result, error="STL contains no triangles")
    records = np.frombuffer(raw, dtype=DTYPE, count=count, offset=84)
    triangles = records["vertices"].astype(np.float64)
    if not np.isfinite(triangles).all():
        return dict(result, error="STL contains non-finite vertex coordinates")

    # Weld exactly the serialized float32 positions, without hiding cracks with
    # a fuzzy distance tolerance. Binary normal vectors are not trusted.
    vertices, inverse = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edge_keys = np.sort(edges, axis=1)
    unique_edges, edge_inverse, incidence = np.unique(
        edge_keys, axis=0, return_inverse=True, return_counts=True
    )
    direction = np.bincount(
        edge_inverse, weights=np.where(edges[:, 0] < edges[:, 1], 1, -1),
        minlength=len(unique_edges),
    )
    areas = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    ) / 2
    volume = float(np.einsum(
        "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    ).sum() / 6)

    # Edge-connected faces, rather than vertex connectivity alone, reject two
    # printable shells that merely touch at a point. Corner connectivity also
    # verifies a single surface fan at each welded vertex (no bow-tie vertices).
    face_sets = UnionFind(count)
    corner_sets = UnionFind(3 * count)
    edge_order = np.argsort(edge_inverse, kind="stable")
    offsets = np.cumsum(np.r_[0, incidence])
    for key_index in np.flatnonzero(incidence == 2):
        e0, e1 = edge_order[offsets[key_index]:offsets[key_index + 1]]
        f0, f1 = int(e0 % count), int(e1 % count)
        face_sets.join(f0, f1)
        c0, c1 = int(e0 // count), int(e1 // count)
        a0, b0 = 3 * f0 + c0, 3 * f0 + (c0 + 1) % 3
        a1, b1 = 3 * f1 + c1, 3 * f1 + (c1 + 1) % 3
        if edges[e0, 0] == edges[e1, 0]:
            corner_sets.join(a0, a1)
            corner_sets.join(b0, b1)
        else:
            corner_sets.join(a0, b1)
            corner_sets.join(b0, a1)
    face_roots = np.fromiter((face_sets.find(i) for i in range(count)), dtype=np.int64)
    corner_roots = np.fromiter(
        (corner_sets.find(i) for i in range(3 * count)), dtype=np.int64
    )
    vertex_fans = np.unique(np.column_stack([faces.ravel(), corner_roots]), axis=0)
    fan_count = np.bincount(vertex_fans[:, 0], minlength=len(vertices))
    components = len(np.unique(face_roots))

    minimum, maximum = vertices.min(axis=0), vertices.max(axis=0)
    result.update({
        "vertices": len(vertices),
        "boundary_edges": int(np.sum(incidence == 1)),
        "non_manifold_edges": int(np.sum(incidence != 2)),
        "non_manifold_vertices": int(np.sum(fan_count != 1)),
        "orientation_mismatch_edges": int(np.sum(direction != 0)),
        "duplicate_faces": len(faces) - len(np.unique(np.sort(faces, axis=1), axis=0)),
        "degenerate_triangles": int(np.sum(areas < AREA_EPSILON_MM2)),
        "components": components,
        "volume_mm3": round(volume, 6),
        "minimum_triangle_area_mm2": float(areas.min()),
        "dimensions_mm": np.round(maximum - minimum, 6).tolist(),
        "bounds_mm": [minimum.tolist(), maximum.tolist()],
        "minimum_z_mm": float(minimum[2]),
    })
    if path.name == "01_frontal_gato.stl":
        parameters = json.loads((ROOT / "parametros.json").read_text(encoding="utf-8"))
        body = parameters["body"]
        # A bare ellipse reaches center_y + height/2. Require actual tips
        # beyond that silhouette, rather than counting ordinary forehead faces.
        tip_y = body["center_y"] + body["height"] / 2 + 1.0
        tip_x = body["width"] * 0.18
        face_centers = triangles.mean(axis=1)
        body_faces = np.flatnonzero(face_centers[:, 1] < body["center_y"])
        ear_masks = [
            (face_centers[:, 0] < -tip_x) & (face_centers[:, 1] > tip_y),
            (face_centers[:, 0] > tip_x) & (face_centers[:, 1] > tip_y),
        ]
        result["ear_tip_region"] = {"minimum_y_mm": tip_y, "minimum_abs_x_mm": tip_x}
        result["ear_tip_triangles"] = [int(mask.sum()) for mask in ear_masks]
        result["ears_connected_to_body"] = bool(
            len(body_faces) and all(
                mask.any() and np.all(face_roots[mask] == face_roots[body_faces[0]])
                for mask in ear_masks
            )
        )
    if path.name in {"07_pulsador_inferior.stl", "08_pulsador_superior.stl"}:
        base = vertices[vertices[:, 2] <= minimum[2] + END_SECTION_EPSILON_MM]
        tip = vertices[vertices[:, 2] >= maximum[2] - END_SECTION_EPSILON_MM]
        base_extent = base[:, :2].max(axis=0) - base[:, :2].min(axis=0)
        tip_extent = tip[:, :2].max(axis=0) - tip[:, :2].min(axis=0)
        result["button_print_orientation"] = {
            "end_section_epsilon_mm": END_SECTION_EPSILON_MM,
            "base_extent_xy_mm": base_extent.tolist(),
            "upper_tip_extent_xy_mm": tip_extent.tolist(),
            "head_on_bed_nose_up": bool(
                np.all(base_extent >= 7.5) and np.all(tip_extent <= 2.0)
            ),
        }
    if path.name in {"12_adaptador_objetivo_20mm.stl", "13_adaptador_objetivo_ciego.stl"}:
        base = vertices[vertices[:, 2] <= minimum[2] + END_SECTION_EPSILON_MM]
        tip = vertices[vertices[:, 2] >= maximum[2] - END_SECTION_EPSILON_MM]
        base_extent = base[:, :2].max(axis=0) - base[:, :2].min(axis=0)
        tip_extent = tip[:, :2].max(axis=0) - tip[:, :2].min(axis=0)
        result["optic_adapter_print_orientation"] = {
            "end_section_epsilon_mm": END_SECTION_EPSILON_MM,
            "base_extent_xy_mm": base_extent.tolist(),
            "upper_neck_extent_xy_mm": tip_extent.tolist(),
            "flat_flange_on_bed_neck_up": bool(
                np.all(np.abs(base_extent - (36.0, 28.0)) < 0.1)
                and np.all(np.abs(tip_extent - (22.8, 22.8)) < 0.1)
            ),
        }
    if path.name == "10_prueba_tuercas.stl":
        sections = VerticalSections(triangles)
        result["sampled_nut_shoulders"] = [
            shoulder_check(sections, "M3 coupon", (-8.0, 0.0), 3.4, 5.8, (0.0, 2.0), (2.0, 4.8)),
            shoulder_check(sections, "M2 coupon", (8.0, 0.0), 2.4, 4.2, (0.0, 2.0), (2.0, 3.9)),
        ]
    if path.name == "01_frontal_gato.stl":
        parameters = json.loads((ROOT / "parametros.json").read_text(encoding="utf-8"))
        split = parameters["body"]["split"]
        sections = VerticalSections(triangles)
        tests = []
        closure = parameters["case_screws"]
        for index, xy in enumerate(closure["centers"], 1):
            tests.append(shoulder_check(
                sections, "M3 closure " + str(index), xy, closure["clearance_diameter"],
                closure["nut_across_flats"], (0.0, closure["nut_pocket_z"][0] - split),
                tuple(z - split for z in closure["nut_pocket_z"]),
            ))
        carrier = parameters["carrier"]
        for index, xy in enumerate(carrier["mount_centers"], 1):
            tests.append(shoulder_check(
                sections, "M2 carrier " + str(index), xy, 2.4,
                carrier["nut_across_flats"],
                (carrier["top_z"] - split, carrier["nut_pocket_z"][0] - split),
                tuple(z - split for z in carrier["nut_pocket_z"]),
            ))
        for index, x in enumerate((-29.5, 29.5), 1):
            tests.append(shoulder_check(
                sections, "M2 front camera " + str(index), (x, 44.0), 2.4, 4.2,
                (47.4 - split, 49.4 - split), (49.4 - split, 51.3 - split),
            ))
        result["sampled_nut_shoulders"] = tests
    if path.name == "02_tapa_trasera.stl":
        parameters = json.loads((ROOT / "parametros.json").read_text(encoding="utf-8"))
        # Rear STL preserves XY and is shifted upward by rear_extension to Z0.
        offset = parameters["body"]["rear_extension"]
        sections = VerticalSections(triangles)
        tests = []
        for index, y in enumerate((-23.0, 13.0), 1):
            tests.append(shoulder_check(
                sections, "M2 rear boost " + str(index), (0.0, y), 2.4, 4.2,
                (-13.0 + offset, -11.0 + offset),
                (-14.9 + offset, -13.0 + offset),
            ))
        for index, x in enumerate((20.0, 44.0), 1):
            tests.append(shoulder_check(
                sections, "M2 rear switch cassette " + str(index), (x, -5.0), 2.4, 4.2,
                (-15.6 + offset, -13.6 + offset),
                (-13.6 + offset, -11.7 + offset),
            ))
        for index, xy in enumerate(parameters["battery"]["tray_mount_centers"], 1):
            tests.append(shoulder_check(
                sections, "M2 removable battery tray " + str(index), xy, 2.4, 4.2,
                (8.0 + offset, 10.0 + offset),
                (6.1 + offset, 8.0 + offset),
            ))
        result["sampled_nut_shoulders"] = tests
    zero_fields = [
        "boundary_edges", "non_manifold_edges", "non_manifold_vertices",
        "orientation_mismatch_edges", "duplicate_faces", "degenerate_triangles",
    ]
    result["pass"] = bool(
        all(result[key] == 0 for key in zero_fields)
        and components == 1 and volume > 0
        and abs(result["minimum_z_mm"]) < BED_EPSILON_MM
        and result.get("ears_connected_to_body", True)
        and result.get("button_print_orientation", {}).get("head_on_bed_nose_up", True)
        and result.get("optic_adapter_print_orientation", {}).get("flat_flange_on_bed_neck_up", True)
        and all(test["pass"] for test in result.get("sampled_nut_shoulders", []))
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Explicit binary STL paths")
    args = parser.parse_args()
    paths = args.files or sorted((ROOT / "stl").glob("*.stl"))
    parts = []
    for path in paths:
        try:
            parts.append(inspect(path))
        except (OSError, ValueError, struct.error) as error:
            parts.append({"file": path.name, "pass": False, "error": str(error)})
    names = {path.name for path in paths}
    manifest_checked = not bool(args.files)
    missing = sorted(EXPECTED_V5_FILES - names) if manifest_checked else []
    unexpected = sorted(names - EXPECTED_V5_FILES) if manifest_checked else []
    report = {
        "method": "Independent read of binary STL; exact serialized-vertex welding; edge incidence and direction; edge-connected surface components; vertex fans; triangle areas; duplicate faces; signed volume; bed position; SHA256. Nut-retaining shoulders sampled on three annular bands at 36 angles. Not a physical fit or self-intersection test.",
        "units": "mm",
        "area_epsilon_mm2": AREA_EPSILON_MM2,
        "bed_epsilon_mm": BED_EPSILON_MM,
        "end_section_epsilon_mm": END_SECTION_EPSILON_MM,
        "parts": parts,
        "part_count": len(parts),
        "directory_manifest_checked": manifest_checked,
        "expected_v5_files": sorted(EXPECTED_V5_FILES),
        "missing_files": missing,
        "unexpected_files": unexpected,
        "pass": bool(parts) and not missing and not unexpected and all(part["pass"] for part in parts),
    }
    (ROOT / "validacion_stl.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for part in parts:
        print(part["file"], "OK" if part["pass"] else "FAIL",
              part.get("dimensions_mm", part.get("error", "")))
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
