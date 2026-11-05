"""Package the current, jointly verified V6 files without stale/debug assets.

Run after generar.py, verificar_tornillos.py, validar_stl.py, the distribution
drawing and exportar_3mf.py. This script uses the Python standard library.
It refuses to package a failed or stale verification report.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import struct
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
STLS = (
    '01_frontal_gato.stl', '02_frontal_mochi.stl',
    '03_cuerpo_sin_carga_magnetica.stl', '04_bandeja_bateria_y_GPS.stl',
    '05_soporte_altavoz.stl', '06_separador_interno_7_7mm.stl',
    '07_pulsador_inferior.stl', '08_pulsador_superior.stl',
    '09_prueba_pantalla.stl', '10_prueba_pulsadores.stl',
    '11_prueba_tuerca_M2.stl',
)
PROJECTS = ('TamaPoke_Gato_V6_Impresion.3mf',
            'TamaPoke_Mochi_V6_Impresion.3mf')
VIEWS = ('01_gato.png', '02_gato_frontal.png', '03_mochi.png',
         '04_trasera_sin_imanes.png', '05_distribucion_interior.png',
         '06_cotas_y_distribucion.png')
REPORTS = ('validacion_stl.json', 'validacion_mecanica.json',
           'validacion_tornillos.json', 'validacion_3mf.json')
SOURCE_SHA256 = 'a315cc7aecfcdb5409a6d39f24f9091f660b0391bbd7c62de32bbdd5933f0f8e'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(path.read_bytes())


def read_json(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))


def safe_file(relative):
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts,
            'Unsafe relative package path: '+str(relative))
    path = ROOT/relative
    require(path.is_file(), 'Missing package input: '+relative.as_posix())
    require(path.resolve().is_relative_to(ROOT.resolve()),
            'Input leaves package directory: '+relative.as_posix())
    return path


def png_metadata(path):
    """Read textual PNG metadata without introducing a Pillow dependency."""
    raw = path.read_bytes()
    require(raw[:8] == b'\x89PNG\r\n\x1a\n', 'Invalid PNG: '+path.name)
    text = {}
    offset = 8
    while offset+12 <= len(raw):
        length = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset+4:offset+8]
        payload = raw[offset+8:offset+8+length]
        require(len(payload) == length, 'Truncated PNG: '+path.name)
        if kind == b'tEXt':
            key, value = payload.split(b'\0', 1)
            text[key.decode('latin1')] = value.decode('latin1')
        elif kind == b'zTXt':
            key, value = payload.split(b'\0', 1)
            require(value[0] == 0, 'Unsupported PNG compression')
            text[key.decode('latin1')] = zlib.decompress(value[1:]).decode('latin1')
        elif kind == b'iTXt':
            key, rest = payload.split(b'\0', 1)
            compressed, method = rest[0], rest[1]
            language, rest = rest[2:].split(b'\0', 1)
            translated, value = rest.split(b'\0', 1)
            if compressed:
                require(method == 0, 'Unsupported PNG compression')
                value = zlib.decompress(value)
            text[key.decode('latin1')] = value.decode('utf-8')
        offset += length+12
        if kind == b'IEND':
            break
    return text


def validate_inputs(quick=False):
    report_names = tuple(n for n in REPORTS if not quick or n != 'validacion_tornillos.json')
    reports = {name: read_json(name) for name in report_names}
    for name, report in reports.items():
        require(report.get('pass') is True, 'Verification did not pass: '+name)
    stl = reports['validacion_stl.json']
    mechanical = reports['validacion_mecanica.json']
    hardware = reports.get('validacion_tornillos.json')
    project_report = reports['validacion_3mf.json']
    actual_stls = {p.name for p in (ROOT/'stl').glob('*.stl')}
    require(actual_stls == set(STLS), 'The STL directory does not match the V6 manifest')
    require(stl.get('part_count') == len(STLS), 'Wrong independent STL part count')
    rows = stl.get('parts', [])
    require({p.get('file') for p in rows} == set(STLS), 'Independent STL manifest is stale')
    current_hashes = {name: digest(safe_file('stl/'+name)) for name in STLS}
    for part in rows:
        require(part.get('pass') is True, 'Independent part failed: '+part['file'])
        require(part.get('sha256') == current_hashes[part['file']],
                'Independent STL verification is stale: '+part['file'])
    if hardware:
        require(hardware.get('stl_sha256') == current_hashes,
                'Hardware verification does not match the current STL files')
    require(mechanical.get('stl_sha256') == current_hashes,
            'Mechanical verification needs a current stl_sha256 manifest')
    require(len(mechanical.get('parts', [])) == len(STLS), 'Wrong mechanical part count')
    require({p.get('stl') for p in mechanical['parts']} == set(STLS),
            'Mechanical part manifest differs from V6')
    for row in mechanical.get('mechanical_checks', []):
        require(row['intersection_mm3'] <= row['allowed_mm3'],
                'Mechanical collision still exceeds its declared tolerance')
    require(not mechanical.get('failed_checks'), 'Unresolved mechanical checks')
    if hardware:
        require(not hardware.get('failed_checks'), 'Unresolved hardware checks')
        require(hardware.get('mechanical_report_sha256') == digest(ROOT/'validacion_mecanica.json'),
                'Hardware verification used an older mechanical report')
    sources = mechanical.get('source_files_sha256', {})
    require({'generar.py', 'cad_base.py', 'parametros.json'}.issubset(sources),
            'Mechanical report omits a generator input hash')
    for name, expected in sources.items():
        require(digest(safe_file(name)) == expected, 'Generator input changed after verification: '+name)
    original = read_json('auditoria/original.json')
    require(original['source_sha256'] == SOURCE_SHA256,
            'Unexpected original model provenance')
    require(digest(safe_file('referencias/TamaPoke_original.3mf')) == SOURCE_SHA256,
            'Original supplied 3MF bytes changed')
    require(mechanical.get('source_3mf_sha256') == SOURCE_SHA256,
            'Mechanical verification references another source 3MF')
    if not quick:
        require(mechanical.get('official_step_solids') == 666,
                'Mechanical verification does not use the complete reference STEP mesh')
    projects = project_report.get('projects', [])
    require({p.get('file') for p in projects} == set(PROJECTS), 'Wrong 3MF projects')
    shared = set(STLS[2:8])
    for project in projects:
        name = project['file']
        require(project.get('pass') is True and project.get('verified_mesh_roundtrip') is True,
                '3MF mesh roundtrip was not verified: '+name)
        require(project.get('units') == 'mm' and project.get('objects') == 7
                and project.get('print_instances') == 8 and project.get('duplicate_spacers') == 2,
                'Unexpected 3MF layout counts or units: '+name)
        require(digest(safe_file(name)) == project.get('sha256'), '3MF report is stale: '+name)
        front = STLS[0] if 'Gato' in name else STLS[1]
        instances = project.get('source_stls', [])
        require(len(instances) == 8 and {p['stl'] for p in instances} == shared|{front},
                '3MF instance list is incomplete: '+name)
        require(sum(p['stl'] == STLS[5] for p in instances) == 2,
                '3MF must print two internal spacers: '+name)
        for part in instances:
            require(part['stl_sha256'] == current_hashes[part['stl']],
                    '3MF contains an older STL: '+part['stl'])
        with zipfile.ZipFile(ROOT/name) as archive:
            require(archive.testzip() is None, '3MF ZIP CRC failed: '+name)
            manifest = json.loads(archive.read('Metadata/piezas_y_huellas.json'))
            require(manifest['instances'] == instances, '3MF internal manifest differs from report')
    view_names = (*VIEWS[:5], '07_perfil_redondo.png') if quick else VIEWS
    for name in view_names:
        path = safe_file('vistas/'+name)
        metadata = png_metadata(path)
        if name != VIEWS[-1]:
            require(path.stat().st_mtime_ns >= (ROOT/'validacion_mecanica.json').stat().st_mtime_ns,
                    'Render predates the current verified assembly: '+name)
        else:
            require('Description' in metadata, 'Distribution drawing lacks input metadata')
            description = json.loads(metadata['Description'])
            inputs = description.get('input_sha256', {})
            require('parametros.json' in inputs
                    and all('stl/'+part in inputs for part in STLS[:3]),
                    'Distribution drawing omits geometry input hashes')
            for relative, expected in inputs.items():
                require(digest(safe_file(relative)) == expected,
                        'Distribution drawing is stale: '+relative)
    blend = safe_file('tamapoke_v6_montaje.blend')
    # Blender 5 can use a compressed Zstandard file rather than a raw header.
    require(blend.stat().st_size > 1_000_000, 'Editable Blender assembly is unexpectedly small')
    require(blend.stat().st_mtime_ns >= (ROOT/'validacion_mecanica.json').stat().st_mtime_ns,
            'Blender assembly predates current geometry verification')
    return reports, current_hashes


def file_lists(quick=False):
    report_names = tuple(n for n in REPORTS if not quick or n != 'validacion_tornillos.json')
    view_names = (*VIEWS[:5], '07_perfil_redondo.png') if quick else VIEWS
    compact = ['LEEME.md', 'parametros.json', *report_names, *PROJECTS,
               'referencias/medidas_bateria_gps.json',
               *('stl/'+name for name in STLS),
               *('vistas/'+name for name in view_names)]
    full = compact+[
        'tamapoke_v6_montaje.blend', 'generar.py', 'actualizar_domo.py', 'cad_base.py',
        'inspeccionar.py', 'validar_stl.py', 'verificar_tornillos.py',
        'exportar_3mf.py', 'empaquetar.py',
        'auditoria/dibujar_distribucion.py', 'auditoria/original.json',
        'auditoria/original_inspeccion_independiente.json',
        'auditoria/registro_pantalla.json', 'auditoria/step_parts.json',
        'auditoria/step_measurements_independent.json',
        'referencias/TamaPoke_original.3mf', 'referencias/mallas_originales.npz',
        'referencias/step_mesh_native.npz',
    ]
    return compact, full


def package(filename, relative_paths, verified_stls, quick=False):
    require(len(relative_paths) == len(set(relative_paths)), 'Duplicate package path')
    files = {relative: safe_file(relative).read_bytes() for relative in relative_paths}
    manifest = {
        'revision': read_json('parametros.json')['revision'],
        'units': 'mm', 'source_3mf_sha256': SOURCE_SHA256,
        'verification_scope': 'quick' if quick else 'full CAD checks',
        'hardware_sweep_rerun': not quick,
        'scope': 'Personal adaptation; CAD and STL checks do not certify physical fit or GPS reception.',
        'stl_sha256': verified_stls,
        'files': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())},
        'manifest_note': 'Hashes cover every payload file listed here; this manifest does not hash itself.',
    }
    files['MANIFIESTO_ARCHIVOS.json'] = (json.dumps(manifest, indent=2, ensure_ascii=False)+'\n').encode('utf-8')
    descriptor, tempname = tempfile.mkstemp(prefix=filename+'.', suffix='.tmp', dir=ROOT)
    os.close(descriptor)
    temp = Path(tempname)
    try:
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
        with zipfile.ZipFile(temp) as archive:
            require(archive.testzip() is None, 'ZIP CRC failed: '+filename)
            require(set(archive.namelist()) == set(files), 'ZIP file list differs from package manifest')
            for name, expected in files.items():
                require(sha(archive.read(name)) == sha(expected), 'ZIP byte roundtrip failed: '+name)
        target = ROOT/filename
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return {'file': filename, 'bytes': target.stat().st_size, 'sha256': digest(target),
            'file_count': len(files), 'crc_verified': True, 'all_bytes_sha256_verified': True,
            'payload_files': sorted(files)}


def main(check_only=False, quick=False):
    reports, hashes = validate_inputs(quick)
    compact, full = file_lists(quick)
    for relative in full:
        safe_file(relative)
    if check_only:
        print('PACKAGE_INPUTS_PASS', len(STLS), 'STL,', len(PROJECTS), '3MF')
        return
    packages = [package('TamaPoke_V6_STL_3MF.zip', compact, hashes, quick),
                package('TamaPoke_V6_Completo.zip', full, hashes, quick)]
    delivery = {
        'pass': True, 'revision': read_json('parametros.json')['revision'],
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_3mf_sha256': SOURCE_SHA256,
        'assembly_cat_dimensions_mm': reports['validacion_mecanica.json']['assembly_cat_dimensions_mm'],
        'assembly_mochi_dimensions_mm': reports['validacion_mecanica.json']['assembly_mochi_dimensions_mm'],
        'stl_sha256': hashes,
        'verification_scope': 'quick' if quick else 'full CAD checks',
        'hardware_sweep_rerun': not quick,
        'verification_reports_sha256': {name: digest(ROOT/name) for name in reports},
        'editable_blend_sha256': digest(ROOT/'tamapoke_v6_montaje.blend'),
        'projects_3mf_sha256': {name: digest(ROOT/name) for name in PROJECTS},
        'packages': packages,
        'physical_fit_certified': False,
    }
    (ROOT/'entrega.json').write_text(json.dumps(delivery, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'pass': True, 'packages': [{k: v for k, v in p.items() if k != 'payload_files'}
                                              for p in packages]}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Validate inputs without creating ZIPs')
    parser.add_argument('--quick', action='store_true', help='Package minimum current checks; omit old hardware report and drawing06')
    args = parser.parse_args()
    main(args.check_only, args.quick)
