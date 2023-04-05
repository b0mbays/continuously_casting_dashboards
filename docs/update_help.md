If you are having issues after updating to the latest version v1.1.4 try the following steps:

1. Remove the integration: HACS -> Integrations -> Continuously Casting Dashboard -> _Three Dots_ -> Remove
2. Remove the integrations repository: HACS -> Integrations -> _Three dots_ -> Custom repositories -> Remove the custom repository for this integration
3. Comment out the integrations configuration setup from the configuration.yaml file. (On Windows you can do this by highlighting the full section and doing _Ctrl + /_ or Mac: _Cmd + /_)
4. Restart Home Assistant
5. Re-install the integartions repository and integration: Follow install steps [here](https://github.com/b0mbays/continuously_casting_dashboards#hacs-recommended)
6. **Reboot** home assistant. (Not a restart, reboot the instance)
7. Un-comment the integrations configuration setup inside the configuration.yaml file. (Ensure you have correctly renamed the section to 'continuously_casting_dashboards')
8. Restart Home Assistant a final time. 

The integration should be working again, apologies for any issues caused by this update 👍
