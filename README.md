# <center>**HA - Continuously Casting Dashboards** </center>

<p align="center">
  <img src="branding/logo.png" width=15% height=20%>
</p>

This custom integration for Home Assistant continuously casts dashboards to Chromecast devices during a specified time window. It ensures that the dashboard is always displayed during the active time window, even if the Chromecast device is accidentally interrupted or disconnected. It will ignore any devices that are currently playing Spotify, Netflix, Recipes etc. Timers will be overtaken by the dashboard but will continue to operate in the background.

I'm using this myself for 5 chromecast devices: Lenovo Smart Display 8 & four 1st Gen Google Nest Hubs.

<p align="center">
  <img src="https://github.com/b0mbays/continuously_casting_dashboards/assets/55556007/9cc32333-312e-41cf-bca0-e531e535a268" width=75% height=75%>
</p>
<br/><br/>

# ✨**Features:**

* Automatically casts specified Home Assistant dashboards to Chromecast devices.
* Monitors the casting state of each device and resumes casting if interrupted.
* Custom entity states for when to cast a dashboard (both globally and individual dashboards)
* Multiple dashboard casting for the same device (cast different dashboards at different times).
* Configurable global time window for active casting.
* Configurable casting interval.
* Configurable volume per device.
* Configurable start and end times per device.
* Google Home Speaker Group support.
* **Exposes sensors for configuring and viewing global settings:**

  * `sensor.cast_delay`
  * `sensor.start_time`
  * `sensor.end_time`
  * `sensor.control_entity`
  * `sensor.required_entity_state`

  These sensors can be set via services. For example:

  ```yaml
  action: continuously_casting_dashboards.set_cast_delay
  target:
    entity_id: sensor.cast_delay
  data:
    value: 60
  ```

<br/><br/>

# ✅ **Requirements:**

1. **Home Assistant**

2. **[HTTPS External Access](https://www.makeuseof.com/secure-home-assistant-installation-free-ssl-certificate/?newsletter_popup=1)** which HA requires for casting and the HACS Addon installed. **Alternatively, if you have a Nabu Casa subscription then this is already set up for you.**

   * *This **does** work without external access if you are behind a valid SSL cert locally*

3. **Trusted network setup** for each Chromecast device to avoid logging in. See guide [here](https://blog.fuzzymistborn.com/homeassistant-and-catt-cast-all-the-things/) and follow the 'Trusted Networks' section.

   ```yaml
   homeassistant:
     external_url: "<your-external-url-for-home-assistant>"
     auth_providers:
       - type: trusted_networks
         trusted_networks:
           - 192.168.12.236/32
           - 192.168.12.22/32
           - 192.168.12.217/32
         trusted_users:
           192.168.12.236: <your-user-id>
           192.168.12.22: <your-user-id>
           192.168.12.217: <your-user-id>
         allow_bypass_login: true
       - type: homeassistant
   ```

4. **[ha-catt-fix](https://github.com/swiergot/ha-catt-fix)** setup to keep the display 'awake'.

5. **[Kiosk Mode](https://github.com/NemesisRE/kiosk-mode)** for fullscreen dashboards.

<br/><br/>

# 🚀**Installation**

### **HACS**

1. Go to the HACS panel in Home Assistant.
2. Click on the three dots > "Custom repositories".
3. Enter `b0mbays/continuously_casting_dashboards`, select "Integration" and click "Add".
4. Install via the Integrations tab.
5. Restart Home Assistant.
6. Setup devices in `configuration.yaml` or via UI.

<br/><br/>

# 🔧**How does it work?**

This integration uses [CATT](https://github.com/skorokithakis/catt) to check the state of each Chromecast every 45 seconds (configurable). If no media is playing, it re-casts the dashboard. Media like YouTube/Spotify will be ignored.

HTTPS is required. Either via your own SSL setup or with Nabu Casa.

<br/><br/>

# 🏠**Configuration**

### UI Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for "Continuously Casting Dashboards".
3. Follow the prompts to configure global and per-device settings.

### YAML Configuration

```yaml
continuously_casting_dashboards:
  logging_level: warning
  cast_delay: 45
  start_time: "07:00"
  end_time: "01:00"
  switch_entity_id: input_boolean.global_ccd_cast
  switch_entity_state: on
  devices:
    "Office display":
      - dashboard_url: "http://192.168.12.104:8123/nest-dashboard/default_view?kiosk"
        volume: 7
        start_time: "06:00"
        end_time: "18:00"
    "Kitchen display":
      - dashboard_url: "http://192.168.12.104:8123/kitchen-dashboard/default_view?kiosk"
        volume: 9
        start_time: "06:00"
        end_time: "22:00"
```

<br/><br/>

# **↕️ Multiple dashboard casting**

You can cast different dashboards to the same device at different times:

```yaml
"Office display":
  - dashboard_url: "http://192.168.12.104:8123/day-dashboard/default_view?kiosk"
    start_time: "07:00"
    end_time: "23:59"
  - dashboard_url: "http://192.168.12.104:8123/night-dashboard/default_view?kiosk"
    start_time: "00:01"
    end_time: "03:00"
```

<br/><br/>

# **🎮 Casting based on entity states**

Create an entity to control global casting:

```yaml
input_boolean:
  global_ccd_cast:
    name: "CCD Global Casting"
    initial: on
```

And reference it in your integration:

```yaml
continuously_casting_dashboards:
  switch_entity_id: input_boolean.global_ccd_cast
```

You can also use custom entity states:

```yaml
continuously_casting_dashboards:
  switch_entity_id: sensor.presence_mode
  switch_entity_state: home
```

Or per-dashboard states:

```yaml
"Living Room Display":
  - dashboard_url: "http://192.168.1.10:8123/lovelace/dashboard?kiosk"
    switch_entity_id: sensor.living_room_mode
    switch_entity_state: entertainment
```

<br/><br/>

# ️⚠️**Troubleshooting**

* **DashCast notification on Android:**

  > Go to Settings > Google > All Services > Devices & sharing > Cast options > Turn off media controls.

* **Dashboard stops casting quickly:**

  > Likely ha-catt-fix isn't working. Set logging to `debug` and check logs for the state output. It should show `Dummy`.

```text
DEBUG (MainThread) [custom_components.continuously_casting_dashboards.dashboard_caster] Status output for Office display when checking for dashboard state 'Dummy': Title: Dummy
```
