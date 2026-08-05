# Firmware Guide — Building & Flashing the Custom IMU Firmware (moteus C1)

A start-to-finish guide for lab members who need to **build the firmware image
(`.elf`)** and/or **flash it onto a moteus C1**, then wire up and test the IMU.
No prior moteus experience is assumed — every command and every scary-looking
message is explained.

> **TL;DR**
> - If you already have `moteus.elf`, skip to **Part 2 — Flashing**.
> - If you don't, **Part 1 — Building** shows how to generate it (needs an
>   x86-64 Ubuntu machine).
> - The single most common mistake on the C1: the AUX1 I2C pins are
>   **`aux1.pins.3` (SCL)** and **`aux1.pins.4` (SDA)** — *not* 2 and 3.

---

## What this firmware is

Stock moteus firmware can't stream raw 6-axis IMU data. This fork adds two
I2C IMU device types that read a sensor directly on the moteus **AUX1** port —
no extra microcontroller:

| Type | Name | Sensor | Output |
|------|------|--------|--------|
| **5** | `lsm6dsv16xRaw` | ST LSM6DSV16X | raw accel + gyro (6 axes) |
| **6** | `mpu6050` | InvenSense MPU6050 | raw accel + gyro (6 axes) |

Both stream 3 accelerometer + 3 gyroscope axes over CAN, alongside the AUX2
encoder and the onboard AS5047P.

**Credit:** built on Otavio Good's LSM6DSV16X quaternion work → Neel Adke added
the type-5 raw mode → this repo adds the type-6 MPU6050 mode. Base firmware is
mjbots/moteus (Josh Pieper), Apache-2.0.

---

# Part 1 — Building the firmware (`.elf`)

You only need this if you don't already have a `moteus.elf`. If someone hands
you the file, skip to Part 2 — you can flash from any OS.

## 1.1 What you need

- **An x86-64 (Intel/AMD) Ubuntu machine** — 20.04, 22.04, or 24.04.
  - It will **not** build on a Mac (Apple Silicon or Intel) or a Raspberry Pi.
    The build cross-compiles for the STM32 chip, but the *build host itself*
    must be x86-64 Linux.
- `git`, `curl`, and `python3` installed:
  ```bash
  sudo apt update && sudo apt install -y git curl python3
  ```

> **Note on Python environments:** the build is driven by **Bazel**, not pip, so
> you do *not* need to `pip install` anything to build. If you happen to have a
> Python virtual environment active (e.g. the `moteus-venv` from Part 2), that's
> completely fine — it won't interfere. The only Python requirement is that a
> working `python3` exists on the machine, because Bazel calls it during the
> build.

## 1.2 Get the source

```bash
git clone https://github.com/v-dahi/moteus-imu-firmware.git
cd moteus-imu-firmware
```

## 1.3 Build

Use the repo's `tools/bazel` wrapper — it downloads the correct Bazel version
and the ARM toolchain automatically (first run needs internet and takes a few
minutes):

```bash
tools/bazel build --config=target //:target
```

When it prints `Build completed successfully`, the firmware is at:

```
bazel-bin/fw/moteus.elf
```

(If you can't find it: `find -L bazel-bin -name "moteus.elf"`.)

Copy that file to wherever you'll flash from:

```bash
cp bazel-bin/fw/moteus.elf ~/moteus.elf
```

## 1.4 Build hiccups you may hit

| What you see | What it means / fix |
|---|---|
| `ERROR: No test targets were found, yet testing was requested` | Only appears if you ran `bazel test` instead of `bazel build`. **Harmless** — `//:target` has no unit tests. The build above it still succeeded. Use `build` to avoid the message. |
| Build fails immediately on a Mac / Raspberry Pi | Wrong CPU. You must build on **x86-64 Ubuntu**. |
| First build hangs for minutes with download activity | Normal — Bazel is fetching its toolchain. Needs internet; let it finish. |
| `python3: command not found` during build | Install it: `sudo apt install -y python3`. |

---

# Part 2 — Flashing the firmware

Do this on the machine connected to the moteus over CAN. It works on Linux or
Mac (the flashing tool is cross-platform).

## 2.1 Install the flashing tool (`moteus_tool`)

On modern Ubuntu, use a virtual environment (avoids the "externally-managed"
pip error). This is also the `moteus-venv` referenced elsewhere:

```bash
sudo apt install -y python3-venv
python3 -m venv ~/moteus-venv
source ~/moteus-venv/bin/activate      # do this in every new terminal
pip install moteus moteus-gui
```

If you're **not** using a venv and pip complains about
`externally-managed-environment`:

```bash
pip3 install moteus moteus-gui --break-system-packages
```

Confirm it works:

```bash
python3 -m moteus.moteus_tool --help
```

That should print a usage screen. If you get `No module named 'moteus'`, your
`pip3` and `python3` point at different installs — force a match with
`python3 -m pip install moteus moteus-gui`.

## 2.2 Connect and confirm the board responds

1. Power the C1 from **its own power supply** (not just the USB CAN adapter).
2. Plug the CAN-FD adapter (e.g. fdcanusb) into your computer's USB and into the
   C1's **CAN** port (the JST-PH3 connector — **not** an AUX port).
3. Test communication:
   ```bash
   python3 -m moteus.moteus_tool --target 1 --info
   ```

- **Returns board info in a second or two → good.** Continue.
- **Hangs for many seconds → the board isn't reachable.** Ctrl-C and check:
  - **Power** — is the C1 actually powered? (most common cause)
  - **CAN wiring** — adapter firmly in the CAN port; the bus usually needs a
    termination resistor.
  - **Adapter detected?** On Mac: `ls /dev/tty.*` should show a
    `/dev/tty.usbmodemXXXX`. On Linux: `ls /dev/ttyACM*`.
  - **Wrong CAN ID?** The board may not be at ID 1. Scan IDs 1–10:
    ```bash
    python3 -m moteus.moteus_tool -t 1-10 -s
    ```
    There is **no `--scan` flag** — it's `-s` with a `-t` range. Use whatever ID
    it finds in place of `1` everywhere below.

## 2.3 Back up everything first (do NOT skip)

There are two separate things to save.

**a) Config backup (fully restorable):**
```bash
python3 -m moteus.moteus_tool --target 1 --dump-config > moteus_config_backup.txt
```
Nothing prints on success. Verify it captured data:
```bash
wc -l moteus_config_backup.txt      # expect a few hundred+ lines
```
This file holds your motor calibration, encoder offset table, and
cogging-compensation table — the painful-to-regenerate stuff. Restore later with
`--restore-config moteus_config_backup.txt`.

**b) Record the current firmware identity:**
```bash
python3 -m moteus.moteus_tool --target 1 --info    # save this output
```

> **⚠️ Firmware is not fully recoverable.** `moteus_tool` can only flash firmware
> *onto* the board; it cannot read the running firmware back out. So:
> - If the board currently runs an **official mjbots release**, you can always
>   re-download that `.elf` from github.com/mjbots/moteus/releases.
> - If it runs a **custom build** (a `git_hash`/date that matches no official
>   release), that exact image is **gone** unless you already have its `.elf`.
>   Get the file from whoever built it **before** you flash over it.
>
> Your real safety net = your **config backup** + the ability to reflash a clean
> official release. The `0.3.x` numbers from pip are the **tool** version, not
> the firmware.

## 2.4 Flash

From the folder containing `moteus.elf`:
```bash
python3 -m moteus.moteus_tool --target 1 --flash moteus.elf
```
Takes a minute or two. **Do not cut power mid-flash.**

The tool automatically saves your config, flashes, and writes the config back.
You will likely see messages that look alarming but are **normal**:

- `Downgraded ...pll_filter_hz from 400.0 to 161.3` — the new firmware caps some
  values and auto-clamps them. Fine.
- `Some config could not be set: conf set aux1.index.invert 0 ...` — those keys
  don't exist in this build, so they're skipped. Harmless when the values were
  defaults.
- Ends with `Saving to persistent storage with 'conf write'` — success.

Confirm the flash took:
```bash
python3 -m moteus.moteus_tool --target 1 --info      # git_hash should be the NEW one
```

## 2.5 Verify the motor and encoders still work

Do this **before** touching the IMU. Open the GUI:
```bash
python3 -m moteus_gui.tview --target 1
```
In tview:
1. **Faults:** in the telemetry tree, `servo_stats.fault` should be `0`.
2. **Encoders:** rotate the shaft by hand, watch `position` change.
3. **Hold test** — type this in **tview's** command box at the bottom (these
   `d ...` lines go in tview, *not* your shell), shaft free:
   ```
   d pos nan 0 1
   ```
   "Hold position, velocity 0, up to 1 Nm." The motor should **hold and resist
   your hand** — noisy but **not spinning** is correct.
4. **Spin test:**
   ```
   d pos nan 1 1
   ```
   Should turn **smoothly**. Then release:
   ```
   d stop
   ```

**Do you need to recalibrate? Almost never.** If the motor spins smoothly and
`fault` is 0, **do not** recalibrate — it overwrites good calibration for no
benefit. Only calibrate if the motor won't commutate (buzzes/jerks/won't hold or
spin). If you truly must, with the motor free to spin:
```bash
python3 -m moteus.moteus_tool --target 1 --calibrate
```
And if a flash ever wiped your settings, restore them:
```bash
python3 -m moteus.moteus_tool --target 1 --restore-config moteus_config_backup.txt
```

## 2.6 Wire and configure the IMU

### Wiring (requires soldering)

On the **moteus C1**, AUX1 has **no connector** — only two exposed pads, **D**
and **E**, on an unpopulated 0.05" through-hole land. The IMU solders to those.

| IMU pin | C1 AUX1 pad | Config pin index |
|---------|-------------|------------------|
| SCL | **D** | `aux1.pins.3` |
| SDA | **E** | `aux1.pins.4` |
| 3.3V | 3.3V pad | — (**not 5V** — SparkFun LSM6DSV16X/MPU6050 boards run at 3.3V) |
| GND | GND pad | — |

- **Power off and disconnect** the board before soldering.
- Use the mjbots C1 pinout for your board revision (reference build used a
  **c1 r1.2**) to locate the D / E / 3V3 / GND pads.
- **Pull-ups:** the C1 has **no internal I2C pull-ups on AUX1**, so your IMU
  breakout *must* provide them (SparkFun boards do). This is why the config
  below sets `aux1.i2c.pullup 0`.
- The AUX2 encoder (e.g. MA600) stays on its own AUX2 connector — unchanged.
- **Check the IMU's I2C address** and match it in the config below.

### Configure — LSM6DSV16X (type 5)

Enter in tview's command box (or prefix each with
`python3 -m moteus.moteus_tool --target 1 -c "..."`):

```
conf set aux1.i2c.i2c_hz 400000
conf set aux1.i2c.pullup 0
conf set aux1.i2c.devices.0.type 5          # 5 = lsm6dsv16xRaw
conf set aux1.i2c.devices.0.address 107     # 0x6B (use 106 / 0x6A if SA0 low)
conf set aux1.i2c.devices.0.poll_rate_us 2000
conf set aux1.pins.3.mode 13                # 13 = i2c  (SCL, pad D)
conf set aux1.pins.4.mode 13                # 13 = i2c  (SDA, pad E)
conf write
```

> **Critical for type 5:** `poll_rate_us` must be **2000** (500 Hz). This
> firmware alternates accel/gyro reads each cycle and **refuses to initialize**
> the LSM6DSV16X if polling is slower than ~2 ms.

### Configure — MPU6050 (type 6)

Same pins, different type and address:

```
conf set aux1.i2c.i2c_hz 400000
conf set aux1.i2c.pullup 0
conf set aux1.i2c.devices.0.type 6          # 6 = mpu6050
conf set aux1.i2c.devices.0.address 104     # 0x68 (use 105 / 0x69 if AD0 high)
conf set aux1.pins.3.mode 13                # SCL, pad D
conf set aux1.pins.4.mode 13                # SDA, pad E
conf write
```

> The MPU6050 driver does a single burst read (not alternating), so it has **no**
> poll-rate restriction — the default is fine.

Power-cycle after `conf write`. In tview, the type dropdown under
`aux1.i2c.devices.0` will now list `lsm6dsv16xRaw` and `mpu6050`.

## 2.7 Test the IMU

Use the example script for your sensor (in `lib/python/examples/`):

| Sensor | Script |
|--------|--------|
| LSM6DSV16X (type 5) | `read_accel_gyro.py` or `readIMUma6.py` (adds encoders) |
| MPU6050 (type 6) | `read_mpu6050.py` |

```bash
python3 lib/python/examples/read_mpu6050.py --target 1
```

These read accel from CAN registers `0x072–0x074` and gyro from `0x080–0x082`,
and convert raw counts to m/s² and deg/s.

**Sanity checks:**
- At rest, accelerometer magnitude ≈ **9.8 m/s²** (1 g).
- Tilt the IMU: the axis pointing down reads ≈ ±9.8.
- Rotate it: the matching gyro axis spikes, then returns to ~0.

---

## Troubleshooting quick reference

| Symptom | Likely cause / fix |
|---|---|
| `--info` / `--dump-config` hangs | Board unreachable: power, CAN wiring/termination, or wrong `--target` ID. Scan with `-t 1-10 -s`. |
| `No module named 'moteus'` | Not installed, or `pip3`/`python3` mismatch. Use `python3 -m pip install moteus moteus-gui`. |
| `unrecognized arguments: --scan` | There is no `--scan`. Use `-t 1-10 -s`. |
| `Downgraded pll_filter_hz` during flash | Normal — firmware clamps to its max. Ignore. |
| `Some config could not be set` during flash | Normal — those keys don't exist in this build; skipped. |
| `d pos ...` → `command not found` | That's a **tview** command, not a shell command. Type it in tview's box. |
| Motor is noisy but won't spin on `d pos nan 0 1` | Correct — that command *holds* position. Use `d pos nan 1 1` to spin. |
| **IMU shows in tview but reads all zeros / never initializes (C1)** | Wrong AUX1 pins. On the C1 it **must** be `aux1.pins.3` (SCL) and `aux1.pins.4` (SDA). Some example-script comments say pins 2/3 — that's for other boards and is **wrong for the C1** (pin 2 isn't even exposed on C1 AUX1). |
| Type 5 IMU won't initialize | `poll_rate_us` too slow — set it to `2000`. |
| Type 5 or 6 not listed in tview dropdown | The board is running old firmware without that type. Rebuild/reflash (Part 1). |
| No I2C communication at all | C1 has no internal AUX1 pull-ups — the breakout must provide them, and `aux1.i2c.pullup` should be `0`. |

---

## Building vs. downloading — quick recap

- **Have the `.elf`?** Flash from any OS (Part 2). Easiest.
- **Don't have it?** Build on x86-64 Ubuntu (Part 1), or ask a labmate for the
  file. Prebuilt binaries may also be attached to this repo's GitHub
  **Releases** page.
- The firmware is licensed Apache-2.0 (see `LICENSE`).
