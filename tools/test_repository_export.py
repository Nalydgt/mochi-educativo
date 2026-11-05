"""Pure preflight checks; never invokes an export copy, Git, NAS or a device."""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import sys
import unittest

SPEC = importlib.util.spec_from_file_location("mochi_repository_export", Path(__file__).with_name("Prepare-MochiRepository.py"))
export = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = export
SPEC.loader.exec_module(export)


def entry(body, path="web/src/example.ts"):
    return export.Entry(Path(__file__), "test", "example", path, body.encode())


class RepositoryPreflight(unittest.TestCase):
    def test_only_explicit_source_paths_are_allowed(self):
        self.assertTrue(export.allowed(PurePosixPath("src/components/Test.tsx"), "web"))
        self.assertTrue(export.allowed(PurePosixPath("assets/mochi-native/body.rgb565a8"), "firmware"))
        self.assertTrue(export.allowed(PurePosixPath("components/microlink/ESPHOME-LICENSE"), "firmware"))
        self.assertTrue(export.allowed(PurePosixPath("components/microlink/x25519-license.txt"), "firmware"))
        self.assertTrue(export.allowed(PurePosixPath("components/lib/algorithm.hh"), "firmware"))
        self.assertTrue(export.allowed(PurePosixPath("peluqo-v13/requirements.txt"), "hardware"))
        self.assertFalse(export.allowed(PurePosixPath("sdkconfig"), "firmware"))
        self.assertFalse(export.allowed(PurePosixPath("capture.png"), "web"))
        self.assertFalse(export.allowed(PurePosixPath("gato-v2/stl/mesh.stl"), "hardware"))
        self.assertFalse(export.allowed(PurePosixPath("repository-template/unreviewed.json"), "tools"))
        self.assertIn("config/asr-small.json", export.ROOT_SOURCES)
        self.assertIn(".gitattributes", export.ROOT_SOURCES)
        self.assertFalse(any("MEMORY" in path or "USER" in path for path in export.ROOT_SOURCES))
        self.assertEqual(export.TEMPLATES["nas.example.json"], "config/nas.example.json")
        self.assertEqual(export.WEB_SOURCES, {"src/data/peluqo.ts", "fixtures/reviewed-mission.ts"})

    def test_traversal_and_drive_paths_are_rejected(self):
        for path in ("../secrets", "/absolute", "C:/outside", "web/../../outside", "web\\outside"):
            with self.assertRaises(export.ExportError):
                export.safe_relative(path)

    def test_authorized_layout_adjustments_are_exact_and_do_not_change_urls(self):
        body = b"MOCHI=ROOT.parent/'tamagochi 2'\nurl='https://peluqo-mundos.vercel.app'\n"
        result, changes = export.transform("web/tools/pilot.py", body)
        self.assertIn(b"MOCHI=ROOT.parent\n", result)
        self.assertIn(b"https://peluqo-mundos.vercel.app", result)
        self.assertTrue(changes)
        self.assertEqual(export.transform("web/src/other.py", body), (body, ()))
        voice = b"device_file = ROOT.parent / 'peluqo-mundos/.runtime/device.json'\n"
        self.assertIn(b"ROOT / 'web/.runtime/device.json'", export.transform("tools/Check-MochiLessonVoice.py", voice)[0])
        build = b"root=Path(__file__).resolve().parents[1]\nwith (root/'.runtime/pilot-build.log').open('w') as log: pass\n"
        adjusted = export.transform("web/tools/build-pilot.py", build)[0]
        self.assertLess(adjusted.find(b"mkdir("), adjusted.find(b"with (root"))
        self.assertEqual(export.transform("web/tools/build-pilot.py", adjusted)[0], adjusted)

    def test_known_credentials_and_real_provider_shapes_block_even_with_file_approval(self):
        configured = b"configured-value-for-preflight-only"
        item = entry(configured.decode())
        approval = [{"path": item.destination, "sha256": hashlib.sha256(item.data).hexdigest(), "reason": "synthetic_in_process_test"}]
        self.assertTrue(export.scan([item], {configured}, approval)["blocked"])
        provider = "sk-proj-" + "Ab8mP2qR9" * 5
        self.assertTrue(export.scan([entry(provider)], set())["blocked"])
        local_password = "".join(("Local", "Database", "Credential42"))
        local_dsn = "postgresql" + "://operator:" + local_password + "@localhost:5432/app"
        self.assertTrue(export.scan([entry(local_dsn)], set())["blocked"])

    def test_manifest_hashes_final_lf_text_and_keeps_binary_bytes_intact(self):
        original = b"first line\r\nsecond line\r\n"
        expected = b"first line\nsecond line\n"
        prepared, changes = export.normalize_lf("firmware/main/example.c", original)
        self.assertEqual(prepared, expected)
        self.assertEqual(changes, ("normalize_lf",))
        item = export.Entry(Path(__file__), "test", "source.c", "firmware/main/example.c", prepared, changes)
        result = export.manifest([item], export.Counter(), {"blocked": False, "findings": [], "portabilityReferences": []})
        self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertNotEqual(result["files"][0]["sha256"], hashlib.sha256(original).hexdigest())
        binary = b"\x89PNG\r\n\x00\xff\r\n"
        self.assertEqual(export.normalize_lf("firmware/assets/body.png", binary), (binary, ()))
        self.assertEqual(export.normalize_lf("firmware/assets/body.rgb565a8", binary), (binary, ()))
        self.assertEqual(export.normalize_lf("firmware/main/example.c", prepared), (prepared, ()))
        self.assertEqual(export.normalize_lf("firmware/components/microlink/ESPHOME-LICENSE", original), (expected, ("normalize_lf",)))

    def test_export_includes_exact_reviewed_web_import_dependencies(self):
        root = export.ROOT
        web = root / "web" if (root / "web").is_dir() else root.parent / "peluqo-mundos"
        entries, _ = export.collect(root, web)
        paths = {item.destination for item in entries}
        self.assertIn("web/src/data/peluqo.ts", paths)
        self.assertIn("web/fixtures/reviewed-mission.ts", paths)
        self.assertEqual({path for path in paths if path.startswith("web/fixtures/")}, {"web/fixtures/reviewed-mission.ts"})
        self.assertIn(b"@/data/peluqo", next(item.data for item in entries if item.destination == "web/src/routes/lab.tsx"))
        self.assertIn(b"../../fixtures/reviewed-mission", next(item.data for item in entries if item.destination == "web/src/test/education.test.tsx"))

    def test_literal_review_is_bound_to_full_file_and_only_literal_rule(self):
        value = "FictionalPasswordForPreflight42"
        item = entry(f"password={chr(34)}{value}{chr(34)}\n")
        first = export.scan([item], set())
        self.assertTrue(first["blocked"])
        approval = [{"path": item.destination, "sha256": hashlib.sha256(item.data).hexdigest(), "reason": "synthetic_in_process_test"}]
        self.assertFalse(export.scan([item], set(), approval)["blocked"])
        modified = entry(item.data.decode() + "// changed file\n")
        self.assertTrue(export.scan([modified], set(), approval)["blocked"])
        private_key = entry("-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5)
        self.assertTrue(export.scan([private_key], set(), approval)["blocked"])

    def test_blocked_plan_never_creates_destination(self):
        path = export.ROOT / ".runtime/repository-export/preflight-must-not-create"
        self.assertFalse(path.exists())
        with self.assertRaises(export.ExportError):
            export.write_export([], {}, {"blocked": True}, path)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
