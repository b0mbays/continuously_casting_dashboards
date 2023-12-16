After updating to 1.3.0 you will need to update your devices configuration.

Please make the following change to add a '-' to each of your dashboard_url's for each device:

Existing:

```yaml
continuously_casting_dashboards:
  ...
  devices:
    "<Display_Name>": #Required: Display name of your device. Find this on the actual device's settings or inside the Google Home app.
        dashboard_url: "<Dashboard_URL>" #Required: Dashboard URL to be casted (This must be the local IP address of your HA instance, not homeassistant.local)
        volume: 5 #Optional: Volume to set the display. (If you remove this, the device will remain the same volume)
        start_time: "07:00" #Optional: Set the start time for this device
        end_time: "01:00" #Optional: Set the end time for this device
    "<Display_Name>": 
        dashboard_url: "<Dashboard_URL>" 
        volume: <Volume>
        start_time: "<Start_Time>" 
        end_time: "<End_Time>"
```

New:

```yaml
continuously_casting_dashboards:
  ...
  devices:
    "<Display_Name>": #Required: Display name of your device. Find this on the actual device's settings or inside the Google Home app.
      - dashboard_url: "<Dashboard_URL>" #Required: Dashboard URL to be casted (This must be the local IP address of your HA instance, not homeassistant.local)
        volume: 5 #Optional: Volume to set the display. (If you remove this, the device will remain the same volume)
        start_time: "07:00" #Optional: Set the start time for this device
        end_time: "01:00" #Optional: Set the end time for this device
    "<Display_Name>": 
      - dashboard_url: "<Dashboard_URL>" 
        volume: <Volume>
        start_time: "<Start_Time>" 
        end_time: "<End_Time>"
```
