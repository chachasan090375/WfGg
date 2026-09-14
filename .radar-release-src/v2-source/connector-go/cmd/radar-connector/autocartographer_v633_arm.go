package main

// AUTO_CARTOGRAPHER_V633_ARM_HELPER
// Build-safe hook. V6.3.3 does not retain request credentials on the VPS.
func maybeArmAutoCartographerV633FromBody(_ *server, _ []byte) {}
