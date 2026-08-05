#!/usr/bin/python3 -B

"""
This example reads the raw SPI value from a MA600 encoder 
connected to the Aux2 port (SPI) of a moteus controller with ID #1.
"""

import asyncio
import moteus
from moteus import multiplex as mp

async def main():
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Query MA600 encoder data from moteus controller')
    parser.add_argument('--target', type=int, default=1, help='ID of the target controller')
    moteus.make_transport_args(parser)
    args = parser.parse_args()

    # Create controller
    transport = moteus.get_singleton_transport(args)
    controller = moteus.Controller(id=args.target, transport=transport)

    print(f"Reading MA600 encoder values from Aux2 SPI (controller ID: {args.target}). Press Ctrl+C to exit.")
    print()

    try:
        while True:
            # Query all encoder registers
            to_query = {
                moteus.Register.ENCODER_0_POSITION: mp.F32,  # Raw SPI value
                moteus.Register.ENCODER_2_POSITION: mp.F32,         #check all three encoders and values
                moteus.Register.ENCODER_2_VELOCITY: mp.F32,
            }

            # Query using custom_query
            result = await controller.custom_query(to_query)
            mc_data = result.values

            # Extract values
            raw_spi_value = mc_data.get(80, 0.0)  # Register 80 = ENCODER_0_POSITION
            enc2_position = mc_data.get(84, 0.0)  # Register 84 = ENCODER_2_POSITION
            enc2_velocity = mc_data.get(85, 0.0)  # Register 85 = ENCODER_2_VELOCITY

            CAM_ENC_TO_DEG = 360  # Deg / Revolution
            # Raw SPI value - convert to counts (MA600 is 16-bit)
            raw_spi_counts = int(raw_spi_value * 65536) if raw_spi_value != 0 else 0
            
            encoder_angle_deg = enc2_position * CAM_ENC_TO_DEG
            encoder_velocity_deg_s = enc2_velocity * CAM_ENC_TO_DEG

            print(f"Raw SPI Value: {raw_spi_counts} (revolutions: {raw_spi_value:.6f})")
            print(f"Encoder Position (raw): {enc2_position:.6f} revolutions")
            print(f"Encoder Position (degrees): {encoder_angle_deg:.2f}°")
            print(f"Encoder Velocity (raw): {enc2_velocity:.6f} rev/s")
            print(f"Encoder Velocity (deg/s): {encoder_velocity_deg_s:.2f}°/s")
            print()

            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == '__main__':
    asyncio.run(main())