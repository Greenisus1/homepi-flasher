#!/usr/bin/env python3
"""Unit + PTY tests for HomePi Flasher. Run: python3 test_flasher.py"""
import hashlib, lzma, os, pty, select, sys, tempfile, time, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flasher


class TestBootDisk(unittest.TestCase):
    def test_parses_pkname(self):
        def fake_run(cmd, **kw):
            class R: stdout = ""
            if cmd[0] == "findmnt":
                R.stdout = "/dev/mmcblk0p2\n"
            else:
                R.stdout = "mmcblk0\n"
            return R()
        with mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(flasher.boot_disk(), "mmcblk0")

    def test_returns_none_on_failure(self):
        with mock.patch("subprocess.run", side_effect=OSError("no findmnt")):
            self.assertIsNone(flasher.boot_disk())


class TestSpareDisks(unittest.TestCase):
    def test_excludes_boot_and_partitions(self):
        lsblk_out = ("mmcblk0 29.7G disk\n"
                     "sda 14.5G disk USB Reader\n"
                     "sda1 14.5G part\n"
                     "sdb 58.6G disk\n")
        def fake_run(cmd, **kw):
            class R: stdout = ""
            if cmd[0] == "findmnt":
                R.stdout = "/dev/mmcblk0p2\n"
            elif "PKNAME" in cmd:
                R.stdout = "mmcblk0\n"
            else:
                R.stdout = lsblk_out
            return R()
        with mock.patch("subprocess.run", side_effect=fake_run):
            disks = flasher.spare_disks()
        names = [d[0] for d in disks]
        self.assertEqual(names, ["sda", "sdb"])
        self.assertNotIn("mmcblk0", names)
        self.assertNotIn("sda1", names)

    def test_empty_when_only_boot(self):
        def fake_run(cmd, **kw):
            class R: stdout = ""
            if cmd[0] == "findmnt":
                R.stdout = "/dev/mmcblk0p2\n"
            elif "PKNAME" in cmd:
                R.stdout = "mmcblk0\n"
            else:
                R.stdout = "mmcblk0 29.7G disk\n"
            return R()
        with mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(flasher.spare_disks(), [])


class TestHashing(unittest.TestCase):
    def test_sha256_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"home pi test data" * 1000)
            path = f.name
        try:
            got = flasher.sha256_file(path)
            want = hashlib.sha256(b"home pi test data" * 1000).hexdigest()
            self.assertEqual(got, want)
        finally:
            os.unlink(path)

    def test_decompress_roundtrip(self):
        raw = os.urandom(300000) + b"homepi" * 5000
        with tempfile.TemporaryDirectory() as d:
            xz = os.path.join(d, "a.xz")
            img = os.path.join(d, "a.img")
            with open(xz, "wb") as f:
                f.write(lzma.compress(raw))
            flasher.decompress(xz, img)
            with open(img, "rb") as f:
                self.assertEqual(f.read(), raw)

    def test_write_image_bytes(self):
        data = os.urandom(100000)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.img")
            dst = os.path.join(d, "out.img")
            with open(src, "wb") as f:
                f.write(data)
            with mock.patch("subprocess.run"):
                flasher.write_image(src, dst)
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), data)


class TestPTY(unittest.TestCase):
    def run_demo(self, keys, timeout=30):
        """Run the app in DEMO mode under a pty, feed keys, return final screen text."""
        pid, fd = pty.fork()
        if pid == 0:
            os.environ["HOMEPI_FLASHER_DEMO"] = "1"
            os.environ["TERM"] = "xterm-256color"
            os.environ["LINES"] = "30"
            os.environ["COLUMNS"] = "90"
            os.execv(sys.executable, [sys.executable, os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "flasher.py")])
        output = b""
        deadline = time.time() + timeout
        sent = 0
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.3)
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
            if sent < len(keys) and b"Type y to go ahead" in output or (sent == 0 and b"Choose the drive" in output):
                time.sleep(0.2)
                os.write(fd, keys[sent])
                sent += 1
            if sent >= len(keys) and (b"Press any key to exit" in output):
                os.write(fd, b" ")
                time.sleep(0.3)
                break
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
        return output.decode("utf-8", "replace")

    def test_full_flow(self):
        screen = self.run_demo([b"\r", b"y"])
        self.assertIn("HomePi Flasher", screen)
        self.assertIn("protected", screen)
        self.assertIn("/dev/sda", screen)
        self.assertIn("ERASED", screen)
        self.assertIn("DONE", screen)
        self.assertIn("Home Pi 1.1.0 is on /dev/sda", screen)

    def test_quit_at_picker(self):
        screen = self.run_demo([b"q"])
        self.assertIn("Choose the drive", screen)

    def test_back_on_non_y(self):
        screen = self.run_demo([b"\r", b"n", b"q"])
        self.assertIn("Choose the drive", screen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
