#!/usr/bin/python3 -B

"""
Read IMU data (accelerometer + gyroscope) and encoder positions from moteus controller.

This script reads 8 values total:
- Accelerometer X, Y, Z (in m/s²)
- Gyroscope X, Y, Z (in degrees/second)
- MA600 external encoder position (in revolutions)
- Onboard AS5047P encoder position (in revolutions)

Hardware Setup:
- LSM6DSV16X IMU on AUX1 I2C (Type 5 mode)
- MA600 encoder on AUX2 SPI
- Onboard AS5047P encoder on AUX1 SPI

Configuration Required for IMU:
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.type 5"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.i2c.devices.0.address 107"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.2.mode 13"
    python3 -m moteus.moteus_tool --target 1 -c "conf set aux1.pins.3.mode 13"
    python3 -m moteus.moteus_tool --target 1 -c "conf write"

Configuration for MA600 (AUX2 SPI):
    aux2.spi.mode = 5  # ma600
    motor_position.sources.0.aux_number = 2
    motor_position.sources.0.type = 1

Configuration for Onboard Encoder (AUX1 SPI):
    motor_position.sources.1.aux_number = 1
    motor_position.sources.1.type = 1
"""

import asyncio
import math
import moteus

# Import data type constants
from moteus.multiplex import INT16, F32

# SCALE FACTORS - Convert raw sensor counts to physical units

# Accelerometer scale factor:
# - IMU configured for ±16g full scale range
# - 16-bit ADC: -32768 to +32767 counts
# - Scale: 16g / 32768 counts = 0.000488 g/count
# - Convert to SI: 0.000488 g/count × 9.80665 m/s²/g = 0.004786 m/s²/count
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
    Example: 64977 (unsigned) = -558 (signed)
    
    Args:
        value: Unsigned integer from register (0-65535)
    
    Returns:
        Signed integer (-32768 to +32767)
    """
    if value > 32767:
        return value - 65536
    return value


async def main():
    # COMMAND LINE ARGUMENTS

    import argparse
    parser = argparse.ArgumentParser(
        description='Read IMU and encoder data from moteus controller'
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

    # QUERY SETUP - Define which registers to read
    # QueryResolution defines what data to request from the controller
    qr = moteus.QueryResolution()
    
    # _extra is a dictionary of custom registers to query
    # Key = register address (hex), Value = data type
    qr._extra = {
        # IMU Accelerometer (Type 5 custom firmware)
        0x072: INT16,  # Accel X - raw int16 value
        0x073: INT16,  # Accel Y - raw int16 value
        0x074: INT16,  # Accel Z - raw int16 value
        
        # IMU Gyroscope (Type 5 custom firmware)
        0x080: INT16,  # Gyro X - raw int16 value
        0x081: INT16,  # Gyro Y - raw int16 value
        0x082: INT16,  # Gyro Z - raw int16 value
        
        # Encoders
        0x001: F32,    # Motor position (MA600 from AUX2 SPI)
        0x006: F32,    # Absolute position (Onboard AS5047P from AUX1 SPI)
    }

    # CONTROLLER CONNECTION
    # Get the CAN transport (handles USB adapter, socketcan, etc.)
    transport = moteus.get_singleton_transport(args)
    
    # Create controller object for the specified device ID
    controller = moteus.Controller(
        id=args.target,              # Which controller to talk to (CAN ID)
        query_resolution=qr,         # What data to request
        transport=transport           # How to communicate (CAN bus)
    )

    # DISPLAY STARTUP INFO
    print(f"Reading IMU and encoders from controller {args.target}")
    print(f"Update rate: {args.rate}s ({1/args.rate:.1f} Hz)")
    print()
    print("Sensors:")
    print("  - LSM6DSV16X IMU (6-axis): Accel ±16g, Gyro ±2000 deg/s")
    print("  - MA600 encoder (AUX2 SPI): External position measurement")
    print("  - AS5047P encoder (AUX1 SPI): Onboard motor shaft position")
    print()
    print("Expected values when stationary:")
    print("  - |Accel| ≈ 9.8 m/s² (Earth's gravity)")
    print("  - Gyro ≈ 0 deg/s (± small noise)")
    print()
    print("Press Ctrl+C to exit")
    print("=" * 80)
    print()

    try:
        # MAIN DATA READING LOOP
        while True:
            # QUERY CONTROLLER - Send CAN request and get response
            # This sends a CAN frame asking for the registers we specified
            # The controller responds with the current sensor values
            result = await controller.query()

            # EXTRACT IMU DATA

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
            # Convert large unsigned values to negative signed values
            
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
            accel_x = accel_x_raw * ACCEL_SCALE
            accel_y = accel_y_raw * ACCEL_SCALE
            accel_z = accel_z_raw * ACCEL_SCALE

            # Gyroscope: counts → degrees/second
            gyro_x = gyro_x_raw * GYRO_SCALE
            gyro_y = gyro_y_raw * GYRO_SCALE
            gyro_z = gyro_z_raw * GYRO_SCALE

            # CALCULATE MAGNITUDE - Total acceleration vector length
            # When stationary, this should equal gravity (9.8 m/s²)
            # Formula: |A| = sqrt(Ax² + Ay² + Az²)
            accel_mag = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)

            # MA600 encoder (motor position register 0x001)
            # Reads from AUX2 SPI (configured as motor_position.sources.0)
            ma600_position_rev = result.values.get(0x001, 0.0)
            
            # Onboard AS5047P encoder (absolute position register 0x006)
            # Reads from AUX1 SPI (internal motor shaft encoder)
            onboard_position_rev = result.values.get(0x006, 0.0)
            
            # Convert encoder positions from revolutions to degrees
            ma600_position_deg = ma600_position_rev * 360.0
            onboard_position_deg = onboard_position_rev * 360.0

            print(f"IMU Accelerometer (m/s²): X: {accel_x:7.3f}  Y: {accel_y:7.3f}  Z: {accel_z:7.3f}  |Accel|: {accel_mag:6.3f}")
            print(f"IMU Gyroscope (deg/s):    X: {gyro_x:7.2f}  Y: {gyro_y:7.2f}  Z: {gyro_z:7.2f}")
            print(f"MA600 Encoder (deg):      Position: {ma600_position_deg:7.2f}°")
            print(f"Onboard Encoder (deg):    Position: {onboard_position_deg:7.2f}°")
            print("=" * 80)

            # Wait before next query (don't spam the controller)
            await asyncio.sleep(args.rate)

    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == '__main__':
    # Run the async main function
    asyncio.run(main())
