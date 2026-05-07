
FlightPlan Battery Cycle Count Patch
====================================

This patch adds estimated battery cycle calculations to the Equipment app.

Formula:
    total discharge percentage / 100

Example:
    30% + 40% + 30% = 100% = 1 battery cycle

Features:
- Flights logged per battery
- Estimated charge cycles
- Total discharge percentage

No migrations required.
