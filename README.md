# hildebrand_glow_ihd
Hildebrand Glow IHD Local MQTT Home Assistant integration

# Guide

## Installation & Usage

1. Install MQTT Addon (https://home-assistant.io/components/mqtt/) - required for this integration to work
2. Buy a Hildebrand Glow IHD device (https://shop.glowmarkt.com/products/display-and-cad-combined-for-smart-meter-customers)
3. Follow this blog post to connect the Hildebrand Glow IHD device (https://medium.com/@joshua.cooper/glow-local-mqtt-f69b776b7af4)
4. Add repository to HACS (see https://hacs.xyz/docs/faq/custom_repositories) - use "https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt" as the repository URL.
3. Install the `hildebrand_glow_ihd_mqtt` integration inside HACS
5. If you only have ONE IHD then in your HA `configuration.yaml`, add the following:
```yaml
sensors:
  - platform: hildebrand_glow_ihd_mqtt
```
6. Restart HA
7. Your various `sensor` will be named something like `sensor.smart_meter...`


If you have more than one device (for some reason) then you will need to pick one:
```yaml
sensors:
  - platform: hildebrand_glow_ihd_mqtt
    device_id: 1234ABC31234 [the mac address of your Hildebrand Glow IHD device - see step 3]
```