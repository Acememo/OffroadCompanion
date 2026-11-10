# Offroad Companion changelog

Newest first. Release-by-release notes start with 1.5.5. Before that, per-release notes weren't kept, so 1.0 to 1.5.4
are summarised by what came in, roughly in order.

## 1.7.9 (2026-11-09)

- **BeamNG.Earth 1.9.1-beta** is the version inside the .exe. A source install downloads 1.9.1-beta, and 1.9.0, 1.8.2,
  1.8.1, 1.8.0, 1.7.x, 1.6.x and 1.5.x still work. 1.9.1 fixes world generation hanging while GitHub is down, distant
  scenery that failed to load after a crash, short freezes in towns and stalls after teleports. Nothing it changed
  touches the ground, so courses and ground codes make the same ground as 1.7.8.
- **The .exe updates itself.** At each start it asks GitHub whether a newer Offroad Companion is out and, if so, asks
  whether to install it now. Yes downloads the new .exe next to this one, checks it against GitHub's SHA-256 checksum
  and starts it. No starts this version. The old .exe stays, and starting it starts the new one, so shortcuts keep
  working. `--no-update-check` skips the question. The BeamMP server zip is still updated by hand.
- Includes 1.7.8's fix for spectators, canopies and parked trucks standing on the track.

## 1.7.8 (2026-11-09)

- **Spectators, canopies and parked trucks no longer stand on the track.** Three causes are fixed:
  - When the track's real place came in together with new crowd spots, the ones already standing kept their old place
    (worked out from the course's line with a guessed width). On a track that rounds a bend inside the line, or follows
    a road beside it, that could be on the track. They are now put up again past its edge.
  - Nothing is put up on a stretch until the companion has said where the track runs there.
  - A truck or canopy moved a few metres along its line to find level ground could end up nearer the track on the
    inside of a bend, or on another pass of the course. It now only moves where it is still clear of the track.
- No ground changes: courses and ground codes make the same ground as 1.7.7.

## 1.7.7 (2026-11-08)

- **BeamNG.Earth 1.9.0-beta** is the version inside the .exe. A source install downloads 1.9.0-beta, and 1.8.2, 1.8.1,
  1.8.0, 1.7.x, 1.6.x and 1.5.x still work. 1.9.0 changed how BeamNG.Earth works out a dirt road's smoothing, which
  stopped the course painter from grading the roads (fixed). Its first visit to each place plans the roads again.
- **The course no longer picks up BeamNG.Earth's dirt road wear where it follows a mapped dirt road.** On Baja, Mild,
  Rough and Extra, a mapped dirt road the course runs along (within 25 m of it, in its direction, for 40 m or more) is
  now treated as the course's own track: no potholes, pits or leans from BeamNG.Earth there either. Other dirt roads
  keep BeamNG.Earth's wear. Default and Flat are unchanged.
- **Ground version 10**: with that wear gone, ground version 9's softening of Baja's rough sections on mapped dirt roads
  is gone too, so they are as rough as the course's own track again. Version 9's section shares stay. Only Baja
  changes, and older ground versions (ground codes) are unchanged.
- **Turn notes** choices are now in the order Top, Left, Right, Bottom.
- The .exe carries BeamNG.Earth 1.9's new launcher module (the 3D map's sky from orbit).

## 1.7.6 (2026-11-06)

- **Every setting fits.** A Settings row too narrow for its choices (Track terrain's six, or any row at a bigger app
  size) now puts them under its name, on more lines if needed. Before this, Extra and Flat could be cut off.
- **App size setting** (top of Settings): − and + scale the whole app, its text, buttons, turn notes and map labels,
  from 70 % to 250 % in 10 % steps. It used to follow the app's width; now resizing the app only changes its room.
- **Ground version 9: Baja tuned for BeamNG.Earth 1.8.2.**
  - Rough sections are rarer, and the rougher the rarer: about 20 % of a course is fast, 40 % mild, 28 % rough and
    12 % extra rough (before: 10 %, 25 %, 40 %, 25 %).
  - Where the course follows a mapped dirt road, which BeamNG.Earth 1.8.2 already wears with its own potholes, the rough
    and extra rough sections are softer (their part over Mild at 65 %), so the two no longer pile up. Around the DANGER
    waypoints, and on the course's own track, they are as rough as before.
  - Only Baja changes. Mild, Rough, Extra, Default and Flat make the same ground as version 8, and older ground versions
    (ground codes) are unchanged.

## 1.7.5 (2026-11-06)

- **Track terrain: Auto is now called Baja**, the same ground as before (and still the default).
- **New Track terrain: Default**, BeamNG.Earth 1.8.2's own dirt track. The course's track is worn like any forest
  track: potholes, broken patches, deep pits and leans, with none of Offroad Companion's relief.
- **Flat smooths every dirt road**, as BeamNG.Earth was before 1.8.2: no potholes or leans on the course's track or
  on the dirt roads around it.
- **Leans are rare on Baja, Mild, Rough and Extra.** The other dirt roads keep BeamNG.Earth 1.8.2's potholes, but only
  about 1 road part in 20 leans to one side. The course's track itself stays as in 1.7.4: its own relief, no wear.
- A change of Track terrain now plans the roads again in BeamNG.Earth 1.8's server, so the new setting reaches every
  dirt road and not only the ones planned after the change.
- Without a course loaded, BeamNG.Earth's dirt roads are as BeamNG.Earth makes them. The course's track on Baja, Mild,
  Rough, Extra and Flat is the same as in 1.7.4 (ground version 8). Ground codes made on BeamNG.Earth 1.8.2 change,
  since the dirt roads around the course do.

## 1.7.4 (2026-11-06)

- **BeamNG.Earth 1.8.2-beta** is the version inside the .exe. A source install downloads 1.8.2-beta, and 1.8.1, 1.8.0,
  1.7.x, 1.6.x and 1.5.x still work.
- **The course's track stays the course's.** BeamNG.Earth 1.8.2 wears its dirt roads: potholes, broken patches, the odd
  deep pit and a lean to one side, and forest tracks the worst of all. The course's track is a track too, so on 1.8.2
  it would have had holes nearly 1 m deep. It now keeps its own ground (its relief, by its ground version), the same
  as on 1.8.1. The mapped dirt roads around the course keep BeamNG.Earth's wear.
- **No BeamNG.Earth update prompt.** BeamNG.Earth 1.8.2's launcher asks at every start whether to install a newer
  BeamNG.Earth, and would download BeamNG.Earth's own .exe beside Offroad Companion's. Offroad Companion's .exe never
  asks: the BeamNG.Earth inside it comes with Offroad Companion's releases.
- **BeamNG.Earth's data folder in the .exe.** 1.8.2 reads its billboards, direction signs and place search data from
  a data folder of its own; the .exe now carries it (the mapped billboards were missing from 1.8.0 and 1.8.1 .exes).
- The ground is the same as 1.7.3's (ground version 8). Players on 1.7.3 and 1.7.4 run different BeamNG.Earth
  versions, so their servers don't share built ground.

## 1.7.3 (2026-11-05)

- **Orange dirt roads on BeamMP, explained and prevented.** BeamNG.Earth 1.8 draws dirt roads, the course's track
  included, as rutted strips with materials that only its 1.8 game mod defines. An older BeamNG.Earth game mod (1.7)
  still works with a 1.8 server but lacks them, so the game shows its orange missing-material texture. On a BeamMP
  server every player gets the server's `Resources/Client/beamng_earth.zip`, so an old copy there does it to everyone
  running the Offroad Companion .exe 1.7.1 or newer.
  - The BeamMP server zip now also carries BeamNG.Earth's own BeamMP files (`Resources/Client/beamng_earth.zip` and its
    plugin) for the BeamNG.Earth version inside the .exe. Unzipping it on the server keeps both mods matched.
  - The app shows a red line under the map when the game's BeamNG.Earth mod is older than its server, saying what to
    replace (on BeamMP: the server's `beamng_earth.zip`; in single player: the old copy in your mods folder).
- The ground is the same as 1.7.2's (ground version 8).

## 1.7.2 (2026-11-04)

- **Ground version 8: wider tracks.** A track gets its full width (now 10 m) with much less room around it: open
  desert with a little relief or a few bushes within 10 m is enough. A wash or canyon floor about 10 m wide now gets
  about 6 m instead of 4-5 m, and the narrowest shelf on a hillside 4-5 m instead of 3-4 m. **Track size** still
  scales them all.
- **Rounded turns.** Course files' points are often hundreds of metres apart, and the track turned on the spot at each
  one: straight lines from point to point. Each corner is now an arc, as wide as the corner allows (up to a 250 m
  radius) while staying within 12 m of the course's corner. A sharp hairpin keeps its point. Courses recorded with
  close points stay as they are. The signs, crowds and turn notes are told where the track went, so they stay beside
  it.
- Ground versions 1-7 are unchanged; replays keep their own ground.

## 1.7.1 (2026-11-04)

- **BeamNG.Earth 1.8.1** is the version inside the .exe. A source install downloads 1.8.1-beta; 1.8.0, 1.7.x, 1.6.x
  and 1.5.x still work.
- **Road plans with the track stay with their course.** 1.8 keeps a place's road plans across updates and shares them
  between the players of a BeamMP server and in baked packs. Plans that carry a course's track are now kept and
  shared only for the same ground code, so a player with another course, or none, never gets them. BeamNG.Earth's own
  plans are never used for a course either. 1.8's experimental world bundles are not used while a course is loaded.
- **Roads beside the course come out as BeamNG.Earth makes them.** The cells the track runs through now take a road's
  lanes and bridges from its home cell, as 1.8 does elsewhere, so they agree with the cells around them (1.8 fixed
  bridges drawn twice at two heights this way). Their road details are kept under an id of their own.
- **No fences or props across the course.** 1.8 places mapped chain-link fences, noise walls, containers, barns,
  billboards, towers, picnic tables and bus shelters. Where the course crosses a fence or noise wall there is now a
  gap, like a ranch gate, and the other props within 6 m of the course line (plus their size) are left out.
- **The track's ruts follow 1.8's dirt strip.** 1.8 draws dirt roads as rutted strips again, the course's track
  included. The wheel ruts now follow that strip, and sand traps, rock sections and crawls still show the ground
  itself.
- **No texture rebuilds from the mod's dates.** The mod's files are now dated in the past in every time zone, as
  BeamNG.Earth 1.8.1 does with its own. Dated in the future west of UTC, the game could rebuild the ground's textures
  at every new block. Server owners: replace `Resources/Client/offroad_companion.zip` with this release's.
- The ground is the same as 1.7.0's (ground version 7).

## 1.7.0 (2026-11-01)

- **Ground version 7: more variety along the track, only where the place has it.**
  - **Sand traps**: deep soft sand where a dry wash crosses or runs along the course (most of them), on desert canyon
    floors and by the sea (some), now and then on open flat desert. The track sinks into the sand about 25 cm, its
    floor churned, the sand thrown up beside it. Never on lakes, rarely on mapped dirt roads.
  - **Rock sections** in canyons and on rocky hillsides: rock underfoot, stronger ledges and lumps, lower whoops,
    loose gravel at the edges and more boulders beside the track.
  - **Gravel** on alluvial fans (a desert track on a steady 2.5-12 % grade), in green-country creek beds, on broken
    ground on the way into the rocks and on dirt roads in the hills: gravel underfoot, a little smoother, a low
    windrow of gravel along the edges.
  - **Rock crawls** (Auto): about 7 in 10 DANGER waypoints that sit in a canyon become a 70-160 m staircase of
    tilted rock shelves, with 30-70 cm boulders in the track, a clear line weaving between them and bigger boulders
    beside it. The waypoint's ditch or kicker gives way to it.
  - Sand traps, rock sections and crawls show the ground itself: the dirt track is not painted over them.
  - Each stretch decides from its place on the Earth, so everyone on the same course gets the same sections. Ground
    versions 1-6 are unchanged; replays keep their own ground.
- **The Big map button shows without a course too.** With no course, the turn notes and the street stay, and the
  route's buttons are hidden.
- **Hide the app.** A **▾** at the end of the tabs folds the app into a small "Offroad Companion" button in its top
  right corner, the way the Race Control app does; click it to bring the app back. A key can be bound to it under
  Options, Controls, "Offroad Companion: hide or show the app" (none by default). While it is hidden, the game sends
  it no updates, and it stays hidden until you show it.

## 1.6.13 (2026-10-31)

- **No more walls across the course from a motorway bridge.** Where the course runs off the roads under a motorway
  bridge (the Libramiento de Ensenada near 31.909° N, 116.547° W), BeamNG.Earth could build the bridge's deck a metre
  or two over the course's ground, a slab ending in a tall wall that the course ran into. Motorway bridges were left
  alone, since only the short off-road bridges were flattened.
  - Now a motorway bridge over the course is judged by its headroom, the same way as the low overpasses: one whose
    deck would stand less than 6.5 m over the course becomes a crossing at ground level, and one high enough (over a
    canyon) stays. Only bridges on the course are touched, and it is checked once when the roads are built.
- **Parked trucks and canopies stand on the ground.** Before one is placed, the game's ground is checked under its
  middle and four sides. If a roof or a wall is under it, or the ground drops more than about half a metre across it, it
  moves a few metres along the line, or is left out. So none sits on a building or floats off a hillside. People,
  fences and flags are placed as before.
- The ground is the same as 1.6.9's (ground version 6).

## 1.6.12 (2026-10-31)

- **No more trees hanging in the sky.** Since 1.6.8, loading a course near the car had BeamNG.Earth send its trees
  and far buildings again while the game still kept the old ones (BeamNG.Earth 1.7.2+ keeps them across rebases and
  teleports). The new trees went into the old tiles, placed from where those were first made, and the old tiles away
  from the car were never dropped, so far-off trees could hang in the air.
  - Now the game itself drops its roads, buildings and trees round the car first, then asks for them again, built
    for the new course.
- The ground is the same as 1.6.9's (ground version 6).

## 1.6.11 (2026-10-30)

- **BeamNG.Earth 1.7.3** is the version inside the .exe. A source install downloads 1.7.3-beta, and 1.7.2, 1.7.1,
  1.7.0, 1.6.x and 1.5.x still work. BeamNG.Earth's development builds (1.7.2-beta.dev.37 and the like) count as the
  release they come before.
- Its faster world building and its fix for roads that never loaded on Windows (a lock file left behind) come with it.
  Nothing in the companion needed changing for them.
- The ground is the same as 1.6.9's (ground version 6).

## 1.6.10 (2026-10-30)

- **New crowd sound.** The spectators now cheer and clap with mglennsound's "AF Crowd Cheer Clapping LOOP" from
  Freesound. It is a seamless 22 s loop, and each crowd starts it at one of three points, so crowds side by side are
  never in step. It is public domain (CC0), so the sound files can be shared with the project. The Mixkit recording
  used since 1.4 is gone.
- **Offroad Companion is open source under the MIT License** (`LICENSE`).
- The ground is the same as 1.6.9's (ground version 6).

## 1.6.9 (2026-10-30)

- **Smoother, more natural track terrain.** The game's ground is a grid of triangles 2 m apart. Many of the
  track's shapes were narrower than that: the windrows along the edges, the sand on the outside of the turns, the
  small bumps, the rut chop, the rock ledges' steps and the edge of a banked corner. On the grid they came out as saw
  teeth and lone spikes that looked like polygons and felt like them under the tyres.
  - Now no shape is narrower than about 6 m, and nothing changes over less than about 3 m.
  - Whoops are a little longer.
  - Broken ground rolls in long swells, and rock ledges step softly.
  - The windrows and the sand on the outside of the turns are wide, soft mounds.
  - A banked corner is a smooth bowl with its lip just past the edge.
  - The tallest spots ease into their limit instead of flattening off.
  - Kickers keep their place and height, with a softer back.
- The terrain is as rough and as tall as before, only rounder. The sharpest change between neighbouring points of the
  grid is about a third of what it was.
- **Ground version 6.** Everyone racing together needs 1.6.9. Replays keep the ground they were recorded on.

## 1.6.8 (2026-10-29)

- **BeamNG.Earth 1.7.2** is the version inside the .exe. A source install downloads 1.7.2-beta, and 1.7.1, 1.7.0,
  1.6.x and 1.5.x still work.
- **A new course clears the place it loads in.** BeamNG.Earth 1.7.2 builds buildings, street furniture, trees and
  far buildings once per map tile and keeps them in the game across rebases and teleports near. A course loaded
  where you already were (or a change of track size or terrain) would have kept buildings and trees standing on the
  new track. Now BeamNG.Earth sends the tiles round the car again, built for the new course.
- **The in-game track works with BeamNG.Earth 1.7.2's map tiles** (only used with BeamNG.Earth's own .exe, without
  the course painter). It is drawn on the new tiles and drawn again after each rebase.
- The ground is the same as 1.6.4's (ground version 5).

## 1.6.7 (2026-10-29)

- **Roads and buildings no longer get stuck at 0 with a course loaded.** This was a deadlock between the course's
  track and BeamNG.Earth 1.7's bridge finder (grade separation). Laying the track needs the area's road details,
  and the bridge finder looks at the neighbouring map areas to work those out. Those neighbours then needed the track
  laid first, so each side waited on the other forever. It happened where the map has short tunnels nearby, as in
  Ensenada.
  - The bridge finder now reads the map's roads without the track. The track takes no part in where bridges go.
- The ground is the same as 1.6.4's (ground version 5).

## 1.6.6 (2026-10-29)

- **The ground, roads and buildings load again with a course loaded.** In the .exe, every one of BeamNG.Earth's
  worker processes (about ten) started its own planner of the track ahead of the car, all fetching map data and
  planning at once. The ground, roads and buildings waited behind them ("Loading ... roads & buildings 0/32"), and the
  server log filled with "no track prefetch: daemonic processes are not allowed to have children". Now only the
  server's own process plans ahead, as in a source install.

## 1.6.5 (2026-10-29)

- **Roads and buildings load again.** In 1.6.4 the loading could stall at "roads & buildings 0/32": BeamNG.Earth's
  road builders waited on the ground to find the rutted sections, while the ground waited on the roads. The roads
  now only use the ground already planned (the track is planned ahead of the car), and never wait.
- The ground is the same as 1.6.4's (ground version 5).

## 1.6.4 (2026-10-29)

- **Banked corners on rough ground.** Some tight corners tilt into the turn like a Baja bowl: the outside is pushed
  up into a lip of dirt that eases back into the ground, and the inside is dug a little.
  - The tighter the corner and the rougher the ground, the likelier it is banked. On Rough about a third of the
    tightest corners are, on Extra most of them, never every one. None on Flat or Mild, on straights or in rock.
  - The bank eases in and out with the corner itself, so there is no step.
- **Rutted sections on Mild or rougher ground.** Some stretches are worn by the tyres: the floor lower, windrows of
  dirt thrown to the edges, the ground chopped up, and braided wheel ruts that wander and split.
  - More of them where the track is narrow and the ground rough, fewer on graded roads, none on Flat.
  - The game's ground is a 2 m grid, so the narrow grooves are drawn on the track. The ground itself takes the worn
    floor, the windrows and the chop.
- **Ground version 5** for both. Everyone racing together needs 1.6.4. Replays keep the ground they were recorded on.

## 1.6.3 (2026-10-28)

- **BeamNG.Earth 1.7.1** is the version inside the .exe. A source install downloads 1.7.1-beta, and 1.7.0, 1.6.x and
  1.5.x still work.
- **Power line towers don't collide anymore.** BeamNG.Earth 1.7's high-voltage lattice towers no longer block the
  car (it drives through them), so a tower on or beside a course can't stop a race. Substation equipment behind its fences stays solid.
- **Sand and gravel layers follow BeamNG.Earth 1.7.1's ground photo setting.** Their names now start with bngEarth,
  so they always match the other ground layers' size (1024, 2048 or 4096).
- **Lane details kept where the course runs:** the map areas the course passes through keep BeamNG.Earth 1.7.1's
  OpenStreetMap lane tags.
- **The .exe includes BeamNG.Earth 1.7.1's new data files:** British Columbia's lidar and photo indexes, and the
  highway signs' lettering and state outlines.

## 1.6.2 (2026-10-28)

- **Spectators stay off the road.** They stand a clear 3 m past the track's edge, with canopies and parked trucks
  further back. They also keep off every road and dirt track OpenStreetMap has around them, not only the ones in the
  game's road map.
- **Round the trees.** Where the course runs into trees, the track bends round them to the nearest level free ground.
  Where there's no room, the trees, bushes and rocks on the track or on a road the course follows are taken out.
  BeamNG.Earth's tree cache is now kept per ground code, so trees from another course never come back.
- **No more grass strip on a bare desert track.** Grass and scrub grow on the track only where the land beside it has
  them, over its edges and (on wide tracks, some stretches) down the middle between the wheel paths, which stay bare.
- **Gentler, rarer washes.** A wash is now a dry streambed: an eased bank down, a flat floor 6-18 m long, an eased
  bank up. Most are 15-45 cm deep, now and then 70 cm, about one per km. The DANGER ditches have the same shape.
- **Wet ground looks wet.** The ground and roads go darker and glossier with the wetness.
- **Puddles show from about 450 m ahead.** Their look depends on the rain:
    - brown water while it rains or just rained;
    - muddier later that day;
    - mud holes a day or more after.
- **Ground version 4** for all of the ground changes. Replays keep the ground they were recorded on.

## 1.6.1 (2026-10-28)

- **Track terrain defaults to Auto.** Settings saved with Rough (the old default) switch to Auto once. If you pick
  Rough again after that, it stays.
- **Choose where the data goes.** The first start of the .exe asks where to keep the data that grows: BeamNG.Earth's
  map downloads (up to 20 GB) and Offroad Companion's planned tracks, replays' ground and your tracks.
  - **Enter** keeps it on the system drive. **F** lets you choose a folder, for example on another drive.
  - What is already there can be moved over, or you can start empty.
  - `--pick-data-dir` asks again.
- **Each release now comes with a source code zip,** and this changelog.

## 1.6.0 (2026-10-28)

- **BeamNG.Earth 1.7.0** is the version inside the .exe. A source install downloads 1.7.0-beta, and 1.6.x and 1.5.x
  still work.
- **Railway crossings where the course runs:** the map areas the course passes through keep BeamNG.Earth 1.7's
  level crossing details (gates, lights, crossbucks).
- **The .exe includes BeamNG.Earth 1.7's new data files:** the climate map, oil wells, refineries, the map data index
  and the Windows certificate store support.
- **BeamNG.Earth 1.7's new Rocks setting** also hides the boulders beside the track. For racing together, everyone
  should use the same setting.

## 1.5.9 (2026-10-28)

- **The ground under the course matches the real place.** This is ground version 3: older replays keep their own
  ground.
  - Sand in dry washes, desert canyon floors and beaches.
  - Mud on the banks of rivers and lakes that hold water all year, and in wetlands.
  - Gravel in green country's creek beds and over rocky ground.
  - Packed dirt on graded roads, dry lake beds and tracks through grassland.
  - Loose dirt on a desert track's sides and the outside of turns.
- **Wet ground after rain** (Settings, on by default). The ground is as wet as the real rain of the last 3 days left
  it at that place, and at least damp while the game's own rain falls.
  - It grips less, gradually: a shower barely shows, a soaked track slides. Sand and mud stay as they are.
  - When the ground is soaked, water stands in the track's closed dips, like the troughs between whoops.
- **Share a ground code.** Settings shows the full code with a **Copy** button. A friend with the same course loaded
  pastes it and presses **Use**, and gets exactly the same ground.

## 1.5.8 (2026-10-28)

- **Everything closes neatly.** About 10 seconds after the game closes, the world server and BeamMP stop and the
  window closes.
- **Closing the window first** stops them too.
- **A leftover BeamMP launcher is closed at start.** One left running by an earlier start broke the next BeamMP
  session ("No players... something is wrong", ping "?").

## 1.5.7 (2026-10-27)

- **SCORE courses that stopped loading** ("mismatched tag") load again. SCORE's site started returning a web page
  instead of the course file, and the course is now found from that page.

## 1.5.6 (2026-10-26)

- **Everything in one program:** `OffroadCompanion-<version>.exe`, with BeamNG.Earth, its server and Python inside.
  There is no Python to install and no setup step.
- **It finds the game's user folder** (also one moved out of AppData), installs both mods and starts the game.

## 1.5.5 (2026-10-26)

- **BeamNG.Earth 1.6.3 support.**
- **Natural cut banks.** Where BeamNG.Earth cut a bare cliff into a hillside beside the dirt track, there is now a
  sloping bank, as a grader leaves it (ground version 2).

## 1.5.0 to 1.5.4 (2026-10-25 to 26)

- **BeamNG.Earth 1.6 support:**
  - The dirt track is painted into the ground's photo.
  - **Teleport to start** plans the track before the ground is built.
  - Plan and revisit caches are kept per ground code.
- **Replays follow the recording.** BeamNG.Earth's world moves to where each moment was recorded.
- **Replays get their recorded ground back.** That is the course, its settings and its ground code.
- **Long recordings are split before 2 GB**, which BeamNG can't play back after a restart.
- **BeamMP fixes:**
  - Your car is held still while the ground loads.
  - BeamNG.Earth's big map draws again with no other players.
  - The mod is switched back on after leaving a server.
- **Spectators:**
  - **Lots** lines the course like a Baja race crowd, bigger near towns.
  - Crowds light up at night with campfires, lanterns and light towers.
  - Crowd sound is a seamless loop near each crowd.
- **The source setup only downloads a BeamNG.Earth version the companion was made for.**

## 1.3 to 1.4 (2026-10-22 to 25)

- **Track terrain:**
  - Whoops, washes, kickers, berms, broken ground and rock ledges along the course (**Mild**, **Rough**, **Extra**,
    **Flat**).
  - **Auto** mixes fast, mild, rough and extra rough sections, with hazards at the course's DANGER markers and boulder
    fields.
- **The same ground for everyone:**
  - Ground versions and a golden test.
  - Missing data is never frozen into the ground.
  - The ground code names exactly one ground.
  - Ground snapshots for replays.
- **The track is planned ahead of the car,** so the ground comes in with its track.
- **Spectators** at the start, finish, checkpoints, jumps and hazards (**Some** / **Lots** / **Off**), with cheers.
- **Make track:** record a drive or tap points on the map, then save and race it.

## 1.2 (2026-10-23)

- **Renamed** from BeamNG.Earth GPS to **Offroad Companion**. Settings, replays, tracks and planned ground move over
  by themselves.
- **Course markers** as desert races use them: VCP boards, CHECKPOINT stop signs, START and FINISH banners, course
  stakes, and (on **Full**) arrows, DANGER AHEAD and speed zone boards.
- **Wheel ruts** where the dirt track blends into the ground.
- **The whole course on the map,** north up, with checkpoints and your progress.

## 1.0 to 1.1 (2026-10-21 to 22)

- **Road navigation:**
  - Search addresses and places.
  - Turn-by-turn directions in English or Spanish, with reroute.
  - BeamNG.Earth's route arrows and Autodrive.
  - A street map that turns with the car.
- **Race courses:**
  - Sources: SCORE, race.mx, OpenStreetMap raceways, GPX / KML / KMZ files, links.
  - Course guidance: the course line on the ground, rally-style corner calls, race mile, VCPs and checkpoints hit or
    missed, speed zones, off-course and wrong-way warnings, lap and course times.
- **A dirt track** painted along the course where no road runs.
- **A clear course** without buildings, walls or low bridges in the way. The route you follow is cleared too.
