# hildebrand_glow_ihd
Hildebrand Glow IHD Local MQTT Home Assistant integration

Inspired and heavily based on [@robertalexa](https://github.com/robertalexa) forum thread here: https://community.home-assistant.io/t/glow-hildebrand-display-local-mqtt-access-template-help/428638

# Guide

## Installation & Usage

1. Install MQTT Addon (https://home-assistant.io/components/mqtt/) - required for this integration to work
2. Buy a Hildebrand Glow IHD device (https://shop.glowmarkt.com/products/display-and-cad-combined-for-smart-meter-customers)
3. Follow this blog post to connect the Hildebrand Glow IHD device (https://medium.com/@joshua.cooper/glow-local-mqtt-f69b776b7af4)
4. Add repository to HACS (see https://hacs.xyz/docs/faq/custom_repositories) - use "https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt" as the repository URL.
5. Install the `hildebrand_glow_ihd_mqtt` integration inside HACS
6. Restart HA
7. Add Hildebrand Glow IHD MQTT integration using the normal HA integration configuration screen - note if you leave the Device ID as '+' it will automatically detect all Hildebrand Glow IHD devices publishing to your MQTT - this is the recommended way.
8. Your various `sensor`s will be named something like `sensor.smart_meter...` grouped as devices.

![image](https://user-images.githubusercontent.com/1478003/173249987-4724af89-ceaa-4422-a426-4b8a2b16d98e.png)


## Electricity cost with changing tariffs

`Smart Meter Electricity: Cost (Today)` accumulates each increase in daily
consumption at the previously observed unit rate, plus the current standing
charge. A new tariff therefore applies to subsequent consumption instead of
repricing the whole day's usage. The accumulator and meter-day reset are
restored after a Home Assistant restart.

On first use without saved history, or on the first reading of a new meter day,
consumption already recorded that day is valued at the current rate. The
`cost_estimated` attribute marks this initial estimate when consumption is
non-zero. This attribute is not an accuracy guarantee: rate changes between
messages or while Home Assistant is offline cannot be reconstructed; usage
across such gaps is valued at the last observed rate. This sensor is an estimate,
not a replacement for supplier billing.

Null or invalid prices/readings produce `unknown` without discarding the last
valid accumulator. Missing fields or timestamps leave the previous state intact.
Out-of-order readings are ignored; a decreasing daily counter within the same
meter day produces `unknown` until it catches up, avoiding double counting.
The configured electricity meter timezone controls the daily reset.
