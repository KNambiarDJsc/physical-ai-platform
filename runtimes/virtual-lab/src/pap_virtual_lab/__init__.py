"""A virtual laboratory: simulated instruments served as LabThings Things (W3C Web of Things).

Simulation only. Nothing here talks to hardware. Every Thing exposes a read-only ``simulated`` property that is
always true; the platform reads it before every command (D-026).
"""
