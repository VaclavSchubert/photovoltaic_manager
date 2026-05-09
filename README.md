# Photovoltaic Manager (Home Assistant Custom Integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=VaclavSchubert&repository=photovoltaic_manager&category=integration)

A Home Assistant custom integration that optimizes household energy flow using a **Mixed-Integer Linear Programming (MILP)** solver.

The integration manages electricity import and export from the grid based on:

*  Czech Energy Spot Prices
*  Photovoltaic production (via SolaX Inverter Modbus)
*  Solar production forecast (Forecast.Solar)
*  Predicted household load

Its goal is to minimize energy costs while respecting battery constraints and optional controllable loads.

Additionally, this integration allows community energy coverage of a second home.


## Dependencies

This integration depends on the following Home Assistant integrations:

* **Czech Energy Spot Prices** – provides hourly electricity spot prices
* **SolaX Inverter Modbus** – provides inverter and battery data
* **Forecast.Solar** – provides photovoltaic production forecasts

Make sure these integrations are installed and properly configured before setting up this one.

## How It Works

The integration runs a MILP optimization model that:

* Forecasts production and load
* Considers hourly electricity prices
* Respects battery constraints (min/max SoC, capacity)
* Optionally accounts for controllable loads (heater, AC)
* Calculates optimal grid import/export strategy

### Important

This integration **does not directly control battery charging logic**.
Its only direct grid-level action is:

* Import from grid
* Export to grid

Battery behavior follows from the optimized energy balance.


## Configuration

Configuration is handled via the Home Assistant **Config Flow**.

Below is a detailed explanation of all configuration options.


##  Core Settings

### Integration Mode

Determines how the integration behaves:

* `observe` – Optimization runs, but no grid control actions are executed.
* `manage` – Optimization runs and grid import/export is actively managed.

---

### Electricity Buy Price Rate

Defines how electricity import price is determined:

* `fixed` – Uses manually provided hourly prices.
* `spot` – Uses Czech spot prices from the spot price integration.

---

### Hourly Electricity Distribution Cost [JSON Array]

JSON array of 24 values representing hourly distribution costs (one value per hour).

Example:

```json
[1.2, 1.2, 1.1, ..., 1.5]
```

Units: CZK per kWh.

---

### Hourly Electricity Import Prices [JSON Array]

JSON array of 24 hourly electricity prices (used when Buy Price Mode = `fixed`).

Example:

```json
[3.5, 3.2, 3.0, ..., 4.1]
```

Units: CZK per kWh.

---

### Minimum State of Charge [%]

Minimum allowed battery state of charge.

Prevents excessive battery discharge.

Example: `20`

---

### Maximum State of Charge [%]

Maximum allowed battery state of charge.

Prevents overcharging.

Example: `95`

---

### Battery Capacity [kWh]

Total usable battery capacity in kWh.

Example: `10.2`


## Air Conditioning / Weather (Optional)

### Entity of Weather Forecast (AC)

Weather entity used for temperature prediction and AC-related load estimation.

Domain: `weather`

---

### Air Conditioning to Control (AC)

Climate entity that may be considered in optimization.

Domain: `climate`


## Heater Settings (Optional)

### Heater Entity to Control (Heater)

Switch entity representing the heater.

Domain: `switch`

---

### Heater Type (Heater)

Defines heater type:

* `combi_heater` - heater is only charged from surplus energy
* `electric_heater` - integration controls heater to charge in optimal hours

---

### Heater Volume [l] (Heater)

Water tank volume in liters.

Used for thermal energy estimation.

---

### Heater Power [kW] (Heater)

Rated heater power in kW.

Used for optimization constraints.


## Second Home Support (Optional)

Allows coordination with a secondary location. You can view the load in a second home. You can also completely cover load in the second home using community energetics.

Has been tested:
* Shelly Pro 3EM

---

### Second Home Server (Second Home)

Server URL of the ShellyCloud authorization cloud.

---

### Second Home API Key (Second Home)

Long-lived access token for authentication.

---

### Second Home Device ID (Second Home)

Identifier of the remote device used for synchronization.

---

### Second Home Management Mode (Second Home)

Defines interaction level:

* `view` – Read-only monitoring.
* `full` – Full optimization participation.

---

### Second Home Average Hourly Load [W] (Second Home)

Average hourly consumption of the second home in watts.

Only relevant if you want to use this integration for community energy.


## Optimization Model

The MILP solver:

* Minimizes total energy cost
* Considers:

  * Spot/fixed prices
  * Distribution costs
  * Forecast PV production
  * Predicted household load
  * Battery constraints
  * Optional controllable loads

The optimization runs on an hourly resolution.


## Installation
### Home Assistant Community Store

1. Add this repository to custom repositories : https://github.com/VaclavSchubert/photovoltaic_manager (type Integration)

2. Search this integration in the store and download

3. Restart Home Assistant
4. Go to:

```
Settings → Devices & Services → Add Integration
```

5. Search for the integration among the add-ons
6. Complete the configuration flow


### Manual installation

1. Copy this integration into:

```
custom_components/photovoltaic_manager/
```

2. Restart Home Assistant
3. Go to:

```
Settings → Devices & Services → Add Integration
```

4. Search for the integration
5. Complete the configuration flow


## Notes
* **IMPORTANT**: As the integration works on a hourly basis, grid import/export is also dependent on the start time of the integration (e.g. integration is initialized at 15:30, then the integration control will be aligned with the start time - at 15:30, 16:30, 17:30, ...). This can significantly effect the results. To achieve peak efficiency, initialize the integration at XX:00 or better yet - **after initialization, restart Home Assistant** because Forecast.Solar predictions are also dependent on start time.
* Ensure all required dependent integrations are installed.
* Price arrays must contain exactly 24 values.
* All numeric inputs must match expected units.
* SolaX Inverter Charger Use Mode must be **Self Use Mode** and SolaX Inverter Manual Mode Control must be **Off** for remote control to take effect.
* Info logging can be enabled via:

```yaml
logger:
  logs:
    custom_components.photovoltaic_manager: info
```

Subsequently, the output can be viewed in raw logs of the Home Assistant instance.

## Disclaimer

This integration performs automated energy optimization.
Always validate configuration parameters before enabling `manage` mode.

Improper configuration may lead to unexpected grid behavior.

