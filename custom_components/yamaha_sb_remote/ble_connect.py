import asyncio
import logging

from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    close_stale_connections,
    close_stale_connections_by_address,  # fallback
)
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
        """Send a BLE command to the device with robust connection and bounded retries."""
        request = create_command_code(['request'], self.device)

        # Resolve the BLE device via HA's bluetooth integration
        bleDevice = bluetooth.async_ble_device_from_address(
            self.hass, self.macAdress, connectable=True
        )

        try:
            # Helpful on some stacks (e.g. BlueZ) to avoid lingering "ghost" connections
            if bleDevice is not None:
                await close_stale_connections(bleDevice)
            else:
                await close_stale_connections_by_address(self.macAdress)  # Fallback

            # Use bleak-retry-connector for a reliable connection and service cache
            target = bleDevice if bleDevice is not None else self.macAdress
            adapter = await establish_connection(
                BleakClientWithServiceCache,
                target,  # can be a BLEDevice or a MAC address
                name=getattr(self.device, "_name", "Yamaha Soundbar"),
                # Keep connector-level attempts small; we also have an outer retry
                max_attempts=3,
            )

            try:
                # Subscribe to notifications so the device status gets updated
                await adapter.start_notify(
                    "5cafe9de-e7b0-4e0b-8fb9-2da91a7ae3ed", self.handle_data
                )

                # Send initial "request" to prime state
                await adapter.write_gatt_char(
                    "0c50e7fa-594c-408b-ae0d-b53b884b7c08", request
                )
                _LOGGER.debug("Initial request command sent successfully")

                # Wait for device to finish initialization (status set via notifications)
                while self.device._status == "unint":
                    _LOGGER.debug("WAIT FOR notify handle: %s", self.device._status)
                    await asyncio.sleep(0.06)

                # Small delay to avoid saturating the BLE stack
                await asyncio.sleep(0.3)

                # If no additional command to send, we're done
                if command is None:
                    return

                # Send the requested command
                _LOGGER.info("Sending BLE command: %s", command[0])
                code = create_command_code(command, self.device)
                await adapter.write_gatt_char(
                    "0c50e7fa-594c-408b-ae0d-b53b884b7c08", code
                )

                # Brief delay to prevent rapid reconnect cycles after commands
                await asyncio.sleep(1)
                _LOGGER.info("BLE command '%s' sent successfully", command[0])

            finally:
                # Always attempt a clean disconnect; ignore teardown errors
                try:
                    await adapter.disconnect()
                except Exception:
                    pass

        except Exception as err:
            # App-level retry in addition to the connector's internal attempts
            if (
                ("ESP_GATT_CONN_FAIL_ESTABLISH" in str(err) or "Disconnected" in str(err))
                and retries > 0
            ):
                _LOGGER.debug(
                    "Error detected (%s), retrying in 0.5s. Remaining retries: %d, attempt: %d",
                    str(err), retries, attempt + 1,
                )
                await asyncio.sleep(0.5)
                return await self.callDevice(
                    command, retries=retries - 1, attempt=attempt + 1
                )
            else:
                _LOGGER.error("Error sending BLE command: %s", err)
                await asyncio.sleep(0.5)
