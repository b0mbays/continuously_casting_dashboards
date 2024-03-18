# Home Assistant - Continuously Casting Dashboards

This custom integration for Home Assistant continuously casts dashboards to Chromecast devices during a specified time window. It ensures that the dashboard is always displayed during the active time window, even if the Chromecast device is accidentally interrupted or disconnected. It will ignore any devices that are currently playing any media/timers/recipes etc.

I'm using this myself for 5 different chromecast devices: Lenovo Smart Display 8 & four 1st Gen Google Nest Hubs.

## Features

- Automatically casts specified Home Assistant dashboards to Chromecast devices.
- Monitors the casting state of each device and resumes casting if interrupted.
- Entity changed dashboard casting (cast specific dashboards when an entity state changes).
- Configurable global time window for active casting.
- Configurable casting interval.
- Configurable volume per device.
- Configurable start and end times per device.
- Google Home Speaker Group support.
- Debug logging support.
Please visit the [Github README](https://github.com/b0mbays/ha-continuously-casting-dashboard) for more information.