import os
import asyncio
import yaml
from tapo import ApiClient


class TapoManager:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.client = ApiClient(email, password)
        self.devices = {}  # device_name → tapo object

    async def init_device(self, name, ip, device_type):
        """
        Initialize a device and store it for future use.
        """
        if name not in self.devices:
            if device_type == "bulb":
                device = await self.client.l530(ip)
            elif device_type == "plug":
                device = await self.client.p110(ip)
            elif device_type == "led_strip":
                device = await self.client.l900(ip)
            else:
                raise ValueError(f"Unsupported device type: {device_type}")
            self.devices[name] = device
            print(f"[TapoManager] ✅ Device '{name}' initialized.")

    async def set_device_state(self, name, on=True):
        """
        Turn the device ON or OFF.
        """
        device = self.devices.get(name)
        if device:
            await device.on() if on else await device.off()
            print(f"[TapoManager] {'Turned ON' if on else 'Turned OFF'} '{name}'.")
        else:
            print(f"[TapoManager] ❌ Device '{name}' not found.")

    async def blink(self, name, duration=2):
        """
        Turn the device ON, wait, then OFF.
        """
        await self.set_device_state(name, on=True)
        await asyncio.sleep(duration)
        await self.set_device_state(name, on=False)


def load_config(path="devices.yaml"):
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    devices = config.get("devices", {})
    return devices


async def create_manager_from_config(path="devices.yaml"):
    email = os.getenv("TAPO_EMAIL")
    password = os.getenv("TAPO_PASSWORD")

    if not email or not password:
        raise EnvironmentError("TAPO_EMAIL and TAPO_PASSWORD must be set in environment variables.")

    device_defs = load_config(path)
    manager = TapoManager(email, password)

    for name, cfg in device_defs.items():
        await manager.init_device(name, cfg["ip"], cfg["type"])

    return manager