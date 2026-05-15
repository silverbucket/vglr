# Raspberry Pi Setup

Complete setup guide for running vglr headless on a Raspberry Pi 5.

---

## Requirements

- Raspberry Pi 5 (4 GB recommended)
- Raspberry Pi OS Lite (64-bit, Debian Bookworm) — no desktop needed
- HDMI cable connected to projector or display
- Zoom F1 (or compatible USB audio device) plugged in
- AKAI MIDI Mix plugged in via USB
- Internet connection for initial package install

---

## 1. OS preparation

Use **Raspberry Pi OS Lite (64-bit)** — the full desktop is not required and adds overhead.

In `raspi-config` (run as root or with `sudo raspi-config`):

```
System Options → Boot / Auto Login → Console Autologin
```

This autologins your user to the console on boot, which is required for DRM/KMS display access from a non-desktop session.

Also enable SSH if you haven't:
```
Interface Options → SSH → Enable
```

---

## 2. System packages

```bash
sudo apt update && sudo apt install -y \
    git \
    python3-venv \
    python3-dev \
    libsdl2-2.0-0 \
    libportaudio2 \
    libasound2-dev
```

| Package | Why |
|---------|-----|
| `python3-venv` | Create an isolated Python environment |
| `python3-dev` | Headers needed to build native Python extensions |
| `libsdl2-2.0-0` | SDL2 runtime for `moderngl-window --window sdl2` |
| `libportaudio2` | PortAudio runtime for `sounddevice` |
| `libasound2-dev` | ALSA headers (needed by `python-rtmidi` build) |

---

## 3. User groups

Your user needs to be in the `video`, `audio`, and `plugdev` groups for DRM, audio, and USB MIDI access:

```bash
sudo usermod -aG video,audio,plugdev $USER
```

Log out and back in (or reboot) for group changes to take effect. Verify:

```bash
groups
# should include: video audio plugdev
```

---

## 4. Clone the repository

```bash
cd ~
git clone https://github.com/silverbucket/vglr.git
cd vglr
```

---

## 5. Python environment

```bash
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install \
    moderngl \
    moderngl-window \
    av \
    sounddevice \
    numpy \
    mido \
    python-rtmidi
```

> `python-rtmidi` is the ALSA MIDI backend used by mido. It requires `libasound2-dev` and `python3-dev` to build (installed in step 2).

Verify the install:

```bash
venv/bin/python -c "import moderngl, av, sounddevice, mido; print('OK')"
```

---

## 6. Identify your audio device

The Zoom F1 (or any USB audio device) needs to be on the correct sounddevice index. Plug it in and run:

```bash
venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"
```

Look for the Zoom F1 in the output (it usually shows up as something like `Zoom AudioCaptureU24`). Note its index number and set `AUDIO_DEVICE` at the top of `vglr.py` to match.

To make the device number stable across reboots, you can pin the card order in ALSA. Create `/etc/modprobe.d/alsa-base.conf`:

```
# Force the built-in card to index 0, USB audio to index 1
options snd-usb-audio index=1
options snd-bcm2835 index=0
```

After rebooting, re-run the device query to confirm. The Zoom F1 should consistently be index 1 (`AUDIO_DEVICE = 1`).

---

## 7. Test run

Before setting up a service, confirm everything works manually:

```bash
cd ~/vglr
SDL_VIDEODRIVER=kmsdrm venv/bin/python vglr.py --window sdl2 --fullscreen
```

You should see video playing fullscreen with the VHS shader. Press `Q` to quit.

If the screen stays black or crashes:
- Check the HDMI cable is connected before booting (Pi 5 needs HDMI at boot for KMS)
- Try without `--fullscreen` first to rule out resolution issues
- Check `journalctl -xe` for errors

---

## 8. Systemd service

Copy the service file and enable it:

```bash
sudo cp ~/vglr/system/vglr.service /etc/systemd/system/vglr.service
```

Edit it to confirm the username and paths match your setup:

```bash
sudo nano /etc/systemd/system/vglr.service
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vglr.service
sudo systemctl start vglr.service
```

Check it started cleanly:

```bash
sudo systemctl status vglr.service
```

---

## 9. Service management

| Command | Effect |
|---------|--------|
| `sudo systemctl start vglr` | Start now |
| `sudo systemctl stop vglr` | Stop now |
| `sudo systemctl restart vglr` | Restart (picks up code changes) |
| `sudo systemctl status vglr` | Show status and last few log lines |
| `sudo journalctl -u vglr -f` | Live log tail |
| `sudo journalctl -u vglr -n 100` | Last 100 log lines |
| `sudo systemctl enable vglr` | Auto-start on boot |
| `sudo systemctl disable vglr` | Disable auto-start |

---

## 10. Updating

```bash
cd ~/vglr
git pull
sudo systemctl restart vglr
```

That's it. The service picks up the new code on restart. Check `systemctl status vglr` afterward to confirm it came back up cleanly.

If you added new Python dependencies (new `pip install` needed), update the venv first:

```bash
cd ~/vglr
git pull
venv/bin/pip install <new-package>
sudo systemctl restart vglr
```

---

## 11. Adding videos

Create the slot directory and drop your video file in:

```bash
mkdir -p ~/vglr/videos/bank1/video2
cp /path/to/your/clip.mp4 ~/vglr/videos/bank1/video2/
```

No restart needed — switching to that slot via REC ARM 2 will load the new clip immediately.

---

## Troubleshooting

**No video / black screen**
- Ensure HDMI is connected before power-on. Pi 5 probes displays at boot; hotplug with KMS is unreliable.
- Run `kmsprint` to confirm the Pi can see the display and its mode list.
- Try `SDL_VIDEODRIVER=kmsdrm SDL_VIDEO_FORCE_EGL=1 venv/bin/python vglr.py --window sdl2 --fullscreen`.

**No audio reactivity**
- Check `AUDIO_DEVICE` in `vglr.py` matches the Zoom F1 index from `sounddevice.query_devices()`.
- Confirm the Zoom F1 is listed: `arecord -l`.
- Run manually and watch the `bass=/mid=/treble=` log lines — if all zeros, the device index is wrong.

**MIDI Mix not detected**
- Check `aconnect -i` to confirm the kernel sees it.
- Confirm your user is in the `audio` and `plugdev` groups (`groups` command).
- Check `venv/bin/python -c "import mido; print(mido.get_input_names())"` — the MIDI Mix should appear.

**Service fails to start / display access denied**
- Confirm console autologin is enabled in `raspi-config` (the autologin session grants KMS device access).
- Confirm your user is in the `video` group.
- Check `ls -la /dev/dri/` — your user or the `video` group should have access to `card0` and `renderD128`.

**Low FPS**
- Current working config: 720p, `GAIN=200.0`. The vhs shader with 7-sample blur runs ~15fps.
- If you need more headroom: simplify a shader, reduce blur samples, or accept 15fps (it reads as intentional glitch aesthetic).
- `sudo vcgencmd measure_clock arm` shows if the Pi is thermally throttled.

**ALSA device index changes after reboot**
- See step 6 for pinning the USB audio card to index 1 via `/etc/modprobe.d/alsa-base.conf`.
