#!/usr/bin/env python3
"""HomePi Flasher - fullscreen terminal app that writes the Home Pi image
to a second SD card or USB drive. Never touches the boot drive.
Python 3 + curses only. MIT license, (c) Greenisus1."""
import curses, hashlib, os, subprocess, sys, time, urllib.request

APP_NAME = "HomePi Flasher"
APP_VERSION = "1.0.0"
IMAGE_URL = "https://x0.at/6dsk.xz"
XZ_SHA256 = "67d6b210c64daaf1578e5e85195016198a1a85b0a426c9d57382e2094b72a482"
IMG_SHA256 = "2c9f2731485690afef45c0a000a75e8ae11e4f24b4dd9c78430d6a89a3ffad6d"
IMG_SIZE = 301990400
XZ_SIZE = 43867432
WORKDIR = os.path.expanduser("~/homepi-flash")
MIN_W, MIN_H = 45, 14


def boot_disk():
    """Name of the disk backing / (e.g. 'mmcblk0'), or None."""
    try:
        src = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/"],
                             capture_output=True, text=True, check=True).stdout.strip()
        pk = subprocess.run(["lsblk", "-no", "PKNAME", src],
                            capture_output=True, text=True).stdout.split()
        if pk:
            return pk[0]
        base = os.path.basename(src)
        while base and (base[-1].isdigit() or base.endswith("p")):
            base = base[:-1]
        return base or None
    except Exception:
        return None


def spare_disks():
    """List of (name, size_str, model) for whole disks that are NOT the boot disk."""
    boot = boot_disk()
    out = subprocess.run(["lsblk", "-dn", "-o", "NAME,SIZE,TYPE,MODEL"],
                         capture_output=True, text=True).stdout.splitlines()
    disks = []
    for line in out:
        parts = line.split(None, 3)
        if len(parts) < 3 or parts[2] != "disk":
            continue
        name = parts[0]
        if name == boot:
            continue
        model = parts[3] if len(parts) > 3 else ""
        disks.append((name, parts[1], model))
    return disks


def sha256_file(path, progress=None):
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    return h.hexdigest()


def download(url, dest, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "HomePi-Flasher/1.0"})
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    return done


def decompress(xz_path, img_path, progress=None):
    import lzma
    done = 0
    with lzma.open(xz_path, "rb") as src, open(img_path, "wb") as dst:
        while True:
            chunk = src.read(4 * 1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    return done


def write_image(img_path, target, progress=None):
    done = 0
    with open(img_path, "rb") as src, open(target, "wb", buffering=0) as dst:
        while True:
            chunk = src.read(4 * 1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            done += len(chunk)
            if progress:
                progress(done)
        dst.flush()
        os.fsync(dst.fileno())
    subprocess.run(["sync"])
    return done


def unmount_target(target):
    subprocess.run("umount /dev/%s* 2>/dev/null" % target, shell=True)

DEMO = os.environ.get("HOMEPI_FLASHER_DEMO") == "1"

if DEMO:
    def spare_disks():
        return [("sda", "14.5G", "USB Card Reader"), ("sdb", "29G", "USB3 Flash")]
    def boot_disk():
        return "mmcblk0"

def draw_header(stdscr):
    h, w = stdscr.getmaxyx()
    title = " %s %s " % (APP_NAME, APP_VERSION)
    stdscr.attron(curses.A_REVERSE)
    stdscr.addnstr(0, 0, title + " " * (w - len(title)), w)
    stdscr.attroff(curses.A_REVERSE)
    stdscr.addnstr(1, 0, "Writes Home Pi 1.1.0 to a second SD card / USB drive.", w - 1)


def too_small(stdscr):
    stdscr.erase()
    stdscr.addnstr(0, 0, "Terminal too small. Need at least %dx%d." % (MIN_W, MIN_H), 40)
    stdscr.refresh()


def pick_drive(stdscr, disks, boot):
    sel = 0
    while True:
        h, w = stdscr.getmaxyx()
        if h < MIN_H or w < MIN_W:
            too_small(stdscr)
            if stdscr.getch() in (ord("q"), 27):
                return None
            continue
        stdscr.erase()
        draw_header(stdscr)
        stdscr.addnstr(3, 2, "Boot drive: /dev/%s - protected, not listed." % (boot or "?"), w - 3)
        stdscr.addnstr(5, 2, "Choose the drive to ERASE and write (Up/Down, Enter, q quits):", w - 3)
        for i, (name, size, model) in enumerate(disks):
            line = " /dev/%-10s %8s  %s" % (name, size, model)
            attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
            stdscr.addnstr(7 + i, 4, line, w - 5, attr)
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            sel = (sel - 1) % len(disks)
        elif ch in (curses.KEY_DOWN, ord("j")):
            sel = (sel + 1) % len(disks)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return disks[sel]
        elif ch in (ord("q"), 27):
            return None


def confirm(stdscr, name, size):
    stdscr.erase()
    draw_header(stdscr)
    h, w = stdscr.getmaxyx()
    stdscr.addnstr(3, 2, "You picked /dev/%s (%s)." % (name, size), w - 3)
    stdscr.attron(curses.A_BOLD)
    stdscr.addnstr(5, 2, "ALL DATA on /dev/%s will be ERASED." % name, w - 3)
    stdscr.attroff(curses.A_BOLD)
    stdscr.addnstr(7, 2, "It will be replaced with Home Pi 1.1.0.", w - 3)
    stdscr.addnstr(9, 2, "Type y to go ahead, any other key to go back: ", w - 3)
    stdscr.refresh()
    return stdscr.getch() == ord("y")


def progress_run(stdscr, name):
    stages = [
        ("Downloading image", XZ_SIZE),
        ("Checking download hash", XZ_SIZE),
        ("Decompressing", IMG_SIZE),
        ("Checking image hash", IMG_SIZE),
        ("Writing to /dev/%s" % name, IMG_SIZE),
    ]
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    draw_header(stdscr)
    stdscr.nodelay(True)

    def show(row, label, done, total):
        pct = min(1.0, done / float(total)) if total else 0
        barw = max(10, w - 30)
        fill = int(barw * pct)
        stdscr.addnstr(row, 2, label, w - 3)
        stdscr.addnstr(row + 1, 4, "[" + "#" * fill + "-" * (barw - fill) + "] %3d%%" % (pct * 100), w - 5)
        stdscr.refresh()

    def run_stage(idx, label, total, fn):
        row = 3 + idx * 3
        show(row, label, 0, total)
        def prog(done):
            show(row, label, done, total)
            ch = stdscr.getch()
        fn(prog)
        show(row, label, total, total)

    xz_path = os.path.join(WORKDIR, "homepi.img.xz")
    img_path = os.path.join(WORKDIR, "homepi.img")
    os.makedirs(WORKDIR, exist_ok=True)

    if DEMO:
        import time as _t
        for idx, (label, total) in enumerate(stages):
            row = 3 + idx * 3
            for step in range(0, 11):
                show(row, label, total * step // 10, total)
                _t.sleep(0.05)
        return True

    run_stage(0, stages[0][0], XZ_SIZE, lambda p: download(IMAGE_URL, xz_path, p))
    run_stage(1, stages[1][0], XZ_SIZE,
              lambda p: (_ for _ in ()).throw(RuntimeError("download hash mismatch"))
              if sha256_file(xz_path, p) != XZ_SHA256 else None)
    run_stage(2, stages[2][0], IMG_SIZE, lambda p: decompress(xz_path, img_path, p))
    run_stage(3, stages[3][0], IMG_SIZE,
              lambda p: (_ for _ in ()).throw(RuntimeError("image hash mismatch"))
              if sha256_file(img_path, p) != IMG_SHA256 else None)
    unmount_target(name)
    run_stage(4, stages[4][0], IMG_SIZE, lambda p: write_image(img_path, "/dev/" + name, p))
    try:
        os.remove(img_path)
    except OSError:
        pass
    return True


def done_screen(stdscr, name):
    stdscr.nodelay(False)
    stdscr.erase()
    draw_header(stdscr)
    h, w = stdscr.getmaxyx()
    stdscr.attron(curses.A_BOLD)
    stdscr.addnstr(3, 2, "DONE. Home Pi 1.1.0 is on /dev/%s." % name, w - 3)
    stdscr.attroff(curses.A_BOLD)
    stdscr.addnstr(5, 2, "Power off, swap the card in, and boot.", w - 3)
    stdscr.addnstr(7, 2, "Press any key to exit.", w - 3)
    stdscr.refresh()
    stdscr.getch()


def fail_screen(stdscr, msg):
    stdscr.nodelay(False)
    stdscr.erase()
    draw_header(stdscr)
    h, w = stdscr.getmaxyx()
    stdscr.addnstr(3, 2, "Stopped: %s" % msg, w - 3)
    stdscr.addnstr(5, 2, "Nothing more was written. Press any key to exit.", w - 3)
    stdscr.refresh()
    stdscr.getch()


def main_ui(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    if os.geteuid() != 0 and not DEMO:
        stdscr.erase()
        draw_header(stdscr)
        stdscr.addnstr(3, 2, "Please run as root (the write step needs it).", 60)
        stdscr.addnstr(5, 2, "Press any key to exit.", 60)
        stdscr.refresh()
        stdscr.getch()
        return 1
    boot = boot_disk()
    disks = spare_disks()
    if not disks:
        stdscr.erase()
        draw_header(stdscr)
        stdscr.addnstr(3, 2, "No spare drive found.", 60)
        stdscr.addnstr(4, 2, "Plug in the second card or USB drive, then run again.", 70)
        stdscr.addnstr(6, 2, "Press any key to exit.", 60)
        stdscr.refresh()
        stdscr.getch()
        return 1
    while True:
        pick = pick_drive(stdscr, disks, boot)
        if pick is None:
            return 0
        name, size, model = pick
        if confirm(stdscr, name, size):
            break
    try:
        progress_run(stdscr, name)
    except Exception as e:
        fail_screen(stdscr, str(e)[:200])
        return 1
    done_screen(stdscr, name)
    return 0


def main():
    if not sys.stdout.isatty() and not DEMO:
        print("HomePi Flasher needs a terminal. Run it in a fullscreen console.")
        return 1
    return curses.wrapper(main_ui)


if __name__ == "__main__":
    sys.exit(main() or 0)
