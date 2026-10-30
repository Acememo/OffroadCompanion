# Offroad Companion on a BeamMP server

In a BeamMP session the game loads only the mods the server sends. To give every player Offroad Companion (courses,
turn notes, VCPs, course signs):

1. Set up the server for BeamNG.Earth first (BeamNG.Earth's own `BeamNG.Earth-BeamMP-Server-<version>.zip`).
2. Unzip this zip into the same server folder. It adds `Resources/Client/offroad_companion.zip`.
3. If the server had it under its old name, delete `Resources/Client/beamng_earth_gps.zip` (players would get both).
4. Restart the server. Players get Offroad Companion when they join.

Each player who wants the dirt track along the course, the track terrain and the cleared course also runs Offroad
Companion with BeamNG.Earth's server (`run_offroad_companion`) on their own computer. To race the same ground,
everyone loads the same course with the same settings and checks that the ground code in the app's Settings matches.
