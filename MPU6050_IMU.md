# moteus IMU firmware — LSM6DSV16X + MPU6050 on AUX1

This is a fork of the [mjbots/moteus](https://github.com/mjbots/moteus) motor
controller firmware that lets the moteus read an **IMU directly over its AUX1
I2C pins** — no separate microcontroller. It supports two IMU families:

- **STMicro LSM6DSV16X** — quaternion (on-chip fusion), accel-only, and raw
  accel+gyro modes.
- **InvenSense MPU6050** — raw accel+gyro (added in this fork).

A second encoder can run on AUX2 (SPI) at the same time, while the onboard
AS5047P remains the motor commutation source.

---

## Credits / who built what

This firmware is the product of several people's work, layered on top of each
other. Please preserve this attribution.

| Layer | Author | Contribution |
|-------|--------|--------------|
| Base firmware | **Josh Pieper / [mjbots](https://github.com/mjbots/moteus)** | The entire moteus motor controller firmware. Apache-2.0 licensed. |
| IMU support | **Otavio Good** (`otaviogood@yahoo.com`) | Added the LSM6DSV16X I2C driver: on-chip SFLP quaternion output, accelerometer mode, quaternion CAN registers + atomic read cache, I2C robustness, and the original Python examples. |
| Raw accel+gyro | **Neel Adke** | Added the `lsm6dsv16xRaw` device type (type 5) exposing raw accelerometer + gyroscope, the gyro CAN registers, and supporting examples. *(Attributed from the source folder provenance; this work was uncommitted in the original tree.)* |
| MPU6050 support | **Vaidehi Gohil** | Added the `mpu6050` device type (type 6) for the InvenSense MPU6050, and `read_mpu6050.py`. |

The commit history in this repo reflects these layers: mjbots/Otavio commits,
then a "type 5" commit credited to Neel Adke, then a "type 6" MPU6050 commit.

> Note: Neel Adke's commit currently uses a placeholder email
> (`neeladke@users.noreply.github.com`). If you have his real address/GitHub
> handle, amend it with
> `git commit --amend --author="Neel Adke <real@email>"` on that commit (via an
> interactive rebase), or leave as-is.

---

## What the MPU6050 addition does (type 6)

The MPU6050 is register-based, so it slots into the same pattern Neel's type-5
raw mode uses. Added, all in `fw/aux_common.h` and `fw/aux_port.h`:

- New enum value `kMpu6050` → **device type 6**, plus its tview name `mpu6050`.
- `InitMpu6050()` — wakes the chip (`PWR_MGMT_1=0x00`), enables the digital
  low-pass filter (~44 Hz), sets 200 Hz output, gyro **±2000 dps**, accel **±16 g**.
- `ReadMpu6050()` — a single non-blocking 14-byte burst read from `0x3B`
  (accel + temp + gyro registers are contiguous).
- `ISR_ParseMpu6050()` — unpacks accel/gyro into the same status fields the LSM
  path uses. **Note:** the MPU6050 is big-endian (high byte first), the opposite
  of the LSM6DSV16X.

Because the accel/gyro data lands in the same `DeviceStatus` fields, it flows
out through the **same CAN registers** as the LSM raw mode — so no changes were
needed to `moteus_controller.cc` or the Python library, and both drivers live
in one firmware image. You switch chips purely by config, no re-flash.

### LSM6DSV16X vs MPU6050

Both are 6-axis (accel + gyro). The LSM6DSV16X additionally has an on-chip
fusion engine (SFLP) that outputs an orientation quaternion; the MPU6050 does
not (in practice), so it gives raw accel+gyro only. Neither has a magnetometer,
so neither provides absolute compass heading.

---

## Hardware setup

- **AUX1** — I2C to the IMU (pins 2 and 3 = SCL/SDA). I2C pull-up resistors are
  required (most breakout boards include them).
- **AUX2** — optional SPI encoder (e.g. MA600).
- **Onboard** — AS5047P, motor commutation.

Tested target: **moteus c1** (STM32G4).

I2C addresses:

| IMU | Default address |
|-----|-----------------|
| LSM6DSV16X | `0x6B` = **107** (`0x6A`/106 if SA0 low) |
| MPU6050 | `0x68` = **104** (`0x69`/105 if AD0 high) |

---

## Building the firmware (Linux only)

mjbots builds this on **x86-64 Ubuntu 20.04 / 22.04 / 24.04**. Only `curl` is
required as a prerequisite; the build fetches its own toolchain.

```bash
# from the moteus/ directory
tools/bazel build --config=target //:target
# firmware ELF: bazel-bin/fw/moteus.elf
```

(`tools/bazel test --config=target //:target` also works; it prints a harmless
"No test targets were found" because `//:target` is a packaging filegroup.)

---

## Flashing (over CAN, via fdcanusb)

Install the host tools (in a Python venv on modern Ubuntu):

```bash
python3 -m venv ~/moteus-venv && source ~/moteus-venv/bin/activate
pip install moteus moteus-gui
```

Flash the ELF built above:

```bash
python3 -m moteus.moteus_tool --target 1 --flash bazel-bin/fw/moteus.elf
```

---

## Configuration

Pins are the same for both IMUs; only the **type** and **address** differ.

### MPU6050 (type 6)

```bash
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.type 6"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.address 104"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.2.mode 13"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.3.mode 13"
python3 -m moteus.moteus_tool --target 1 -c "conf write"
```

### LSM6DSV16X raw accel+gyro (type 5)

```bash
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.type 5"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.address 107"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.2.mode 13"
python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.3.mode 13"
python3 -m moteus.moteus_tool --target 1 -c "conf write"
```

`pins.*.mode 13` = I2C. Power-cycle after `conf write`. In tview, the device
type dropdown under `aux1.i2c.devices.0` will list `mpu6050` and `lsm6dsv16xRaw`.

---

## Reading the data

| Script | Sensor |
|--------|--------|
| `lib/python/examples/read_mpu6050.py` | MPU6050 (type 6) |
| `lib/python/examples/read_accel_gyro.py` | LSM6DSV16X raw (type 5) |
| `lib/python/examples/readIMUma6.py` | IMU + MA600/onboard encoders |

```bash
python3 lib/python/examples/read_mpu6050.py --target 1
```

Both scripts read the same CAN registers (accel `0x072–0x074`, gyro
`0x080–0x082`) and apply scale factors. **The gyro scale differs by chip:**

| | accel (±16 g) | gyro (±2000 dps) |
|-|---------------|------------------|
| LSM6DSV16X | 0.000488 g/count | 0.070 °/s/count |
| MPU6050 | 0.000488 g/count | **0.0610 °/s/count** (1/16.4) |

Stationary you should read `|accel| ≈ 9.8 m/s²` and gyro ≈ 0; rotate the board
and the gyro axes should respond.

---

## Intended application

Wearable exoskeletons (back / hip / ankle) — detecting gait cycle, hip
movement, and bending vs. lifting. The workhorse signals are **gyro angular
velocity** (measured directly) and **segment angle** (from a lightweight
complementary/Madgwick filter on the host, fusing raw accel + gyro). Note that
true linear velocity is *not* reliably obtainable from any of these IMUs, since
integrating accelerometer data drifts.

---

## License

The moteus firmware is licensed under Apache License 2.0 (see `LICENSE`). All
additions in this fork are contributed under the same license.
