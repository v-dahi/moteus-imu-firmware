#!/usr/bin/python3 -B

import asyncio
import moteus
from moteus.multiplex import F32

async def main():
    # Query ALL possible encoder registers
    qr = moteus.QueryResolution()
    qr._extra = {
        0x001: F32,  # Motor position
        0x006: F32,  # Absolute position
        0x050: F32,  # Encoder 0
        0x052: F32,  # Encoder 1
        0x054: F32,  # Encoder 2
    }
    
    controller = moteus.Controller(id=1, query_resolution=qr)
    
    print("Scanning all encoder registers...")
    print("Rotate the motor shaft and see which value changes\n")
    
    try:
        while True:
            result = await controller.query()
            
            # Read all encoder registers
            pos_0x001 = result.values.get(0x001, 0.0)
            pos_0x006 = result.values.get(0x006, 0.0)
            pos_0x050 = result.values.get(0x050, 0.0)
            pos_0x052 = result.values.get(0x052, 0.0)
            pos_0x054 = result.values.get(0x054, 0.0)
            
            print(f"0x001 (Motor Pos):    {pos_0x001:8.4f} rev")
            print(f"0x006 (Abs Pos):      {pos_0x006:8.4f} rev")
            print(f"0x050 (Encoder 0):    {pos_0x050:8.4f} rev")
            print(f"0x052 (Encoder 1):    {pos_0x052:8.4f} rev")
            print(f"0x054 (Encoder 2):    {pos_0x054:8.4f} rev")
            print("-" * 50)
            
            await asyncio.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == '__main__':
    asyncio.run(main())
