from .ble_connect import BleData

from custom_components.yamaha_sr_c20a import _LOGGER, DOMAIN as SOUNDBAR_DOMAIN
from homeassistant.components.select import (
    SelectEntity,
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up platform."""
    """Initialize the Soundbar device."""
    devices = []
    soundbar_list = hass.data[SOUNDBAR_DOMAIN]

    for device in soundbar_list:
        _LOGGER.debug("Configured a new SoundbarNumber %s", device.name)
        devices.append(SoundbarLed(hass, device))
    
    async_add_entities(devices)

class SoundbarLed(SelectEntity):
    def __init__(self, hass, DeviceEntity):
        self._state = None
        self._led= None
        self._type = "led"
        self.hass = hass
        self._macAdress = DeviceEntity.macAdress
        self._device_id = DeviceEntity.device_id
        self._name = DeviceEntity.name + '_led' 
        self._pollingAuto = DeviceEntity.pollingAuto
        self._status = 'unint'
        self._attr_current_option = None
        self._attr_options= ["Bright", "Dim", "Off"]


    #Run when added to HASS TO LOAD SOURCES
    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()    

    @property
    def name(self):
        return self._name

    @property
    def type(self):
        return self._type
    
    @property
    def state(self):
        return self._state

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._device_id + "_" + self._type         

    async def async_update(self):
        """Update the Number State."""
        if self._status == 'unint' or self._pollingAuto is True : 
            ble_connect = BleData(self, self.hass, self._macAdress)
            await ble_connect.callDevice()
            if self._status == 'init' :
                if (self._led is not None) :
                    self._state = self._led
                    self._attr_current_option = self._led

    async def async_select_option(self, option: str) -> None:
        """Update the current value."""
        ble_connect = BleData(self, self.hass, self._macAdress)
        if option == 'Bright' :
            await ble_connect.callDevice(["ledBright"])
        elif option == 'Dim' :
            await ble_connect.callDevice(["ledDim"])  
        else :
            await ble_connect.callDevice(["ledOff"])  
        
        self._attr_current_option = option     
        self._state = option
