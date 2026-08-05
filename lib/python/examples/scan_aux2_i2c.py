#!/usr/bin/python3
import asyncio
import moteus

async def main():
    transport = moteus.get_singleton_transport([])
    controller = moteus.Controller(id=1, transport=transport)

    print("Scanning Aux2 I2C addresses...")
    found = []
    for addr in range(0x03, 0x78):
        try:
            result = await controller.query(aux_i2c=(2, addr, b''))
            # If no exception, device responded
            found.append(addr)
        except Exception:
            continue

    if found:
        print(f"Found I2C devices at addresses: {[hex(a) for a in found]}")
    else:
        print("No devices detected on Aux2 I2C.")

if __name__ == "__main__":
    asyncio.run(main())
