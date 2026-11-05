# Offroad Companion on a BeamMP server

In a BeamMP session the game loads only the mods the server sends. To give every player Offroad Companion (courses,
turn notes, VCPs, course signs):

1. Unzip this zip into the server's folder, replacing what is there. It adds `Resources/Client/offroad_companion.zip`,
   and BeamNG.Earth's own BeamMP files for the BeamNG.Earth version inside the Offroad Companion .exe:
   `Resources/Client/beamng_earth.zip` (the BeamNG.Earth game mod every player gets) and its plugin
   `Resources/Server/BeamNGEarth`.
2. If the server had it under its old name, delete `Resources/Client/beamng_earth_gps.zip` (players would get both).
3. Restart the server. Players get both mods when they join.

Keep `Resources/Client/beamng_earth.zip` the same BeamNG.Earth version the players run. In a BeamMP session every
player's game loads the server's copy (their own mods are turned off), so an older one there makes everyone's dirt roads
solid orange (the game's missing-material texture): BeamNG.Earth 1.8 draws dirt roads with materials its 1.8 game mod
defines. The app says so when it happens.

Each player who wants the dirt track along the course, the track terrain and the cleared course also runs Offroad
Companion with BeamNG.Earth's server (`run_offroad_companion`) on their own computer. To race the same ground,
everyone loads the same course with the same settings and checks that the ground code in the app's Settings matches.
