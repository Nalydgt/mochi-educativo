"""Inspect actual exported binary STL files, independently of Blender.

Run without arguments to inspect every STL in this revision's stl/ directory,
or pass explicit STL paths. Requires Python and NumPy. Writes validacion_stl.json
even when a file is invalid. Front/body checks use preserved case XY and bed
Z offsets; the buttons use their prescribed rotated print orientation.
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
# Design datum supplied independently of the mesh generator: the new domed
# body retains assembly XY and is translated +37 mm onto its flat rear foot.
BODY_PRINT_TRANSLATION_MM = 37.0
EXPECTED_V6_FILES = {
    "01_frontal_gato.stl", "02_frontal_mochi.stl",
    "03_cuerpo_sin_carga_magnetica.stl", "04_bandeja_bateria_y_GPS.stl",
    "05_soporte_altavoz.stl", "06_separador_interno_7_7mm.stl",
    "07_pulsador_inferior.stl", "08_pulsador_superior.stl",
    "09_prueba_pantalla.stl", "10_prueba_pulsadores.stl",
    "11_prueba_tuerca_M2.stl",
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


def pocket_hex_void_check(sections, label, xy, pocket):
    """Probe an AF4 M2 nut envelope, including corners, within the AF4.2 pocket.

    The corrected primitive rotation cancels Blender's +30 degree vertex phase,
    leaving one vertex radial and a flat parallel to each loading-slot wall.
    """
    angle = np.arctan2(xy[1], xy[0])
    radius = 4.0 / (2 * np.cos(np.pi / 6))
    vertices = np.array([
        (radius * np.cos(angle + j * np.pi / 3),
         radius * np.sin(angle + j * np.pi / 3)) for j in range(6)
    ])
    heights = (pocket[0] + 0.2, (pocket[0] + pocket[1]) / 2, pocket[1] - 0.1)
    failures = []
    for edge in range(6):
        for fraction in np.linspace(0, 1, 13, endpoint=False):
            outer = vertices[edge] * (1 - fraction) + vertices[(edge + 1) % 6] * fraction
            for band in (0.25, 0.5, 0.75, 0.99):
                point = np.array(xy) + band * outer
                cuts = sections.intersections(point)
                for height in heights:
                    if np.sum(cuts < height) % 2:
                        failures.append({"xy": point.tolist(), "z_mm": height,
                                         "intersections_z_mm": cuts.tolist()})
    return {
        "label": label,
        "center_xy_mm": list(xy),
        "nut_across_flats_mm": 4.0,
        "first_vertex_angle_degrees": float(np.rad2deg(angle)),
        "sample_count": 936,
        "sample_heights_z_mm": list(heights),
        "failed_samples": failures,
        "pass": not failures,
    }


def nut_loading_corridor_check(sections, label, xy, pocket):
    """Probe the AF4 nut envelope at seven stations along its inward entry.

    The nominal 1.6 mm nut is lowered by 0.05 mm from its loaded shoulder
    contact while sliding; three heights stay 0.05 mm inside its two faces.
    These are samples of the serialized plastic mesh, not an exhaustive sweep.
    """
    angle = np.arctan2(xy[1], xy[0])
    inward = -np.array((np.cos(angle), np.sin(angle)))
    radius = 4.0 / (2 * np.cos(np.pi / 6))
    vertices = np.array([
        (radius * np.cos(angle + j * np.pi / 3),
         radius * np.sin(angle + j * np.pi / 3)) for j in range(6)
    ])
    distances = np.linspace(0.0, 6.0, 7)
    heights = (pocket[1] - 1.6, pocket[1] - 0.85, pocket[1] - 0.1)
    failures = []
    for distance in distances:
        center = np.array(xy) + distance * inward
        for edge in range(6):
            for fraction in np.linspace(0, 1, 13, endpoint=False):
                outer = vertices[edge] * (1 - fraction) + vertices[(edge + 1) % 6] * fraction
                for band in (0.25, 0.5, 0.75, 0.99):
                    point = center + band * outer
                    cuts = sections.intersections(point)
                    for height in heights:
                        if np.sum(cuts < height) % 2:
                            failures.append({"distance_inward_mm": float(distance),
                                             "xy": point.tolist(), "z_mm": height,
                                             "intersections_z_mm": cuts.tolist()})
    return {
        "label": label,
        "center_xy_mm": list(xy),
        "nut_across_flats_mm": 4.0,
        "nut_height_mm": 1.6,
        "loading_gap_below_shoulder_mm": 0.05,
        "sample_distances_inward_mm": distances.tolist(),
        "sample_heights_z_mm": list(heights),
        "sample_count": 936 * len(distances),
        "failed_samples": failures,
        "pass": not failures,
    }


def inspect(path, quick=False):
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
        # The undeformed source front has radius 30 mm. A tip beyond Y31
        # on each side can only belong to the integrated ear deformation.
        face_centers = triangles.mean(axis=1)
        body_faces = np.flatnonzero(face_centers[:, 1] < 0.0)
        ear_masks = [
            (face_centers[:, 0] < -6.0) & (face_centers[:, 1] > 31.0),
            (face_centers[:, 0] > 6.0) & (face_centers[:, 1] > 31.0),
        ]
        result["ear_tip_region"] = {"minimum_y_mm": 31.0, "minimum_abs_x_mm": 6.0}
        result["ear_tip_triangles"] = [int(mask.sum()) for mask in ear_masks]
        result["ears_connected_to_body"] = bool(
            len(body_faces) and all(
                mask.any() and np.all(face_roots[mask] == face_roots[body_faces[0]])
                for mask in ear_masks
            )
        )
    if path.name == "02_frontal_mochi.stl":
        xy_size = maximum[:2] - minimum[:2]
        maximum_radius = float(np.linalg.norm(vertices[:, :2], axis=1).max())
        result["mochi_outline"] = {
            "nominal_outer_diameter_mm": 61.6,
            "bounds_xy_mm": [minimum[:2].tolist(), maximum[:2].tolist()],
            "maximum_xy_radius_mm": maximum_radius,
            "round_source_extent_preserved": bool(
                np.all(np.abs(xy_size - 61.6) < 0.1)
                and maximum_radius <= 30.85
            ),
        }
    if path.name in {"07_pulsador_inferior.stl", "08_pulsador_superior.stl"}:
        base = vertices[vertices[:, 2] <= minimum[2] + END_SECTION_EPSILON_MM]
        tip = vertices[vertices[:, 2] >= maximum[2] - END_SECTION_EPSILON_MM]
        base_extent = base[:, :2].max(axis=0) - base[:, :2].min(axis=0)
        tip_extent = tip[:, :2].max(axis=0) - tip[:, :2].min(axis=0)
        result["button_print_orientation"] = {
            "end_section_epsilon_mm": END_SECTION_EPSILON_MM,
            "base_extent_xy_mm": base_extent.tolist(),
            "upper_tip_extent_xy_mm": tip_extent.tolist(),
            "stem_face_on_bed_nose_up": bool(
                np.all((base_extent >= 2.2) & (base_extent <= 2.6))
                and np.all(np.abs(np.sort(tip_extent) - (1.0, 1.6)) < 0.1)
                and np.all((maximum[:2] - minimum[:2]) >= 4.3)
            ),
        }
    if path.name == "03_cuerpo_sin_carga_magnetica.stl":
        sections = VerticalSections(triangles)
        shift = BODY_PRINT_TRANSLATION_MM
        pocket = (shift - 23.2, shift - 21.3)
        lip = (shift - 21.3, shift - 19.3)
        contact_faces = np.all(
            np.abs(triangles[:, :, 2]) < END_SECTION_EPSILON_MM, axis=1
        )
        contact_area = float(areas[contact_faces].sum())
        base_vertices = vertices[
            np.abs(vertices[:, 2]) < END_SECTION_EPSILON_MM
        ]
        base_extent = (base_vertices[:, :2].max(axis=0)
                       - base_vertices[:, :2].min(axis=0)) if len(base_vertices) else np.zeros(2)
        result["rear_print_base"] = {
            "assembly_to_print_translation_z_mm": shift,
            "expected_body_dimensions_mm": [62.0, 62.0, 37.0],
            "expected_flat_foot_diameter_mm": 20.0,
            "serialized_contact_triangle_count": int(contact_faces.sum()),
            "serialized_contact_area_mm2": contact_area,
            "serialized_contact_bounds_xy_mm": base_extent.tolist(),
            "support_required_on_outer_dome": True,
            "pass": bool(
                np.all(np.abs((maximum - minimum) - (62.0, 62.0, 37.0)) < 0.1)
                and 310.0 <= contact_area <= 316.0
                and np.all(np.abs(base_extent - 20.0) < 0.05)
            ),
        }
        result["sampled_nut_shoulders"] = [] if quick else [
            shoulder_check(sections, "M2 tray " + str(index), xy, 2.4, 4.2,
                           lip, pocket)
            for index, xy in enumerate(((-18.5, 5.0), (20.5, 5.0)), 1)
        ]
        result["sampled_nut_pocket_void"] = [] if quick else [
            pocket_hex_void_check(sections, "M2 tray " + str(index), xy, pocket)
            for index, xy in enumerate(((-18.5, 5.0), (20.5, 5.0)), 1)
        ]
        result["sampled_nut_loading_corridor"] = [] if quick else [
            nut_loading_corridor_check(sections, "M2 tray " + str(index), xy, pocket)
            for index, xy in enumerate(((-18.5, 5.0), (20.5, 5.0)), 1)
        ]
    if path.name == "11_prueba_tuerca_M2.stl" and not quick:
        sections = VerticalSections(triangles)
        result["sampled_nut_shoulders"] = [
            shoulder_check(sections, "M2 coupon", (0.0, 0.0),
                           2.4, 4.2, (4.0, 6.0), (2.1, 4.0))
        ]
        result["sampled_nut_pocket_void"] = [
            pocket_hex_void_check(sections, "M2 coupon", (0.0, 0.0), (2.1, 4.0))
        ]
        result["sampled_nut_loading_corridor"] = [
            nut_loading_corridor_check(sections, "M2 coupon", (0.0, 0.0), (2.1, 4.0))
        ]
    zero_fields = [
        "boundary_edges", "non_manifold_edges", "non_manifold_vertices",
        "orientation_mismatch_edges", "duplicate_faces", "degenerate_triangles",
    ]
    result["pass"] = bool(
        all(result[key] == 0 for key in zero_fields)
        and components == 1 and volume > 0
        and abs(result["minimum_z_mm"]) < BED_EPSILON_MM
        and result.get("ears_connected_to_body", True)
        and result.get("button_print_orientation", {}).get("stem_face_on_bed_nose_up", True)
        and result.get("mochi_outline", {}).get("round_source_extent_preserved", True)
        and result.get("rear_print_base", {}).get("pass", True)
        and all(test["pass"] for test in result.get("sampled_nut_shoulders", []))
        and all(test["pass"] for test in result.get("sampled_nut_pocket_void", []))
        and all(test["pass"] for test in result.get("sampled_nut_loading_corridor", []))
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true",
                        help="Minimum mesh, dimensions and print-base checks; skip sampled nut pockets/loading")
    parser.add_argument("files", nargs="*", type=Path, help="Explicit binary STL paths")
    args = parser.parse_args()
    paths = args.files or sorted((ROOT / "stl").glob("*.stl"))
    parts = []
    for path in paths:
        try:
            parts.append(inspect(path, quick=args.quick))
        except (OSError, ValueError, struct.error) as error:
            parts.append({"file": path.name, "pass": False, "error": str(error)})
    names = {path.name for path in paths}
    manifest_checked = not bool(args.files)
    missing = sorted(EXPECTED_V6_FILES - names) if manifest_checked else []
    unexpected = sorted(names - EXPECTED_V6_FILES) if manifest_checked else []
    report = {
        "method": "Independent read of binary STL; exact serialized-vertex welding; edge incidence and direction; edge-connected surface components; vertex fans; triangle areas; duplicate faces; signed volume; bed position; SHA256. Domed rear: measured dimensions and actual planar contact triangles on the print bed. Nut-retaining shoulders sampled on three annular bands at 36 angles; AF4 hexagonal nut pocket occupancy sampled at 936 points over three heights, including corners; straight inward loading corridor sampled at seven stations. Not a physical fit or global self-intersection test.",
        "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "validation_mode": "quick" if args.quick else "full",
        "nut_pocket_and_loading_samples_run": not args.quick,
        "units": "mm",
        "area_epsilon_mm2": AREA_EPSILON_MM2,
        "bed_epsilon_mm": BED_EPSILON_MM,
        "end_section_epsilon_mm": END_SECTION_EPSILON_MM,
        "parts": parts,
        "part_count": len(parts),
        "directory_manifest_checked": manifest_checked,
        "expected_v6_files": sorted(EXPECTED_V6_FILES),
        "missing_files": missing,
        "unexpected_files": unexpected,
        "pass": bool(parts) and not missing and not unexpected and all(part["pass"] for part in parts),
    }
    if args.quick:
        report["method"] = "Minimum independent read of binary STL: exact serialized-vertex welding, closed/oriented edge incidence, edge-connected surface components, vertex fans, triangle areas, duplicate faces, signed volume, bed position, dimensions and SHA256. Actual planar rear-foot contact triangles measured. Nut-pocket, loading-corridor and component interference sweeps were not run. Not a physical fit or global self-intersection test."
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
