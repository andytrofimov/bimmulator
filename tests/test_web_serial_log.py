import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from web_serial_log import MAX_LIMIT, SerialLogTail


class SerialLogTailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "serial"
        self.tail = SerialLogTail(self.path)

    def append(self, data):
        with self.path.open("ab") as stream:
            stream.write(data)

    def test_tail_append_and_independent_cursors(self):
        self.path.write_bytes(b"0123456789")
        first = self.tail.read(limit=4)
        self.assertEqual(first["text"], "6789")
        self.assertFalse(first["reset"])
        self.assertTrue(first["available"])
        self.append(b"abcde")
        a = self.tail.read(first["cursor"], limit=2)
        b = self.tail.read(first["cursor"], limit=5)
        self.assertEqual(a["text"], "ab")
        self.assertEqual(b["text"], "abcde")
        self.assertEqual(self.tail.read(a["cursor"])["text"], "cde")
        self.assertEqual(self.tail.read(b["cursor"])["text"], "")

    def test_utf8_split_and_bad_bytes(self):
        self.path.write_bytes(b"A\xe2")
        first = self.tail.read()
        self.assertEqual(first["text"], "A")
        self.append(b"\x82\xac\x00\x1b\xff\r\n\t")
        result = self.tail.read(first["cursor"], limit=1)
        self.assertEqual(result["text"], "")
        result = self.tail.read(result["cursor"])
        self.assertEqual(result["text"], "€\\x00\\x1b\\xff\r\n\t")

    def test_rotation_symlink_and_truncate(self):
        one, two = self.root / "one", self.root / "two"
        one.write_bytes(b"first long content")
        two.write_bytes(b"second")
        try:
            self.path.symlink_to(one)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        first = self.tail.read()
        self.path.unlink()
        self.path.symlink_to(two)
        second = self.tail.read(first["cursor"])
        self.assertTrue(second["reset"])
        self.assertEqual(second["text"], "second")
        two.write_bytes(b"x")
        third = self.tail.read(second["cursor"])
        self.assertTrue(third["reset"])
        self.assertEqual(third["text"], "x")
        two.write_bytes(b"replacement longer than before")
        fourth = self.tail.read(third["cursor"])
        self.assertTrue(fourth["reset"])
        self.assertEqual(fourth["text"], "replacement longer than before")

    def test_missing_preserves_cursor_and_replacement_resets(self):
        self.assertEqual(self.tail.read(), {"cursor": None, "text": "", "reset": False, "available": False})
        self.path.write_bytes(b"old")
        old = self.tail.read()
        self.path.unlink()
        missing = self.tail.read(old["cursor"])
        self.assertFalse(missing["available"])
        self.assertEqual(missing["cursor"], old["cursor"])
        self.path.write_bytes(b"new content")
        result = self.tail.read(missing["cursor"])
        self.assertTrue(result["reset"])
        self.assertEqual(result["text"], "new content")

    def test_malformed_cursors_and_limits(self):
        self.path.write_bytes(b"a" * (MAX_LIMIT + 10))
        for bad in ("", "v1:0:0:0::bad", "x" * 1000000, 123, "v1:0:0:0:ff:0000000000000000"):
            with self.subTest(bad=str(bad)[:20]):
                result = self.tail.read(bad, 3)
                self.assertTrue(result["reset"])
                self.assertEqual(result["text"], "aaa")
        self.assertEqual(len(self.tail.read(limit=10**30)["text"]), MAX_LIMIT)
        for limit in (0, -1, True, 1.2, "1", None):
            with self.assertRaises(ValueError):
                self.tail.read(limit=limit)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_fifo_is_not_opened(self):
        os.mkfifo(self.path)
        self.assertFalse(self.tail.read()["available"])

    def test_directory_not_available(self):
        self.assertFalse(SerialLogTail(self.root).read()["available"])


if __name__ == "__main__":
    unittest.main()
