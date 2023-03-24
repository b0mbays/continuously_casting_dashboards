# Home Assistant - Continuously Casting Dashboards

This custom integration for Home Assistant continuously casts dashboards to Chromecast devices during a specified time window. It ensures that the dashboard is always displayed during the active time window, even if the Chromecast device is accidentally interrupted or disconnected. It will ignore any devices that are currently playing any media/timers/recipes etc.

I'm using this myself for 3 different chromecast devices: Lenovo Smart Display 8 & two 1st Gen Google Nest Hubs.

## Features

- Automatically casts specified Home Assistant dashboards to Chromecast devices.
- Monitors the casting state of each device and resumes casting if interrupted.
- Configurable time window for active casting.
- Configurable casting interval.
- Debug logging support.

## How does it work?

The project uses [CATT](https://github.com/skorokithakis/catt) (cast all the things) to cast the dashboard to your Chromecast compatible device. Home Assistant does offer an in-built casting option but I found this to be unreliable for me and I couldn't get it working properly without paying for a Nabu Casu subscription... Instead, I wanted to host HA externally myself for free. (well, $1 p/year). The guide I used is [here](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1) and I bought a domain for $1 from [here](https://gen.xyz/).

This integration runs in the background on your HA instance, so no external device is required. If you'd prefer to run it on a Raspberry Pi or similiar linux box then you can try out [HA-Pi-Continuously-Cast](https://github.com/b0mbays/ha-pi-continuously-cast)


## Configuration

To configure the integration, add the following to your `configuration.yaml` file:

```yaml
ha-continuous-casting-dashboard:
  logging_level: debug # Optional: Set the logging level (default is 'info')
  cast_delay: 30 # Optional: Time (in seconds) between casting checks (default is 60)
  start_time: "06:30" # Start time of the casting window (format: "HH:MM")
  end_time: "02:00" # End time of the casting window (format: "HH:MM")
  devices:
    "Device Name": "Dashboard URL"
    # Add more devices as needed
    # eg: "Office display": "http://192.168.12.104:8123/office-dashboard/default_view?kiosk"
    # eg: "Kitchen display": "http://192.168.12.104:8123/kitchen-dashboard/default_view?kiosk"
