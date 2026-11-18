from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image
from assets import AssetCatalog, AssetError, discover_roots, reference_png


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def image(self, relative, mode="RGB"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new(mode, (128, 128), "gray").save(path)
        return path

    def xml(self, folder, mappings):
        path = self.root / folder / "config.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        root = ET.Element("record")
        listing = ET.SubElement(root, "list", id="maps")
        for source, target in mappings:
            ET.SubElement(listing, "record", {"from": source, "to": target})
        path.write_bytes(ET.tostring(root, encoding="utf-8"))
        return path

    def test_face_uses_xml_when_filename_is_not_player_id(self):
        face = self.image("faces/photos/player_photo.jpg")
        self.xml("faces", [("photos/player_photo", "graphics/pictures/person/123/portrait")])
        catalog = AssetCatalog(self.root / "faces")
        self.assertEqual(catalog.face("123"), (face, "123"))
        self.assertEqual(catalog.suggestions()[0]["faces"], 1)

    def test_regen_prefix_is_read_from_existing_mapping(self):
        face = self.image("face.png")
        self.xml(".", [("face", "graphics/pictures/person/r-123/portrait")])
        self.assertEqual(AssetCatalog(self.root).face("123"), (face, "r-123"))

    def test_kit_variant_uses_team_kits_mapping_not_logos(self):
        home = self.image("kits/manchester_h.png")
        away = self.image("kits/manchester_a.png")
        self.image("kits/logo.png")
        self.xml("kits", [("manchester_h", "graphics/pictures/team/680/kits/home"),
                          ("manchester_a", "graphics/pictures/team/680/kits/away"),
                          ("logo", "graphics/pictures/club/680/logo")])
        catalog = AssetCatalog(self.root)
        self.assertEqual(catalog.kit("680", "home"), home)
        self.assertEqual(catalog.kit("680", "away"), away)
        with self.assertRaises(AssetError):
            catalog.kit("680", "third")

    def test_numeric_fallback_and_subdirectories(self):
        face = self.image("nested/123.webp")
        kit = self.image("nested/680_away.jpg")
        catalog = AssetCatalog(self.root)
        self.assertEqual(catalog.face("123")[0], face)
        self.assertEqual(catalog.kit("680", "away"), kit)
        self.assertIn("ID 파일", catalog.suggestions()[0]["basis"])

    def test_plain_numeric_kit_is_home_only(self):
        self.image("680.png")
        catalog = AssetCatalog(self.root)
        self.assertEqual(catalog.kit("680").name, "680.png")
        with self.assertRaises(AssetError):
            catalog.kit("680", "away")

    def test_duplicate_kits_are_sampled_without_blocking_and_preview_lists_all(self):
        first = self.image("packA/shirt.png")
        second = self.image("packB/shirt.png")
        for name in ("packA", "packB"):
            self.xml(name, [("shirt", "graphics/pictures/team/680/kits/home")])
        catalog = AssetCatalog(self.root)
        with patch("assets.random.choice", return_value=second) as choose:
            self.assertEqual(catalog.kit("680"), second)
            self.assertEqual(set(choose.call_args.args[0]), {first, second})
        self.assertEqual(catalog.kit_candidates("680"), [first, second])

    def test_generated_pack_is_not_discovered_as_source(self):
        self.image("output/680.png")
        self.xml("output", [("680", "graphics/pictures/person/680/portrait")])
        (self.root / "output" / ".fm-face-owner").write_text("managed")
        catalog = AssetCatalog(self.root)
        self.assertEqual(catalog.suggestions(), [])

    def test_conflicting_packs_are_not_chosen_arbitrarily(self):
        for name in ("packA", "packB"):
            self.image(f"{name}/photo.png")
            self.xml(name, [("photo", "graphics/pictures/person/123/portrait")])
        with self.assertRaisesRegex(AssetError, "후보 2개") as error:
            AssetCatalog(self.root).face("123")
        self.assertEqual(set(error.exception.candidates), {self.root / name / "photo.png" for name in ("packA", "packB")})
        self.assertEqual(len(AssetCatalog(self.root).suggestions()), 2)
        self.assertEqual(AssetCatalog(self.root / "packA").face("123")[0].parent.name, "packA")

    def test_duplicate_records_for_same_file_are_not_a_conflict(self):
        face = self.image("face.png")
        mapping = ("face", "graphics/pictures/person/123/portrait")
        self.xml(".", [mapping, mapping])
        self.assertEqual(AssetCatalog(self.root).face("123")[0], face)

    def test_missing_mapping_is_not_replaced_with_unrelated_numeric_file(self):
        self.image("123.png")
        self.xml(".", [("missing_photo", "graphics/pictures/person/123/portrait")])
        with self.assertRaisesRegex(AssetError, "원본 이미지가 없습니다"):
            AssetCatalog(self.root).face("123")

    def test_3d_texture_is_excluded_from_2d_lookup(self):
        self.image("680.png")
        self.xml(".", [("680", "graphics/pictures/team/680/kit_textures/home")])
        catalog = AssetCatalog(self.root)
        self.assertEqual(catalog.textures, 1)
        self.assertEqual(catalog.suggestions(), [])
        with self.assertRaises(AssetError):
            catalog.kit("680")

    def test_output_pack_is_excluded(self):
        self.image("generated/123.png")
        self.xml("generated", [("123", "graphics/pictures/person/123/portrait")])
        catalog = AssetCatalog(self.root, exclude=[self.root / "generated"])
        with self.assertRaises(AssetError):
            catalog.face("123")

    def test_mapping_cannot_escape_selected_root(self):
        self.image("outside.png")
        self.xml("pack", [("../outside", "graphics/pictures/person/123/portrait")])
        with self.assertRaises(AssetError):
            AssetCatalog(self.root / "pack").face("123")
        # Selecting the common graphics root explicitly permits this layout.
        self.assertEqual(AssetCatalog(self.root).face("123")[0], self.root / "outside.png")

    def test_symlink_mapping_cannot_escape_selected_root(self):
        target = self.image("outside.png")
        pack = self.root / "pack"
        pack.mkdir()
        try:
            (pack / "face.png").symlink_to(target)
        except OSError:
            self.skipTest("Symlinks unavailable on this platform")
        self.xml("pack", [("face", "graphics/pictures/person/123/portrait")])
        with self.assertRaises(AssetError):
            AssetCatalog(pack).face("123")

    def test_windows_slashes_and_uppercase_extension(self):
        image = self.image("pictures/photo.PNG")
        self.xml(".", [("pictures\\photo", "graphics/pictures/person/123/portrait")])
        self.assertEqual(AssetCatalog(self.root).face("123")[0], image)

    def test_malformed_xml_does_not_leave_partial_mappings(self):
        self.image("photo.png")
        (self.root / "config.xml").write_text('<record><record from="photo" to="graphics/pictures/person/123/portrait"/><broken>')
        catalog = AssetCatalog(self.root)
        self.assertTrue(catalog.warnings)
        self.assertFalse(catalog.faces)

    def test_dtd_is_rejected_without_expanding_entities(self):
        (self.root / "config.xml").write_text('<!DOCTYPE record [<!ENTITY name "face">]><record/>')
        self.assertTrue(AssetCatalog(self.root).warnings)

    def test_jpeg_reference_is_encoded_as_real_png(self):
        source = self.image("photo.jpg")
        staged = reference_png(source)
        with Image.open(BytesIO(staged)) as image:
            self.assertEqual(image.format, "PNG")
            image.load()

    def test_discovery_includes_onedrive_and_custom_graphics_not_whole_home(self):
        custom = self.root / "custom-graphics"
        default = self.root / "user/Documents/Sports Interactive/Football Manager 27/graphics"
        cloud = self.root / "cloud/Documents/Sports Interactive/Football Manager 27/graphics"
        for folder in (custom, default, cloud):
            folder.mkdir(parents=True)
        roots = discover_roots({"graphics_root": str(custom)}, home=self.root / "user", environ={"OneDrive": str(self.root / "cloud")})
        self.assertEqual(set(roots), {custom, default, cloud})
        self.assertNotIn(self.root / "user", roots)

    def test_cancelled_search_stops(self):
        import threading
        stop = threading.Event()
        stop.set()
        with self.assertRaisesRegex(AssetError, "취소"):
            AssetCatalog(self.root, stop=stop)


if __name__ == "__main__":
    unittest.main()
