"""Six coding combinations through actual archive overlays, synthetic bytes only.

Pins are replaced with hashes of newly generated zero-filled fixtures. Production
hash/instruction/page validation is not weakened; no OEM input is opened.
"""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
spec = importlib.util.spec_from_file_location('coding_archive', TOOLS / 'archive-idrive-rootfs.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class CodingArchiveTests(unittest.TestCase):
    def test_six_real_archive_combinations_and_off_reversal_source_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='id6-coding-') as directory:
            base = Path(directory)
            root = base / 'root'
            def write(name, data):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            data = bytearray(0xDC000)
            patches = (archive.HMI_ID6L_PATCHES + (archive.HMI_CID_1440_PATCH,)
                       + archive.HMI_CID_TOUCH_PATCHES + (archive.HMI_DEVELOPER_MENU_PATCH,
                                                        archive.HMI_CAMERA_RVC_PATCH))
            for offset, expected, replacement in patches:
                data[offset:offset + len(expected)] = expected
            for key, size, offset in ((3, 0x96, 0xDB46C), (5, 0x96, 0xDAFAC),
                                      (7, 0x96, 0xDB2C0), (8, 0x32, 0xDA500),
                                      (9, 0x64, 0xDAEDC), (12, 0x32, 0xDA2B4), (15, 0x1E, 0xDA2F0)):
                struct.pack_into('<III', data, archive.HMI_CODING_DEFAULTS_INDEX_OFFSET + (key-1)*12,
                                 key, size, offset)
            registry = b'fixture:' + b';'.join(old for old, new in archive.HMI_VARIANTREGISTRY_F32_ASSET_PATHS) * 2
            index = b'\n'.join(b'alias: "' + new + b'"\nfile: "bmw/widgetasset/' + new + b'/widget.pbw"'
                               for old, new in archive.HMI_VARIANTREGISTRY_F32_ASSET_PATHS)
            write(archive.HMI_CODING_PATH, data)
            write(archive.HMI_VARIANTREGISTRY_PATH, registry)
            write(archive.HMI_VARIANTREGISTRY_INDEX_PATH, index)
            for old, new in archive.HMI_VARIANTREGISTRY_F32_ASSET_PATHS:
                write('opt/hmi/ID5/data/ro/bmw/widgetasset/' + new.decode() + '/widget.pbw', b'synthetic widget')
            packages = archive.GRAPHICS_STOP_PACKAGES | archive.GRAPHICS_RUN_PACKAGES
            write('opt/sys/etc/starter.cfg', ('<Starter><Environment><Number>4</Number><Value>/opt/hmi/lib</Value></Environment>' + ''.join(
                '<Package><Name>' + name + '</Name><RequestState>RUN</RequestState></Package>'
                for name in sorted(packages)) + '</Starter>').encode())
            write('etc/umass-enum.cfg', b'vendor=0x2239,device=0xf004,type=CDC\n')
            write('bin/start_usb.sh', b'-d omap5-xhci ioport=0x4a030000,irq=124,verbose=5 ')
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            pins = {'HMI_CODING_SHA256': hashlib.sha256(data).hexdigest(),
                    'HMI_VARIANTREGISTRY_SHA256': hashlib.sha256(registry).hexdigest()}
            with patch.multiple(archive, **pins):
                baseline = archive._hmi_coding_id6l_overlay(root, cid_1440=True, cid_touch=True)
                # ON followed by OFF verifies reversibility of the next fresh tar,
                # not an attempt to mutate an already-running guest.
                combinations = [(d, c, r) for d in (True, False)
                                for c, r in ((True, True), (False, True), (False, False))]
                for number, (developer, camera, resources) in enumerate(combinations):
                    with self.subTest(developer=developer, camera=camera, resources=resources):
                        output = base / f'fresh-{number}.tar.gz'
                        archive.archive_rootfs(root, output, compressed=True, emulator_profile='omap5-graphics',
                            hmi_coding_id6l=True, hmi_coding_cid_1440=True, hmi_coding_cid_touch=True,
                            hmi_coding_developer_menu=developer, hmi_coding_camera_rvc=camera,
                            hmi_variantregistry_f32=resources)
                        expected = baseline
                        if developer:
                            expected = archive._hmi_coding_developer_menu_overlay(expected)
                        if camera:
                            expected = archive._hmi_coding_camera_rvc_overlay(root, expected)
                        with tarfile.open(output) as tar:
                            self.assertEqual(tar.extractfile(archive.HMI_CODING_PATH).read(), expected)
                            self.assertEqual(tar.extractfile(archive.HMI_VARIANTREGISTRY_PATH).read(),
                                archive._hmi_variantregistry_f32_overlay(root) if resources else registry)
                            self.assertEqual(len([m for m in tar if m.name == archive.HMI_CODING_PATH]), 1)
                with self.assertRaisesRegex(RuntimeError, 'requires'):
                    archive.archive_rootfs(root, base / 'invalid.tar', compressed=False,
                        emulator_profile='omap5-graphics', hmi_coding_id6l=True, hmi_coding_camera_rvc=True)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
