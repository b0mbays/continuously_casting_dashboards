#HA - Continuously Casting Dashboards

This custom integration for Home Assistant continuously casts dashboards to Chromecast devices during a specified time window. It ensures that the dashboard is always displayed during the active time window, even if the Chromecast device is accidentally interrupted or disconnected. It will ignore any devices that are currently playing any media/timers/recipes etc.

I'm using this myself for 3 different chromecast devices: Lenovo Smart Display 8 & two 1st Gen Google Nest Hubs.

<p align="center">
  <img src="https://i.imgur.com/U63Z7aF.jpg" width=75% height=75%>
</p>
<br/><br/>

Features:
============

- Automatically casts specified Home Assistant dashboards to Chromecast devices.
- Monitors the casting state of each device and resumes casting if interrupted.
- Configurable time window for active casting.
- Configurable casting interval.
- Debug logging support.

<br/><br/>

Requirements: 
============

1. **Home Assistant** (with https [external access setup](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1) required for casting) and the HACS Addon installed.
2. **Trusted network setup** for each Chromecast device to avoid logging in. See guide [here](https://blog.fuzzymistborn.com/homeassistant-and-catt-cast-all-the-things/) and follow the 'Trusted Networks' section half way down. You can either do your entire home network, or individual devices. You can find the IP address for each device by going to Settings -> Device Information -> Technical Information on the device.
3. **ha-catt-fix** setup for your dashboard to keep the display 'awake' and not time out after 10 minutes. Install this from [here](https://github.com/swiergot/ha-catt-fix)

<br/><br/>

Installation
============

### HACS (Recommended)

1. Go to the HACS panel in Home Assistant.
2. Click on the three dots in the top right corner and choose "Custom repositories".
3. Enter `b0mbays/ha-continuously-casting-dashboard` in the "Add custom repository" field, select "Integration" from the "Category" dropdown, and click on the "Add" button.
4. Once the custom repository is added, you can install the integration through HACS. You should see "Continuously Cast Dashboards" in the "Integrations" tab. Click on "Download" to add it to your Home Assistant instance.
5. Restart Home Assistant to load the custom integration.
6. Setup your devices inside the configuration.yaml file, follow the steps from the configuration section below.
4. Restart again to start the integration.

### Manual

1. Copy the `ha_continuous_casting_dashboard` folder into your `custom_components` directory within your Home Assistant configuration directory.
2. Restart Home Assistant to load the custom integration.
3. Configure the integration in your `configuration.yaml` file (see the "Configuration" section below).
4. Restart again to start the integration.

<br/><br/>

How does it work?
============

The project uses [CATT](https://github.com/skorokithakis/catt) (cast all the things) to cast the dashboard to your Chromecast compatible device. Home Assistant does offer an in-built casting option but I found this to be unreliable for me and I couldn't get it working properly without paying for a Nabu Casu subscription... Instead, I wanted to host HA externally myself for free. (well, $1 p/year). The guide I used is [here](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1) and I bought a domain for $1 from [here](https://gen.xyz/).

This integration runs in the background on your HA instance, so no external device is required. If you'd prefer to run it on a Raspberry Pi or similiar linux box then you can try out [HA-Pi-Continuously-Cast](https://github.com/b0mbays/ha-pi-continuously-cast)


<br/><br/>

Configuration
============

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
