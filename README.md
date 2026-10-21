# HomePi Flasher

A fullscreen terminal app that writes the Home Pi 1.1.0 image to a second SD card or USB drive plugged into your Pi. Made for the Raspberry Pi keyboard-in-hand case: pick the target with arrow keys, confirm, and it downloads, hash-checks, decompresses, writes and syncs the card for you.

The drive the Pi booted from is detected and never listed, so you cannot erase your running system by accident. Before anything is written, the app shows the exact target device and size and makes you type `y`.

## What it does

1. Lists only spare drives (the boot drive is shown as protected and excluded).
2. Tells you the target will be erased and waits for a typed `y`.
3. Downloads the official Home Pi 1.1.0 image.
4. Verifies the download's sha256, then the decompressed image's sha256.
5. Writes the image to the card and syncs.

Python 3 with curses only. No desktop, browser, pip packages or API keys. Works on DietPi, Raspberry Pi OS, Linux or macOS over SSH.

## Install

```sh
wget -O install-homepi-flasher.sh https://raw.githubusercontent.com/Greenisus1/homepi-flasher/main/install.sh && sh install-homepi-flasher.sh
```

The `app-store.sh` marker lets Pi App Store discover this under Apps. Refresh the store, install HomePi Flasher, then launch it from Run apps. Its store launcher is always fullscreen.

## No-store path

The same safety flow exists as a plain shell script that needs only `wget`, `xz`, `dd` and `sha256sum`:

```sh
wget -O flash.sh https://raw.githubusercontent.com/Greenisus1/homepi/main/homepi-flash.sh
sh flash.sh
```

Use that on a fresh Pi that does not have the App Store yet.

## Notes

- Run as root; writing a card needs it.
- Everything on the target card is erased. Use a spare card if you want to keep what is on it.
- Minimum terminal size: 45 columns by 14 rows. Resize freely.

Built with AI assistance from my design.

## License

MIT
