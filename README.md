# FlightPlan Equipment Usage Patch

Drop these files over the existing project.

Updated files:
- equipment/views.py
- equipment/templates/equipment/equipment_list.html

What it does:
- Confirms and uses FlightLog drone fields: drone_name, drone_type, drone_serial, drone_reg_number, air_time.
- Confirms and uses FlightLog battery fields: battery_name, battery_serial_printed, battery_serial_internal, battery percentages/mAh/volts.
- Adds flight-log usage stats to Drone equipment rows.
- Adds flight-log usage stats to Battery equipment rows.
- Appends read-only virtual rows for drones and batteries found in logs but not yet entered in Equipment Inventory.
- Shows logged flights, logged flight time, and estimated battery charge cycles in the view modal.

Notes:
- No migration required.
- The current FlightLog model does not include a manufacturer-reported battery charge cycle field, so battery cycles are estimated as one logged battery use per flight.
