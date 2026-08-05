#!/usr/bin/python3 -B

"""
Read raw accelerometer and gyroscope data from LSM6DSV16X IMU
on a moteus controller configured with Type 5 (lsm6dsv16xRaw mode).

This script continuously reads 6 values:
- Accelerometer X, Y, Z (in m/s²)
- Gyroscope X, Y, Z (in degrees/second)

Configuration in tview:
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.type 5"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.address 107"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.2.mode 13"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.3.mode 13"
    python3 -m moteus.moteus_tool --target 1 -c "conf write"
"""

import asyncio
import math
import moteus
from moteus.multiplex import INT16

# SCALE FACTORS - Convert raw sensor counts to physical units

# Accelerometer scale factor calculation:
# - IMU configured for ±16g full scale range
# - 16-bit ADC: -32768 to +32767 counts
# - Scale: 16g / 32768 counts = 0.000488 g/count
# - Convert to SI units: 0.000488 g/count × 9.80665 m/s²/g = 0.004786 m/s²/count
ACCEL_SCALE = 0.000488 * 9.80665  # m/s² per LSB (at ±16g range)

# Gyroscope scale factor:
# - IMU configured for ±2000 degrees/second full scale range
# - From datasheet: sensitivity = 70 mdps/LSB = 0.07 deg/s per count
GYRO_SCALE = 0.07  # degrees/second per LSB (at ±2000 dps range)


def convert_to_signed(value):
    """
    Convert unsigned 16-bit value to signed 16-bit integer.
    
    The moteus library returns register values as unsigned integers (0-65535),
    but sensor data is actually signed (-32768 to +32767).
    
    If value > 32767, it's actually a negative number in two's complement format.
    For example: 64977 (unsigned) = -558 (signed)
    
    Args:
        value: Unsigned integer from register (0-65535)
    
    Returns:
        Signed integer (-32768 to +32767)
    """
    if value > 32767:
        return value - 65536
    return value


async def main():

    # COMMAND LINE ARGUMENT PARSING
    import argparse
    parser = argparse.ArgumentParser(
        description='Read accelerometer and gyroscope from moteus controller'
    )
    parser.add_argument(
        '--target', 
        type=int, 
        default=1, 
        help='CAN ID of the target controller (default: 1)'
    )
    parser.add_argument(
        '--rate', 
        type=float, 
        default=0.1,
        help='Update rate in seconds (default: 0.1 = 10 Hz)'
    )
    # Add standard moteus transport arguments (--can-iface, --fdcanusb, etc.)
    moteus.make_transport_args(parser)
    args = parser.parse_args()
    
    # QUERY SETUP - Tell moteus which registers to read    
    # QueryResolution defines what data to request from the controller
    qr = moteus.QueryResolution()
    
    # _extra is a dictionary of custom registers to query
    # Key = register address (hex), Value = data type
    # These registers were added in our custom firmware (Type 5 mode)
    qr._extra = {
        # Accelerometer data (reuses quaternion registers in Type 5 mode)
        0x072: INT16,  # Accel X - raw int16 value
        0x073: INT16,  # Accel Y - raw int16 value
        0x074: INT16,  # Accel Z - raw int16 value
        
        # Gyroscope data (new registers added for Type 5)
        0x080: INT16,  # Gyro X - raw int16 value
        0x081: INT16,  # Gyro Y - raw int16 value
        0x082: INT16,  # Gyro Z - raw int16 value
    }

    # CONTROLLER SETUP - Establish CAN bus connection
    
    # Get the CAN transport (handles USB adapter, socketcan, etc.)
    transport = moteus.get_singleton_transport(args)
    
    # Create controller object for the specified device ID
    controller = moteus.Controller(
        id=args.target,              # Which controller to talk to (CAN ID)
        query_resolution=qr,         # What data to request
        transport=transport           # How to communicate (CAN bus)
    )

    # DISPLAY STARTUP INFO
    print(f"Reading accel and gyro from controller {args.target}")
    print(f"Make sure controller is configured with type 5 (lsm6dsv16xRaw)")
    print(f"Update rate: {args.rate}s ({1/args.rate:.1f} Hz)")
    print()
    print("Accelerometer range: ±16g (±156.9 m/s²)")
    print("Gyroscope range: ±2000 deg/s")
    print()
    print("Expected values when stationary:")
    print("  - |Accel| ≈ 9.8 m/s² (Earth's gravity)")
    print("  - Gyro ≈ 0 deg/s (± small noise)")
    print()
    print("Press Ctrl+C to exit")
    print("-" * 70)
    print()

    try:
        
        # MAIN DATA READING LOOP
        while True:
            # QUERY CONTROLLER - Send CAN request and get response
            # This sends a CAN frame asking for the registers we specified
            # The controller responds with the current sensor values
            result = await controller.query()
            # EXTRACT RAW VALUES - Get data from CAN response
            # result.values is a dictionary: {register_address: value}
            # .get(address, 0) returns the value, or 0 if register not present
            
            # Accelerometer raw counts (from registers 0x072-0x074)
            accel_x_raw = result.values.get(0x072, 0)
            accel_y_raw = result.values.get(0x073, 0)
            accel_z_raw = result.values.get(0x074, 0)
            
            # Gyroscope raw counts (from registers 0x080-0x082)
            gyro_x_raw = result.values.get(0x080, 0)
            gyro_y_raw = result.values.get(0x081, 0)
            gyro_z_raw = result.values.get(0x082, 0)
            
            # CONVERT TO SIGNED - Handle negative values correctly
            # The CAN protocol returns unsigned values (0-65535)
            # But sensor data is signed (-32768 to +32767)
            # We need to convert large unsigned values to negative signed values
            
            accel_x_raw = convert_to_signed(accel_x_raw)
            accel_y_raw = convert_to_signed(accel_y_raw)
            accel_z_raw = convert_to_signed(accel_z_raw)
            
            gyro_x_raw = convert_to_signed(gyro_x_raw)
            gyro_y_raw = convert_to_signed(gyro_y_raw)
            gyro_z_raw = convert_to_signed(gyro_z_raw)

            # CONVERT TO PHYSICAL UNITS - Apply scale factors

            # Raw counts are meaningless without conversion
            # Multiply by scale factor to get real-world measurements
            
            # Accelerometer: counts → m/s²
            # At ±16g range: each count = 0.004786 m/s²
            accel_x_ms2 = accel_x_raw * ACCEL_SCALE
            accel_y_ms2 = accel_y_raw * ACCEL_SCALE
            accel_z_ms2 = accel_z_raw * ACCEL_SCALE

            # Gyroscope: counts → degrees/second
            # At ±2000 dps range: each count = 0.07 deg/s
            gyro_x_dps = gyro_x_raw * GYRO_SCALE
            gyro_y_dps = gyro_y_raw * GYRO_SCALE
            gyro_z_dps = gyro_z_raw * GYRO_SCALE

            # CALCULATE MAGNITUDE - Total acceleration vector length
            # The magnitude tells you the total acceleration regardless of direction
            # When stationary, this should equal gravity (9.8 m/s²)
            # When moving, it's gravity plus motion acceleration
            # Formula: |A| = sqrt(Ax² + Ay² + Az²)
            accel_magnitude = math.sqrt(accel_x_ms2**2 + accel_y_ms2**2 + accel_z_ms2**2)
            print(f"Accelerometer (m/s²): X: {accel_x_ms2:7.3f}  Y: {accel_y_ms2:7.3f}  Z: {accel_z_ms2:7.3f}  |Accel|: {accel_magnitude:.3f}")
            print(f"Gyroscope (deg/s):    X: {gyro_x_dps:7.2f}  Y: {gyro_y_dps:7.2f}  Z: {gyro_z_dps:7.2f}")
            print("-" * 70)

            # Wait before next query
            await asyncio.sleep(args.rate)

    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == '__main__':
    # Run the async main function
    # asyncio.run() handles the event loop setup and cleanup
    asyncio.run(main())
