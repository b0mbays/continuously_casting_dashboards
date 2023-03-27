# <center>**HA - Continuously Casting Dashboards** </center>

<p align="center">
  <img src="branding/logo.png" width=15% height=20%>
</p>


This custom integration for Home Assistant continuously casts dashboards to Chromecast devices during a specified time window. It ensures that the dashboard is always displayed during the active time window, even if the Chromecast device is accidentally interrupted or disconnected. It will ignore any devices that are currently playing any media/timers/recipes etc.

I'm using this myself for 3 different chromecast devices: Lenovo Smart Display 8 & two 1st Gen Google Nest Hubs.

<p align="center">
  <img src="https://i.imgur.com/U63Z7aF.jpg" width=75% height=75%>
</p>
<br/><br/>

✨**Features:**
============

- Automatically casts specified Home Assistant dashboards to Chromecast devices.
- Monitors the casting state of each device and resumes casting if interrupted.
- Configurable time window for active casting.
- Entity changed dashboard casting (cast specific dashboards when an entity state changes).
- Configurable casting interval.
- Debug logging support.

<br/><br/>

✅ **Requirements:**
============

1. **Home Assistant** (with https [external access setup](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1) required for casting) and the HACS Addon installed.

2. **Trusted network setup** for each Chromecast device to avoid logging in. See guide [here](https://blog.fuzzymistborn.com/homeassistant-and-catt-cast-all-the-things/) and follow the 'Trusted Networks' section half way down. You can either do your entire home network, or individual devices. You can find the IP address for each device by going to Settings -> Device Information -> Technical Information on the device.

3. **[ha-catt-fix](https://github.com/swiergot/ha-catt-fix)** setup for your dashboard to keep the display 'awake' and not time out after 10 minutes. Install steps:

    - Go to the HACS panel in Home Assistant
    - Click on the three dots in the top right corner and choose "Custom repositories"
    - Enter `swiergot/ha-catt-fix` in the "Add custom repository" field, select "Lovelace" from the "Category" dropdown, and click on the "Add" button.
    - Go to the "Frontend" tab within HACS, and click on 'Explore and download repositories" and search for 'ha-catt-fix'.
    - Click "Download"
    - Restart Home Assistant
    - Ensure that 'ha-catt-fix' is listed inside your dashboards resources. (_Your dashboard_ -> Three dots -> Edit -> Three dots -> Manage resources)


<br/><br/>

🚀**Installation**
============

### **HACS (Recommended)**

1. Go to the HACS panel in Home Assistant.
2. Click on the three dots in the top right corner and choose "Custom repositories".
3. Enter `b0mbays/continuously_casting_dashboards` in the "Add custom repository" field, select "Integration" from the "Category" dropdown, and click on the "Add" button.
4. Once the custom repository is added, you can install the integration through HACS. You should see "Continuously Cast Dashboards" in the "Integrations" tab. Click on "Download" to add it to your Home Assistant instance.
5. Restart Home Assistant to load the custom integration.
6. Setup your devices inside the configuration.yaml file, follow the steps from the configuration section below.
4. Restart again to start the integration.

### **Manual**

1. Copy the `ha_continuous_casting_dashboard` folder into your `custom_components` directory within your Home Assistant configuration directory.
2. Restart Home Assistant to load the custom integration.
3. Configure the integration in your `configuration.yaml` file (see the "Configuration" section below).
4. Restart again to start the integration.

<br/><br/>

⚡️**How does it work?**
============

This integration runs in the background on your HA instance, so no external device is required. If you'd prefer to run it on a Raspberry Pi or similiar linux box then you can try out [HA-Pi-Continuously-Cast](https://github.com/b0mbays/ha-pi-continuously-cast). However, I have had no issues running this on my Home Assistant instance.

The integration uses [CATT's](https://github.com/skorokithakis/catt) functionality to 'call' each of your Google Chromecast devices checking the status every 45 seconds (you can change this in the config) for any 'state' changes. If there is no media playing on the device, then the dashboard will be cast. If the device already has the dashboard casting then it will be ignored. And if there is youtube/recipes/spotfy playing on the device then it will also be ignored.

The casting functionality within Home Assistant requires your instance to be accesible via HTTPS with either paying for a Nabu Casu subscription or setting this up yourself. Home Assistant does offer an in-built casting option but I found this to be unreliable for me and I couldn't get it working properly without paying for a Nabu Casu subscription... Instead, I wanted to host HA externally myself for free. (well, $1 p/year). The guide I used is [here](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1) and I bought a domain for $1 from [here](https://gen.xyz/).


<br/><br/>

⚙️**Configuration**
============

To configure the integration, add the following to your `configuration.yaml` file:

```yaml
ha-continuous-casting-dashboard:
  logging_level: warning #Required: Set the logging level - debug/info/warning (default is 'warning' - try 'debug' for debugging)
  cast_delay: 45 #Required: Time (in seconds) for casting checks between devices
  start_time: "06:30" #Required: Start time of the casting window (format: "HH:MM")
  end_time: "02:00" #Required: End time of the casting window (format: "HH:MM") and must be after "00:00"
  devices:
    "<Display_Name": #Required: Display name of your device. Find this under device settings -> Information -> Device Name
        dashboard_url: "<Dashboard_URL>" #Required: Dashboard URL to be casted
    "<Display_Name": 
        dashboard_url: "<Dashboard_URL>" 

    #You can then add more devices repeating the above format

    # Examples:
    # "Office display":
    #   dashboard_url: "http://192.168.12.104:8123/nest-dashboard/default_view?kiosk"
    # "Kitchen display":
    #   dashboard_url: "http://192.168.12.104:8123/kitchen-dashboard/default_view?kiosk"
    # "Basement display":
    #   dashboard_url: "http://192.168.12.104:8123/nest-dashboard/default_view?kiosk"
```


<br/><br/>
**🔄 Entity changed dashboard casting**
============


With this feature, you can configure specific dashboards to be cast when the state of a specified entity changes. To enable this feature, add a new section to your configuration.yaml file:

```yaml
ha-continuous-casting-dashboard:
  # ...
  state_triggers:
    "<Display_Name>"
        - entity_id: "<Entity_ID>"
          to_state: "<To_State>"
          dashboard_url: "<Dashboard_URL>"
          time_out: <Timeout_time> #Optional!
```

Replace **<Display_Name>** with the Chromecast device, **<Entity_ID>** with the desired entity ID, **<To_State>** with the state that triggers the casting and **<Dashboard_URL>** with the URL of the dashboard you want to cast.

**<Timeout_time>** is an optional field to "time out" a specific dashboard after a certain amount of time(in seconds). There is an example use case below.

You can add multiple entity-triggered casting configurations by adding more sections following the same format.

Example:

```yaml
ha-continuous-casting-dashboard:
  # ...
  state_triggers:
    "Living room display"
        - entity_id: "sensor.samsung_tv"
          to_state: "On"
          dashboard_url: "http://192.168.12.104:8123/tv_remote_dashboard/default_view?kiosk"
        - entity_id: "sensor.samsung_tv"
          to_state: "Off"
          dashboard_url: "http://192.168.12.104:8123/living_room_dashboard/default_view?kiosk"
```
The first example for the "Living room display" will cast my custom "tv_remote_dashboard" which has my TV remote controls to my Nest Hub when my TV entity reports the status of "On". When the TV turns off and now reports a status of "Off" then my normal "living_room_dashboard" will be casted.

```yaml
ha-continuous-casting-dashboard:
  # ...
  state_triggers:
    "Office display"
        - entity_id: "binary_sensor.front_door_ring"
          to_state: "Detected"
          dashboard_url: "http://192.168.12.104:8123/cctv_dashboard/default_view?kiosk"
          time_out: 60
```


The second example will cast my custom "cctv_dashboard" which has cameras of the front door when my Ring doorbell is "Detected". I am using the optional "time_out" feature which will stop casting the CCTV display after 60 seconds. Once the dashboard has then stopped casting, the default dashboard will start casting to this display.

<br/><br/>

⚠️**Troubleshooting**
============

- The dashboard starts on my device and then stops within a few seconds.

    If this is happening, you may not have installed the ha-catt-fix correctly and your device will be using a different state name for when a dashboard is "active". The device should be reporting "Dummy". You can find out what your device is reporting by changing the "logging_level" to "debug"; then going to the Home Assistant logs and you will see logs for this integration. In the logs you should find a log checking the status output for a working dashboard state. For example, mine looks like this:


    ```
    DEBUG (MainThread) [custom_components.ha-continuous-casting-dashboard.dashboard_caster] Status output for Office display when checking for dashboard state 'Dummy': Title: Dummy 22:27:13 GMT+0000 (Greenwich Mean Time)
    Volume: 50
    ```

    If "Dummy" is missing here, please ensure you have installed the ha-catt-fix correctly from following the instructions from the [requirements](#requirements) section.
