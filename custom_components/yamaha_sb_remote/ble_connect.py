import asyncio
from bleak import BleakScanner, BleakClient, BleakError
import logging
from homeassistant.components import bluetooth
from .utils import *

_LOGGER = logging.getLogger(__name__)

class BleData:
    def __init__(self, device, hass, macAdress):
        self.hass = hass
        self.macAdress = macAdress
        self.device = device

    def handle_data(self, handle, value):
        _LOGGER.debug("Received data: %s" % (value.hex()))
        if len(value) > 3:
            length = value[2]
            if value[0] != 0xcc:
                _LOGGER.warning("Bad first bit: 0x%s" % (value.hex()))
            elif value[1] != 0xaa:
                _LOGGER.warning("Bad second bit: 0x%s" % (value.hex()))
            elif not checksum_byte(value):
                _LOGGER.warning("Bad checksum in data: 0x%s" % (value.hex()))
            elif (len(value) - 4) != length:
                _LOGGER.warning("Bad value for data length: 0x%s" % (value.hex()))
            else:
                if length == 14:  # this should be a status message
                    self.device = set_by_hex(int(value.hex(), 16), self.device)
                elif length == 2:
                    _LOGGER.debug("Received: " + interpret_message(value))
                elif length == 3:
                    _LOGGER.debug("Received: " + interpret_message(value))
                elif length == 5:
                    _LOGGER.debug("Received: " + interpret_message(value))
                else:
                    _LOGGER.warning("Received unexpected data length: 0x%s" % (value.hex()))
        elif value.hex() == "":
            _LOGGER.debug("Received empty data packet, this is expected once on startup")
        else:
            _LOGGER.warning("Received data that is not an expected message size: 0x%s" % (value.hex()))
        if handle != 0x8:
            _LOGGER.debug("Bad handle: %s" % str(handle))

    async def callDevice(self, command=None, retries=3, attempt=0):
        # Sends a BLE command to the device with retry logic and delays to prevent saturation.
        request = create_command_code(['request'], self.device)
        bleDevice = bluetooth.async_ble_device_from_address(self.hass, self.macAdress, connectable=True)
        try:
            async with BleakClient(bleDevice) as adapter:
                await adapter.start_notify('5cafe9de-e7b0-4e0b-8fb9-2da91a7ae3ed', self.handle_data)
                await adapter.write_gatt_char("0c50e7fa-594c-408b-ae0d-b53b884b7c08", request)
                
                # Log: initial request command sent successfully
                _LOGGER.debug("Initial request command sent successfully")
                
                # Wait for device initialization
                while self.device._status == 'unint':
                    _LOGGER.debug("WAIT FOR notify handle : " + self.device._status)
                    await asyncio.sleep(0.06)
                
                # Added delay after request to avoid BLE saturation
                await asyncio.sleep(0.3)
                
                if command is None:
                    return
                else:
                    _LOGGER.info("Sending BLE command: " + command[0])
                    code = create_command_code(command, self.device)
                    await adapter.write_gatt_char("0c50e7fa-594c-408b-ae0d-b53b884b7c08", code)
                    # Added delay after sending command to prevent rapid re-connections
                    await asyncio.sleep(1)
                    # Log: custom command sent successfully
                    _LOGGER.info("BLE command '%s' sent successfully", command[0])
        except Exception as err:
            # Handling ESP_GATT_CONN_FAIL_ESTABLISH and Disconnected errors by retrying the connection and command
            if ("ESP_GATT_CONN_FAIL_ESTABLISH" in str(err) or "Disconnected" in str(err)) and retries > 0:
                _LOGGER.error("Error detected (%s), retrying in 0.5s. Remaining retries: %d, attempt: %d", str(err), retries, attempt+1)
                await asyncio.sleep(0.5)
                return await self.callDevice(command, retries=retries-1, attempt=attempt+1)
            else:
                _LOGGER.error("Error sending BLE command: %s", err)
                await asyncio.sleep(0.5)
