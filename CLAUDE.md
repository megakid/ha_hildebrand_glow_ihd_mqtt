# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Hildebrand Glow IHD (In-Home Display) devices that connects via local MQTT. The integration allows Home Assistant users to monitor smart meter data (electricity and gas consumption) from their Hildebrand Glow devices without relying on cloud services.

## Architecture

- **Integration Type**: Home Assistant Custom Component (HACS-compatible)
- **Communication**: Local MQTT subscription to Glow device topics
- **Platform**: Sensor platform only (creates multiple sensor entities)
- **Configuration**: Uses Home Assistant's config flow system with UI-based setup

### Core Components

- `__init__.py`: Main integration setup, handles Home Assistant version checking and entry management
- `config_flow.py`: UI configuration flow with device ID, topic prefix, and timezone settings
- `sensor.py`: Main sensor platform implementing MQTT-based sensors for electricity and gas meters
- `const.py`: Constants including sensor definitions, meter intervals, and configuration keys
- `manifest.json`: Integration metadata (dependencies: mqtt, version info)

### Key Architecture Patterns

- **MQTT Topic Structure**: `{topic_prefix}/{device_id}/STATE` and `{topic_prefix}/{device_id}/SENSOR/{metertype}`
- **Device ID Handling**: Supports wildcards ("+") for auto-detection of multiple devices
- **Sensor Categories**: STATE sensors (device info, connectivity) and METER sensors (energy consumption data)
- **Timezone Handling**: Separate timezone configuration for electricity and gas meters using zoneinfo

## Data Model

The integration processes two main MQTT message types:

1. **STATE Messages**: Device status, software version, connectivity metrics, battery state
2. **SENSOR Messages**: Energy consumption data with cumulative/interval readings, power values, pricing info

## Development Commands

This project has no build system, linting, or testing infrastructure. Development involves:

- **Installation**: Copy `custom_components/hildebrand_glow_ihd_mqtt/` to Home Assistant's custom_components directory
- **Testing**: Manual testing within Home Assistant environment with actual Glow devices
- **Validation**: Home Assistant's built-in integration validation during startup

## Configuration Schema

The integration accepts:
- `device_id`: MAC address or "+" for auto-detection
- `topic_prefix`: MQTT topic prefix (default: "glow") 
- `time_zone_electricity`: Timezone for electricity meter timestamps
- `time_zone_gas`: Timezone for gas meter timestamps

## Important Notes

- Requires Home Assistant 2024.12.0+ (enforced in `__init__.py:25-32`)
- Depends on Home Assistant's MQTT integration being configured first
- Creates sensors dynamically based on MQTT messages received from Glow devices
- Handles both SMETS1 and SMETS2 smart meter data formats