# Offroad Companion

Off-road racing on the real world, for [BeamNG.Earth](https://github.com/TecnaGamer/BeamNG.Earth). Load a real race
course (SCORE's Baja races, race.mx, OpenStreetMap circuits, or any GPX/KML/KMZ file) and drive it: turn notes,
VCPs and checkpoints with real course signs, a dirt track laid along the course with whoops, washes and rocks, the
course cleared of buildings and walls, timing and replays. Everyone driving the same course gets the same ground,
bump for bump. Between races it is a GPS too: the street you are on, and turn-by-turn directions to any place.

It is an add-on: it uses BeamNG.Earth's own world, street names, search, route arrows and Autodrive. It has two
parts: the in-game app (a game mod) and a small helper program that runs beside BeamNG.Earth's server, for the
things the game cannot do by itself (its Lua cannot reach the internet and its UI browser blocks web requests,
which is also why BeamNG.Earth has a server). Offroad Companion was called "BeamNG.Earth GPS" before 1.2.0.

## What you get

**Road navigation**
- Current street, town and country (from BeamNG.Earth's map data).
- Search any address or place: results come as you type (after a short pause), **Enter** or the Search button
  searches harder, and coordinates (`32.83, -117.19`) work too. The Offroad Companion does the searching, one search at
  a time: Photon (komoot) while typing, and on Enter also OpenStreetMap's Nominatim when Photon is slow or finds
  nothing. Without the companion, BeamNG.Earth's own search is used.
- Turn-by-turn: "In 350 m, turn right onto Boulevard Agua Caliente", the maneuver after it, distance and time
  left, automatic reroute when you leave the route. English or Spanish.
- BeamNG.Earth's stock route arrows on the road and its Autodrive work with every route you pick here.
- A map like Google Maps' dark map: the streets around you from OpenStreetMap, main roads in amber, street names
  written along them; it turns with the car. `+` / `−` zoom.
- The route you follow is cleared of blockages too (see below), whether you searched it here, in BeamNG.Earth's
  menu or put a marker on BeamNG.Earth's big map.

**Make your own track**
- The **Make track** tab: **Record drive** drops a point every 8 m as you drive; **Tap on map** turns the map
  north-up so you can tap points in order (drag to look around); **Add here** and **Checkpoint** use the car's
  spot; **Undo**, **Clear**.
- **Save and load** writes it as a GPX file into the companion's tracks folder and loads it as the course right
  away, so it gets cleared and gets its dirt track like any course. It stays under Courses > My files.
- Handy where a real course is blocked by odd map data: drive or tap around it, save, and race that.

**Race courses**
- Course line drawn on the ground ahead of you (cyan, yellow in speed zones, red near hazards) and posts at
  checkpoints / VCPs.
- Rally-style corner calls from the course's shape: "Right 3 in 120 m, into Left 4", hairpins.
- Race mile (from the file's RM markers), distance done / to go, the next VCPs, checkpoints, DANGER markers and
  speed zones, the speed limit inside a zone with a warning when you are over it.
- VCPs and checkpoints judged as hit or missed; lap times on circuits; start-to-finish time on open courses.
- Off course: how far and which way back, and a wrong-way warning.
- Courses that are only a list of places (race.mx's Baja 1000 race order) go waypoint to waypoint, with road
  directions to each one.
- Buttons for road directions to the start, teleport to the start, back to the course.
- Over the map's **+ / -**: how far the map reaches ahead of the car, and the radius of the ring around the car.
- **Big** (top right of the map, with or without a course): a bigger map. The turn notes stay, and on a course its
  name, race mile, time and progress bar; the rest under the map (done / to go, the next VCPs, the buttons; with no
  course, the route's buttons) is hidden until you press it again. The app remembers it.
- **Hide** (the **▾** at the end of the tabs): the app folds away to a small **Offroad Companion** button in its top
  right corner; click it to bring the app back. You can also bind a key to it: Options, Controls, **Offroad
  Companion: hide or show the app** (no key by default). While hidden the app costs nothing: the game sends it no
  updates. It stays hidden the next time until you show it.
- **Turn notes** (Settings): the box with the arrow, the distance and the call at the top of the app (**Top**), at its
  bottom (**Bottom**), or down its whole left or right side (**Left** / **Right**: the arrow above the text, one column;
  the map, the course strip and the tabs beside it).
- **Course** on the map: the whole course, north up, with its checkpoints and where you are on it (the part done
  dimmed). Drag to move it; the mouse wheel, **+ / -** or a double-click zooms where the mouse is; drag with the right
  mouse button (or shift + drag, or the turn buttons) to turn it. **Fit** shows the whole course again, **Car** keeps
  the car in the middle, **↑** turns the map with the car, **Big** hides the strips below for a bigger map. The
  checkpoints' names show wherever there is room for them. **Back** returns to the map around the car. (BeamNG.Earth's big map draws only its own GPS route; another
  mod cannot add a line to it, so the course overview lives in this app.)
- **Course markers**, signs on stakes the way desert races are marked, only near you, each turned to face you:
  - **Checkpoints** (default): an orange **VCP** board on a stake both sides of the course at each VCP, a red
    **STOP** sign over a **CHECKPOINT** plate both sides at each checkpoint, a **START** banner and a checkered
    **FINISH** banner across the course, and a pink-painted course stake about every 8 km (5 miles).
  - **Full**: also orange **arrow** boards on the inside of the turns, about 30 m before them (one arrow under
    45 degrees, two for 45 to 75, two on a pink board for sharper), pink **DANGER AHEAD** boards about 150 ft before
    the hazards, both sides, and **SPEED ZONE** / **RESUME RACE SPEED** boards at the speed zones' ends.
  - **Off**.

  They stand beside the track: with BeamNG.Earth's server from source, the companion tells the app how wide the dirt
  track (or the road the course follows) is and where its middle is, and each sign goes 1.5 m past its edge (about 6 m
  from the course line until that is known). Where the course passes the same place twice (out and back along one
  road), a sign also stands clear of the other pass: past the far edge of the whole road, never in its middle. The app asks
  the companion for the width of every pass near you (not only the stretch you are on), so this holds on wide roads
  too. They
  don't collide. Signs are put up within 600 m; ones put up far away (where the ground may not be loaded yet)
  are checked again within 350 m and put back on the ground if they were off. **Test markers** in Settings puts two
  VCP boards ahead of the car, facing you, and says whether the game loaded them. Settings shows how many stand near
  you, the nearest VCP / checkpoint sign and whether it sits on the ground; if the game cannot show them, the course
  strip says why.

## Dirt tracks along the course

Wherever the loaded course leaves BeamNG.Earth's roads (open desert, washes, hillsides), a dirt track is laid along
it as the world streams in, so there is something to drive on and follow. Where the course runs on a road
BeamNG.Earth already draws, nothing is added: the course just uses that road.

The track's width follows the **terrain clearance**: at every 10 m the painter measures how far the ground stays
level with the track (and free of trees) on each side, out to 16 m.

| Terrain | Room | Track |
|---|---|---|
| Open, flat desert | 30+ m | 9 m, a wide graded course road |
| Wash or canyon floor about 10 m wide | about 10 m | 4–5 m |
| 30 % hillside, or between trees | a few metres | 3–4 m, a shelf cut into the slope |

Widths change gradually along the course. The **Track size** setting (Narrower / Auto / Wider) scales them all.

The track goes into BeamNG.Earth's own road data, so it gets everything a mapped dirt road gets: the dirt road
surface, the ground graded flat under it, the dirt feel under the tyres, and trees kept off it.

It works two ways, and the app picks one by itself:

- **BeamNG.Earth's .exe (or `run_server`), as you normally start it:** no extra setup. The companion plans the
  track: it gets the roads already there from OpenStreetMap, and the terrain from AWS Terrain Tiles, one of
  BeamNG.Earth's own elevation sources. The game then draws it as dirt road decals on BeamNG.Earth's road tiles as
  they stream in, and removes them with the tiles. The track is drawn on the natural ground, which is not regraded
  under it, and trees don't narrow it.
- **BeamNG.Earth from source, started with `OffroadCompanion/run_offroad_companion`** (.bat / .sh) instead of
  `run_server`: the track goes into BeamNG.Earth's own road data. The ground is graded flat under it, the tyres feel
  dirt, trees are kept off it and also narrow it. This runs BeamNG.Earth's own launcher with the same options and
  mod update. The first time, if BeamNG.Earth is not found, add `--earth "C:\path\to\BeamNG.Earth"` (it is
  remembered). When you load a course, the roads around you are sent again so the track shows right away. Ground
  already loaded is regraded at BeamNG.Earth's next world shift; teleporting to the start does it at once.

Settings shows which way is in use. Either way, keep the Offroad Companion running.

Only courses with a real course line are painted. Courses made only of waypoints, or a "Rough line" drawn
between race-mile markers, are not.

## A clear course: no buildings, walls or low bridges in the way

Map data puts things on a race course that you could not drive through. With **Clear the course** on (Settings, on by
default), BeamNG.Earth's server leaves them out as the world streams in:

- **buildings** whose footprint lies within 6 m of the course line (and their yard fences). Toll plazas stay:
  their islands, booths and flat plaza footprint are kept, so BeamNG.Earth (1.5.5 on) still draws West Coast USA's
  toll booths there; you drive through a lane as in life;
- **short bridges the course crosses off-road** (at most 150 m long, not motorways). A creek that the map calls a
  bridge becomes, in the game, a deck with parapet walls the course runs into. These are built as ordinary
  ground roads instead, graded to the ground, so the course crosses at grade. A bridge over a road the course
  follows (an underpass) stays as it is;
- **low overpasses**: a short road bridge (BeamNG.Earth's own roads too, motorways included) over the road the
  course follows is kept only when BeamNG.Earth can build its deck at least 6.5 m over that road. That is judged the
  way BeamNG.Earth grades the ground: the road below is flat across its lanes and shoulder and blends up 1 m per
  2 m, each road's height is smoothed along it, and a deck climbs at most 6 % from its ends. So an overpass whose ends
  stand at the edge of a highway cutting (the Carretera Tijuana - Ensenada, the Libramiento de Ensenada) ends up a
  metre over the highway in the game, a wall of parapets, and is built as a crossing at ground level instead. A
  real flyover with long spans stays. A motorway's bridge over the course where the course runs off the roads is
  judged the same way: a deck that would stand less than 6.5 m over the course's ground (a slab ending in a wall
  the course runs into) becomes a crossing at ground level; one high enough over a canyon stays;
- **walls across the course**: retaining walls are cut where the course passes through them, and wherever one
  stands on the lanes of the road the course follows (a crossing road's wall reaching into the highway). Walls
  running alongside it stay.

### The GPS route too

With **Clear the GPS route** on (Settings, on by default), the road route you follow gets the same treatment, in a
narrower strip (its lanes): buildings on it, walls across it and low overpasses. It works for a place you search in
this app, in BeamNG.Earth's menu, or a marker you put on BeamNG.Earth's big map (BeamNG.Earth's own route is used).
A long route like Ensenada to Tijuana is cleared all the way, as the world streams in. When you pick a new
destination, the roads around the car are sent again so it applies right away; ending the route stops it.
"Route cleared" under the street name shows it is on.

This needs BeamNG.Earth's server from source, because the .exe's server is sealed. Set it up once:

1. Run `OffroadCompanion/setup_offroad_companion` (.bat / .sh). It downloads BeamNG.Earth's source for the newest release
   next to this folder and runs BeamNG.Earth's own installer (Python 3.10+, a few minutes). If the download is
   blocked, download the zip from GitHub (Code > Download ZIP) and run `setup_earth_source --zip PATH`.
2. From then on, start `OffroadCompanion/run_offroad_companion` instead of the .exe (close the .exe first), then start
   BeamNG.drive yourself. The Offroad Companion runs in that same window (its lines start with `[Offroad]`) and stops with
   it; `run_companion_only` is only for BeamNG.Earth's own .exe (or add `--no-gps` and run it in its own window).

Your map cache is shared, so nothing is downloaded twice.

### Wheel ruts where the track blends in

On light desert sand (San Felipe) the dirt track is the ground's own colour and disappears from the driver's seat.
With **Wheel ruts: Auto** (Settings), BeamNG.Earth's server adds two darker wheel ruts along the track only where
that happens. It compares the satellite imagery under the track (BeamNG.Earth's own, from its cache; nothing extra
is downloaded) with the dirt's colour. Elsewhere the track keeps its normal look. **Always** puts ruts all along it,
**Off** none. The rutted sections of the track terrain (below) get braided ruts whatever the setting but **Off**
(drawn once the ground there is planned; the planner works ahead of the car, and a road tile never waits for it).
The ruts lie on the track's own surface, over crests and dips. Ruts need BeamNG.Earth's server from
source (`run_offroad_companion`); where the imagery has not been downloaded yet, they appear the next time that
ground loads.

### Track terrain: whoops, washes, berms, banked corners, ruts, rocks, sand traps, rock crawls

The elevation data is 30 m, so a desert track laid on it is a smooth sheet, and you can cut across anywhere. With
**Track terrain** (Settings) on **Auto** (the default since 1.6.1) or **Rough**, BeamNG.Earth's server adds a desert race course's relief to the
ground along the course, wherever it runs on dirt (its own dirt track, or a dirt or gravel road it follows):

- whoops: rolling bumps across the track about 10 m apart, high in whoop sections (about a third of a course) and
  low rollers elsewhere;
- washes crossing the course and kickers (a ramp up, then a short drop). A wash is a dry streambed: an eased bank
  down, a flat floor 6-18 m long, an eased bank up, mostly 15-45 cm deep and now and then 70 cm, about one per km
  (ground version 4; before it they were narrower, deeper holes about every 600 m);
- sand piled on the outside of the turns, a low windrow along the edges, the track floor worn in a little;
- broken ground everywhere, and stepped rock ledges in canyons and on rocky hillsides, with boulders beside the
  track there (BeamNG.Earth's own desert rocks: they collide near the car).
- banked corners (ground version 5): some tight corners tilt into the turn like a Baja bowl, the outside pushed up
  into a lip of dirt that eases back into the ground, the inside dug a little. The tighter the corner and the rougher
  the ground, the likelier: on **Rough** about a third of the tightest corners, on **Extra** most, never every one,
  none on **Flat** or **Mild**, on straights or in rock. Each 150 m stretch of the course decides from its place on
  the Earth, and the bank eases in and out with the corner;
- rutted sections (ground version 5, **Mild** or rougher): stretches worn by the tyres, the floor lower, windrows of
  dirt at the edges, the ground chopped up, with braided wheel ruts drawn on the track that wander and split. More of
  them where the track is narrow and the ground rough, fewer on graded roads. (The physics ground is a 2 m grid, so
  the narrow grooves themselves are drawn; the ground takes the worn floor, the windrows and the chop.)

**Ground version 6** keeps all of it and its heights but rounds every shape off. The game's ground is a lattice of
triangles 2 m apart, and narrower shapes (windrows a metre wide, the sand on the outside of the turns, the broken
ground's small bumps, the banked corner's edge) stood on it as saw teeth and lone spikes, to the eye and to the tyres.
Now nothing is narrower than about 6 m or changes over less than about 3 m: whoops a little longer, the broken ground
in long swells, the windrows and the turns' sand as wide soft mounds, the banked corner a smooth bowl with its lip just
past the edge, and the tallest places easing into their limit instead of flattening off.

**Ground version 7** adds sections where the track changes with the ground it crosses, the way a Baja course does.
Each comes only where the place has it, and where it may come, each stretch of 130-180 m decides from its place on
the Earth whether it does, easing in and out:

- **sand traps**: where a dry wash crosses or runs along the course (most of them), on a desert canyon's floor and by
  the sea (some), and now and then on open, flat, bare desert. The track sinks into deep soft sand (about 25 cm),
  its floor churned into soft swells, the sand thrown up beside it, all sand underfoot. Never on a lake, rarely on a
  mapped dirt road;
- **rock sections**: in canyons and on rocky hillsides: the track runs over rock, its ledges and lumps stronger, the
  whoops lower, loose gravel at its edges and more boulders beside it. Never in a wash or on a lake;
- **gravel**: on the alluvial fans at the foot of the mountains (a desert track climbing or falling a steady 2.5-12 %
  grade), in creek beds in green country, on broken ground on the way into the rocks, and on dirt roads in the hills:
  gravel underfoot, the track a little smoother, a low windrow of gravel along its edges;
- **rock crawls** (**Auto** only, where the course file's DANGER waypoints count): about 7 in 10 DANGER waypoints
  that sit in a canyon become a rock crawl 70-160 m long. The track is a staircase of tilted rock shelves, each step
  up or down over about 3 m, with boulders of 30-70 cm in the track and a line weaving between them that is always
  clear, and bigger boulders beside it. The waypoint's own ditch or kicker gives way to it.

A sand trap, a rock section and a crawl show the ground itself: the dirt track is not painted over them, so you see
the place's own sand or rock. Gravel keeps the dirt track's look. The heights follow **Track terrain** (none on
**Flat**; a sand trap is never deeper than on **Rough**); the sand, rock and gravel underfoot are there on any
setting, since they are the place's ground.

None on asphalt (it fades out over about 30 m where the course crosses or joins a paved road), and dry or salt lakes
(mapped as intermittent or salt water) stay mostly smooth. **Mild** is about half as high, **Extra** about 1.6
times, **Flat** turns it off (the setting decides where the banked corners and rutted sections are, not their size).
The physics ground, the dirt track's surface and the ground you see all take the same heights, so the tyres and the
picture agree.

Where the course runs along a steep hillside, BeamNG.Earth cuts the road into it with a retaining wall's step: a flat
strip, then the ground straight up. Beside a paved road a stone wall stands there; beside a dirt road nothing does, so
the track ran beside a smooth bare cliff. Along the course's dirt (its own track, or a dirt road it follows) that step
is a sloping cut bank instead, as a grader leaves it: up from the strip at about 39 degrees (steeper only where the
hillside itself is so steep it would not meet it within 15 m), never above the hillside. Only those places change: the
track, the downhill side, every other road and every gentle transition stay as BeamNG.Earth grades them. Any track
terrain setting, Flat included.

**Auto** (the default) mixes them along the course: each stretch of 1-3 km is fast and smooth (about 10 % of a course), mild
(about 25 %), rough (about 40 %) or extra rough (about 25 %), blending over about 100 m. From about 160 m before each
DANGER waypoint of the course file to about 100 m after it, it is extra rough, and at the waypoint there is a hazard:
a deep ditch, a big kicker or a rock garden. Boulder fields stand beside the track on about a third of the course
(none on the rest, a few or many where they are), more on rocky ground, never on lakes or asphalt, using the rock
models BeamNG.Earth already uses in that area. All of it is picked from the course's place on the Earth and the
course file, so everyone driving the same course sees the same sections, hazards and rocks.

A course recorded beside a dirt road (a GPS line often runs 10-20 m off the road it followed) takes that road as its
own when it runs the same way within 25 m: no second track is laid beside it, and the relief, the wheel ruts and the
signs go on that road. A paved road counts only within 5 m (a desert course beside a highway is not on the highway).
Where the laid track meets the road the course takes (or leaves it for open ground), the track's end bends onto the
road's middle over 10-50 m and narrows to the road's width, so the two join like a fork instead of the track stopping
beside the road.

It is deterministic: every bump comes from a hash of its place on the Earth, every wash and kicker from where the
course is, and the rest from the course, the map and the elevation data. The same course in the same place is the
same ground on every computer, every time. A change of setting shows on ground loaded after it (at the next world
shift). Needs BeamNG.Earth's server from source (`run_offroad_companion`).

### The ground's surface: sand, mud, loose and packed dirt

BeamNG.Earth already gives the physics ground a BeamNG ground model from the land cover (bare land loose dirt,
shrubland dusty dirt, grass, wetland mud, steep ground rock) and lays the course's track as plain dirt. Along the
course (the track and 20 m either side of it) the companion puts down the ground the real place has, from what is
mapped and measured there, never at random:

- **sand** in dry washes (streams and rivers mapped as intermittent, in dry country), on sandy canyon floors in the
  desert (the ground rising on both sides) and on beaches (within 45 m of the sea);
- **mud** on the banks of rivers, streams, lakes and ponds that hold water all year (6 m back from the water), and in
  wetlands;
- **gravel** in creek beds in green country, and where the track runs over rocky ground (from ground version 7 also
  the gravel sections, with **rock** in the rock sections and crawls and **sand** in the sand traps: see above);
- **hard dirt** on graded dirt roads the course follows, on dry lake beds (playas are packed hard) and on tracks
  through green country;
- **loose dirt** on a desert track's sides and piled on the outside of its turns; its racing line is packed.

**Plants on the track** (ground version 4): BeamNG.Earth grows its grass and scrub on the grassland and shrubland
ground. The track carries them only where the land beside it has them, never through bare desert, and never where the
wheels go: over its edges, and on wide tracks (over about 5 m) a grassy or scrubby strip down the middle between the
two wheel paths on some stretches (others run bare wall to wall). It uses the same ground cover as the rest of the
map, so it costs nothing more.

**Round the trees** (ground version 4): where the course line runs into trees, the track bends round them to the
nearest free strip of level ground (up to 6 m to the side), easing in and out like a driven trail. Where there is no
room, the trees standing on the track (or on a road or path the course follows) are taken out, as are bushes and
rocks.

Everything else (paved roads, steep rock, snow, the ground away from the course) stays as BeamNG.Earth made it. The
water and land cover come from the same data BeamNG.Earth uses (Overture water, ESA WorldCover), planned once per
course and kept with the rest of its ground, so everyone with the same ground code drives on the same sand and mud.
This is the physics ground (how the tyres grip and dig in); the ground you see keeps its satellite photo. It came
with ground version 3 (the plants and the trees with version 4): replays recorded earlier keep their own ground.

### Wet ground after rain

With **Wet ground after rain** on (Settings, the default), the ground is as wet as the real rain of the last three
days at that place has left it: the companion asks Open-Meteo (the weather service BeamNG.Earth's real weather uses)
for the hourly rain, and older rain counts less as the ground dries, faster in hot dry air and slower in cool damp
air. While the game's own rain falls (BeamNG.Earth's weather; on BeamMP the server's), the ground is at least damp.

- **Grip:** dirt, grass, gravel, rock and asphalt lose some grip with the wetness, up to about what is measured on wet
  against dry surfaces (dirt about 15 %, grass about 25 %, asphalt as BeamNG's own wet asphalt when braking). Sand
  and mud stay as they are. It is gradual: a light shower barely shows, a soaked track slides.
- **Looks wet:** the ground and the roads you see go darker and glossier with the wetness, asphalt most; dry, they
  look as BeamNG.Earth made them.
- **Puddles:** when the ground is really wet, water stands in the closed dips of the track (the troughs between
  whoops, a dip held in by the ground on every side), filled part way, more the wetter it is, out to about 450 m
  ahead along the course so you can see them coming. A dip open to one side, a slope or a wash crossing the track
  holds none (the water would run off). While it rains or just rained they hold brown water with the sky in it;
  later the same day, thicker muddy water; a day or more after, opaque mud holes.

Everyone within a few km at the same hour gets the same wetness, and the same ground gives the same puddles on every
computer. When the setting is turned off or the ground dries, BeamNG's own grip comes back.

### Planned ahead of the car

BeamNG.Earth grades the ground it shows from each area's road data. When you drive faster than that data is ready,
a stretch of ground is shown before its roads are graded into it, and you see ungraded ground over the road that
you drive through (it corrects itself once that area is rebuilt). The course painter adds the dirt track to that
road data, so it plans the track around the car ahead of time: a background process of its own, at low priority,
plans the course nearest first where you are heading (the game tells it where you are through the companion) and
keeps it on disk for BeamNG.Earth's workers, so BeamNG.Earth never waits for it. If you still see ground over the
road without a course loaded, that is BeamNG.Earth's own streaming.

## Spectators

Where people gather at a desert race, they stand along the course (Settings, **Spectators**: Some, Lots or Off):
the biggest crowds at the start and finish under pop-up canopies with flags, the checkpoint crew's canopy, chairs and
cooler at each checkpoint, fans either side of the landing at the jumps (the track terrain's own kickers), groups well
back at the course file's danger spots, people who parked by the road at paved road crossings, and a group on the
inside of the hairpins. Besides the gates there is at most one crowd per 1.6 km of course (0.8 km on Lots), the best
spot of each stretch. They stand in little groups a clear 3 m past the track's edge (its real width, as the course
signs; canopies and parked trucks further), never on a road or a dirt track (the game's road map and OpenStreetMap's
roads and tracks around you, which the companion fetches while a course is loaded), clear of every pass of the course (a tight hairpin's inside is its other leg: they step back past it, or stay home), face
the course and turn to watch you go by. Parked trucks and canopies only stand on open, nearly level ground: where a
roof, a wall or a steep slope is under one, it moves a few metres along the line or is left out, so none sits on a
building or hangs off a hillside. Nothing collides: a crowd never ends a run. Where they stand, how many, their
poses and their clothes are all picked from the course's place, so everyone on the same course sees the same crowds.

**Lots** lines the course the way a Baja race crowd does: people packed along both sides (behind an orange safety
fence in town or along a really big crowd: each piece laid along the course's curve, left out where a corner is too
sharp for a straight piece), pop-up canopies behind them, pickups and SUVs parked nose-in behind those, flags in the crowd (Mexico's in
Mexico) and light towers at the ends of the start, finish and checkpoints. The closer to a town, the bigger it gets:
a jump out in the desert has a 45 m line of a few people a metre, the same jump at the edge of a city a line four
times as long, packed, with a canopy and a truck every few metres; near towns, stretches with nothing special get a
plain line too. How urban each stretch is comes from OpenStreetMap's cities, towns and villages along the course
(fetched once per course by the companion, kept for a year), so it stays the same on your computer; a friend whose
companion fetched it at another time could see slightly different crowd sizes.

Up close the spectators and the parked trucks are drawn in detail (rounded limbs, hands, faces, caps and sombreros;
round wheels, windows, grilles, mirrors); from about 40 m (a truck a little further) the game switches each to a simple
model of its own, so a big crowd costs about what it did.

**After dark** (Settings, **Night lights**: On, Bright or Off) the crowds light up once the sun has set where you are
(the game's time of day): a campfire behind each crowd, a lantern under every canopy, and towable light towers at
the start, the finish and the checkpoint crews. The nearest 16 of them light the ground for real (no shadows, so
they cost about what a few car lamps do); the rest glow. Bright gives each more light. Settings shows whether it is
night there and how many are lit.

**Crowd sound** (On or Off): the crowds near you cheer and clap, a seamless loop from where each one stands. It
comes in as you get within about 250 m, louder as you near and to the side the crowd is on, and fades out as you
leave. The nearest few play at once; bigger crowds are louder, and the start, finish and checkpoints play two loops
together. **Test crowd sound** plays one 25 m ahead of the car for a few seconds and Settings says how it played. (The
sound is mglennsound's ["AF Crowd Cheer Clapping LOOP"](https://freesound.org/people/mglennsound/sounds/678542/) on
Freesound, CC0, started at three points of the loop.)

## Replays

BeamNG.Earth's world is a local frame around a point on the Earth that moves on every ~10 km as you drive (the world
and the car shift together). A replay stores the car's positions in the frame of their moment, so played back later,
when the world is somewhere else, the car drives over the wrong ground (or floats over none). With **Replays in
BeamNG.Earth: Follow the recording** (Settings, on by default), the app logs where the world was while the game records
a replay (a small file per recording, in `settings/offroadCompanion/replays/`, the last 30 kept). When you watch it, it finds
each moment by the replayed car's position, moves BeamNG.Earth's world to where it was recorded and pauses the game
until the ground under the car is in, then plays on; where the recording moved the world, the playback does too, and
seeking works. Meanwhile BeamNG.Earth's own world moves, drop hold and edge guard leave the replayed car alone; they are
back when the playback ends. Replays recorded before this (or with it off) have no log and play as before. BeamNG cannot play back a replay file
over 2 GB once the game has been restarted (it lists its size as "16384 PB" and plays it with no car; about 50-60
minutes of driving), so a recording is split before that: near 1.8 GB it is stopped (saved) and a new one started a
second later, with a message on screen; Settings shows the recording's length and size meanwhile.

A replay also gets back the ground it was recorded on. The recording notes the course, the track settings and the
**ground code** (Settings, under the track options, e.g. `T1-3f9a2c`: the name of exactly that ground), and the
companion keeps a copy of the course's planned ground under the recording's name (`snapshots/`, the last 60). If you
watch it after changing the track terrain or size, loading another course, or updating to a version whose ground is
different, the playback pauses, asks for the recorded course and settings with the server pinned to that copy,
rebuilds the ground around the car and plays on; when it ends, your own settings come back and the ground around
the car is built again with them. Replays recorded before this have no ground noted: they play on today's ground.

## The same ground, every time

Everything that shapes the ground along a course comes from the course file, its settings and BeamNG.Earth's own data,
never from timing or chance: every bump, dip, wash, rock and the track's own width is computed from fixed rules on
the course's place on the Earth. So that it stays that way:

- the first ground planned for a course is kept (on disk, per course and size) and never planned again, by any of
  the server's processes: whichever planned a stretch first, every other one uses that;
- data that has not arrived yet (tree heights, dry lakes put off while BeamNG.Earth was busy) is waited for, never
  taken as "none"; ground near the car whose plan is not ready yet is asked again within seconds;
- the ground has a version (`OffroadCompanion/gpsd/terrain.py`; version 2 added the cut banks on hillsides, version 3 the sand, mud, gravel and loose or packed dirt along the course, version 4 the plants on the track, the
  track round the trees and the gentler washes, version 5 the banked corners and rutted sections, version 6 the
  rounder shapes, version 7 the sand traps, rock sections, gravel and rock crawls; a replay
  recorded on version 1 still gets version 1's ground). A change to the code that would move a single bump makes a
  new version and keeps the old one as it was; a golden test (`tests/test_terrain.py`) fails on any change to an
  existing version's ground;
- the ground code names one ground: the same code on two computers (same BeamNG.Earth version) is the same ground,
  bump for bump. For racing together (BeamMP), everyone loads the same course with the same track size, terrain and
  ruts settings, and the codes match.

### Sharing a ground code

Settings shows the full ground code under the track options (e.g. `T3-3f9a2c-0C1G0S010R1G4`): it carries the ground's
version, the track size, terrain and ruts settings and the BeamNG.Earth version. **Copy** puts it on the clipboard.
A friend loads the same course, pastes it into the box under it ("Paste a friend's ground code") and presses **Use** (or Enter): the companion checks it against
the loaded course and switches their track settings (and ground version) to the ones that make exactly that ground.
If the code is for another course, needs another BeamNG.Earth version or a newer companion, it says so instead. The
change applies to ground loaded from then on (the world around the car is rebuilt at the next world shift). Changing
a track setting by hand afterwards goes back to your own settings.

Wheel ruts on **Auto** are only paint (no bumps), but where they go depends on the satellite imagery having been
downloaded; **Always** or **Off** look the same for everyone.

## When there is no dirt track

The course strip in the app says what the track is doing where you are:

| Status | Meaning |
|---|---|
| none needed near you | OpenStreetMap has a road along the course here, so no track is added. If the road is not in the game, that road is missing from BeamNG.Earth's own data. |
| planning N km near you | the companion is still fetching roads and terrain |
| no map data (…) | OpenStreetMap or the terrain tiles could not be reached; it tries again |
| waiting for BeamNG.Earth's road tiles | the track is ready, and is drawn when BeamNG.Earth's road tiles arrive |
| restart OffroadCompanion\run_companion_only | the companion is an older version than the mod: restart run_offroad_companion (or run_companion_only) |

`dump(offroadCompanion_main.debug())` in the game console shows the details.

## Where courses come from

| Source | What it has |
|---|---|
| **SCORE International** (score-raceinfo.com) | The official course files SCORE posts for the Baja 1000, Baja 500, Baja 400 and San Felipe 250 (GPX/KML/KMZ, Pro and Sportsman). The 2026 Baja 1000 files are due late October; they appear in the list once posted. |
| **Race.mx** (open data, CC BY 4.0) | Mexico's circuits, ovals and Baja start lines; circuit outlines come from OpenStreetMap at each venue. The 2026 Baja 1000 towns and checkpoints in race order. |
| **OpenStreetMap circuits** | Real track outlines (highway=raceway, karting, motocross) within 10–150 km of the car, anywhere. |
| **Baja Tracker** | Baja Tracker's race maps are private to each team (password protected), so nothing can be downloaded from it. Ask your team admin for the course as KML/GPX, then use My files or Link. |
| **My files** | Any GPX / KML / KMZ / GeoJSON you put in `OffroadCompanion/tracks/`. |
| **Link** | Paste a link to a GPX / KML / KMZ / GeoJSON file. |

SCORE's files are often only waypoints (race-mile markers every 5 miles, VCPs, speed zones, hazards). When a file
has no course line, the app draws a rough line straight between the race-mile markers and marks it "Rough line";
corner calls are turned off on such lines since they would be invented.

## Install

**The easy way (Windows): one program.** Download `OffroadCompanion-<version>.exe` and double-click it. That's all:
no Python, no BeamNG.Earth folder, no setup step. It has BeamNG.Earth inside (the version this release is made for)
and does everything `run_offroad_companion` does:

- asks once, at its first start, where to keep the data that grows: **Enter** keeps it on the system drive, **F**
  lets you choose a folder (the folder window, or type / paste the path), for example on another drive. There it makes
  `OffroadCompanion` (the courses' planned ground, replays' ground, your tracks, downloads) and `BeamNG.Earth cache`
  (BeamNG.Earth's map downloads, up to 20 GB: BeamNG.Earth's own .exe uses that folder too), and offers to move what
  is already there (Enter) or start empty (N: downloaded again). It is remembered; `--pick-data-dir` asks again (and
  moves it again). If that drive is unplugged it says so and asks. BeamNG.Earth's logs and the game's own user folder
  stay where they are;
- finds the BeamNG.drive user folder the game really uses (also one moved out of AppData; if it can't tell, it lists
  what it found and you type the number), and remembers it (`--pick-user-dir` to choose again);
- puts both mods (BeamNG.Earth and Offroad Companion) into the game's `mods` folder, and keeps them up to date;
- runs BeamNG.Earth's world server with the course painter and Offroad Companion's helper in its window, then starts
  BeamNG.drive (through Steam) and, when you have it, BeamMP; closing the game stops it all (about 10 seconds after,
  and the window closes by itself). Closing the window first stops the world server and the BeamMP it started too,
  and a BeamMP left running by an earlier start is closed before a new one starts (it lost the session's player list
  and ping: "No players... something is wrong").

Use it instead of BeamNG.Earth's own .exe (not both at once). Your BeamNG.Earth map cache and settings are shared with
it. The first time, Windows may say "Windows protected your PC" (the program isn't signed): **More info**, then
**Run anyway**. Put it wherever you like (Desktop, a games folder); it keeps nothing next to itself: your tracks and
planned ground are in the data folder chosen at the first start (`%LOCALAPPDATA%\OffroadCompanion` when kept on the
system drive; tracks of an earlier source install are copied over). The
same options as BeamNG.Earth's .exe work (`--no-game`, `--cache-dir`, `--game-dir`, `--no-beammp`, ...);
`--companion` runs only the helper (beside BeamNG.Earth's own .exe). To update, download the new .exe.

**From source** (Linux, or to change the code):

You need BeamNG.Earth set up from its source zip (its `start.py`, `server` folder and `install.py`), Python 3.10+
and BeamNG.drive started once.

1. Unzip `OffroadCompanion-<version>.zip` (e.g. `OffroadCompanion-1.2.0.zip`) **inside your BeamNG.Earth folder**
   (you get `BeamNG.Earth\OffroadCompanion\...`). It is not a game mod: do not put it in `mods`.
2. Run `OffroadCompanion\setup_offroad_companion.bat` once (Linux: `OffroadCompanion/setup_offroad_companion.sh`). It:
   - uses the BeamNG.Earth folder it is in (nothing is downloaded), when that is a version Offroad Companion works with
     (1.7.3, 1.7.2, 1.7.1, 1.7.0, 1.6.3, 1.6.2, 1.6.1, 1.6.0 or 1.5.x); otherwise it downloads the source of **BeamNG.Earth 1.7.3-beta**, the version this
     release is made for, next to it, never simply the newest (a newer BeamNG.Earth may change what the course painter
     hooks into). If the download fails it prints the address of that release's zip to fetch by hand (then
     `setup_offroad_companion.bat --zip PATH`);
   - finds the BeamNG.drive user folder **the game really uses**, also when you moved it out of AppData
     (e.g. `D:\BeamNGUser\current`, from the game's own setting). If it can't tell, it lists what it found and you
     can type the folder. Or give it: `setup_offroad_companion.bat --user-dir "D:\BeamNGUser\current"`;
   - runs BeamNG.Earth's installer with that folder (BeamNG.Earth's mod into it, the server's Python packages), and
     copies the Offroad Companion mod (`offroad_companion.zip`) into the same `mods` folder.
3. To play, start `OffroadCompanion\run_offroad_companion.bat` and keep its window open: BeamNG.Earth's server with the
   course painter (instead of `run_server.bat` or the .exe), and Offroad Companion's helper program in the same window
   (its lines start with `[Offroad]`). It passes your user folder along and keeps both mods up to date. The user
   folder you chose once is used from then on without asking; to choose another, start it with `--pick-user-dir`.
   (`OffroadCompanion\run_companion_only.bat` starts the helper alone, for BeamNG.Earth's .exe.)
   
   Then start BeamNG.drive, load the BeamNG.Earth level, and add **Offroad Companion** from the UI apps menu.

Without the course painter (BeamNG.Earth's .exe or `run_server`), the app still works: the dirt track is drawn by the
game, and the course is not cleared of buildings and walls.

**Coming from BeamNG.Earth GPS** (before 1.2.0): unzip the new version next to the old `companion` folder and start
`OffroadCompanion\run_offroad_companion.bat`. The first start moves everything over: the old mod
(`beamng_earth_gps.zip`) is put aside so the game does not run both, the app keeps its place in your UI layouts,
your settings, replays, saved tracks, planned ground and remembered folders carry over, and the old `companion`
folder is renamed `companion (old - now OffroadCompanion)`: delete it when you like. Ground codes stay the same.

### BeamNG.Earth 1.7, 1.6 and BeamMP

Works with BeamNG.Earth 1.7.3 (the version the .exe has inside), 1.7.2, 1.7.1, 1.7.0, 1.6.3, 1.6.2, 1.6.1 and 1.6.0 (and 1.5.x). With 1.7:

- The cells the course runs through keep what 1.7 adds to their roads: OpenStreetMap's level crossing details (gates,
  lights or crossbucks where a road crosses a railway) and, when turned on (`BNE_GRADESEP=on`), its grade separations.
- 1.7's **Rocks** setting off hides the boulders beside the track too (they are BeamNG.Earth's own rocks). For racing
  together, leave it the same on every computer: the boulders collide.
- 1.7 no longer has BeamMP's sharing port; nothing changes for the companion (it never needed it).
- 1.7's high-voltage lines' lattice towers never collide with Offroad Companion's mod in the game: a 36 m steel tower
  where a mapped line crosses open country (often on or beside a course) stopped a race dead. The substations' parts
  behind their fences stay solid.
- 1.7.1 joins OpenStreetMap's lane tags to the roads, and sets every BeamNG.Earth ground layer's photo size from its
  graphics settings: the course's sand and gravel layers are named like BeamNG.Earth's own (bngEarthGroundOcSand,
  bngEarthGroundOcGravel) so they follow it too.
- 1.7.2 builds the road tiles' buildings and street furniture, the trees and the far buildings once per tile of a
  global grid, and the game keeps them across rebases and teleports near. When the course (or its size or terrain)
  changes, the game drops its roads, buildings and trees round the car and asks BeamNG.Earth for them again, built for
  the new course, so no building or tree kept from before stands on the new track. Without the course painter (BeamNG.Earth's own .exe), the in-game track is drawn
  on those tiles too, and drawn again after each rebase.
- The cells the course runs through no longer give BeamNG.Earth's bridge finder (grade separation) the track when it
  reads their neighbours: it deadlocked the road builders where the map has short tunnels nearby (Ensenada).

What changed with 1.6:

- BeamNG.Earth now paints roads into the ground's photo instead of laying road surfaces over it. The dirt track is
  painted the same way (a brown tint that keeps most of the photo), and the wheel ruts still go along it.
- After a long teleport BeamNG.Earth first places the car on quick ground without levelled roads (and without the
  track's whoops and dips), then swaps in the finished ground. A replay waits for the finished ground before it plays.
  **Teleport to start** tells the course painter where the start is first, so the track there is planned before the
  ground is built.
- 1.6.1 shares the planning of the roads between BeamNG.Earth's processes on disk; the dirt track is part of those
  plans, so each ground code gets its own (another course or setting never picks up old plans).
- 1.6.3 keeps what it built around places you drive through again (its revisit cache). The dirt track is part of that
  ground, so each ground code keeps its own (a different course or setting never shows another's track), and ground
  built while the course's data was still missing is not kept.
- In a BeamMP session BeamNG.Earth cannot pause the game while the ground under you loads (it would stop everyone's
  cars on your screen), so it holds only your car, with its gravity off. Its springs then pushed it up and it floated
  away until the ground came and it fell; Offroad Companion keeps it still every frame of the hold.
- BeamNG.Earth's big map in a BeamMP session with no other player known kept failing to draw (its empty player list
  reached the page as `{}`, not a list: "(state.value.others || []).map is not a function" in the console every
  second); Offroad Companion hands that empty list on as none.
- Joining a BeamMP server turns your other mods off and leaves them off. Leaving a server that sends Offroad Companion
  turns yours back on in the game, and starting `run_offroad_companion` does too, as BeamNG.Earth does for its own.

**BeamMP.** In a BeamMP session the game loads only the mods the server sends, so for Offroad Companion the server needs
it too: unzip `OffroadCompanion-BeamMP-Server-<version>.zip` into the BeamMP server's folder (it adds
`Resources/Client/offroad_companion.zip`, next to BeamNG.Earth's own). Each player who wants the dirt track, the
terrain and the cleared course runs `run_offroad_companion` (instead of the BeamNG.Earth app) and the BeamMP
launcher. BeamNG.Earth switches to its own BeamMP app layout when you join: add **Offroad Companion** to it once from
the UI apps menu.

To race the same ground, everyone loads the same course with the same track size, track terrain and ruts settings,
on the same BeamNG.Earth version, and checks that their **ground code** (Settings) matches. BeamNG.Earth 1.6 shares
the building of distant landscape between players near each other; with the course painter, tiles are only shared
between players with the same ground code (anyone else's are built on your own computer), so nobody gets distant
ground without the track, or with another course's. Replays work the same in a BeamMP session: each player
there has their own world origin (BeamNG.Earth converts the other players' cars between them), so a replay moves
yours to where it was recorded as it does alone. While it plays, BeamNG.Earth does not move you onto the other
players' origin (when its shared generation is on); afterwards it does again.

## Use

- **Search**: type a place, pick a result (Enter if nothing comes up). Autodrive and End route appear under the
  street name.
- **Courses**: pick a source, pick a course. Then To start / Teleport to start, and drive.
- **Settings**: language, units (or follow the game's), the course line on the ground, road directions between
  course waypoints.
- **Make track**: record, tap or add points, then Save and load (see above).
- `+` / `−` on the map zoom it; the map turns with the car. Streets and names can be hidden in Settings.
- **▾** (end of the tabs) hides the app to a small button; a key can be bound to it (Options, Controls).
- **Size**: resize the app in the game's UI editor. Text, buttons and the map scale with its width. When it is too
  short for what is open, it shrinks a little to fit; below that the part under the map scrolls, while the
  direction box, the map and the tabs always stay whole.

Already-loaded ground keeps the old buildings and bridges until it is loaded again: when you pick a new
destination or course, the roads around you are reloaded, and teleporting or driving on loads fresh ground.

## Services and credits

- Routing: OSRM on OpenStreetMap (FOSSGIS instance, with project-osrm.org as fallback); data © OpenStreetMap
  contributors, ODbL.
- Circuits: OpenStreetMap via the Overpass API. The public Overpass servers are often busy: the companion asks the
  main one (overpass-api.de) and Private.coffee in turn (the one that answered last first), each for at most 25 s, and
  a busy one (HTTP 502 / 504, a timeout) once more with a minute's patience; the first try goes to both at once. It
  uses an answer either gave before (kept a week; areas on a 5 km grid, so spots near each other share one), an older
  one when none answers, and loads the circuits around the car in the background as you drive, so the list is usually
  there at once. The app waits up to four minutes for a list or a course and says when its source is slow.
- Venues and Baja 1000 race order: Race.mx, CC BY 4.0.
- Courses: SCORE International.
- Search: Photon by komoot and Nominatim (Enter only, at most one request a second, as its policy asks), data
  © OpenStreetMap contributors; BeamNG.Earth's search without the companion.
- Streets on the map: © OpenStreetMap contributors via the Overpass API (tiles of about 2 km, cached).
- Dirt track (the .exe way): roads © OpenStreetMap contributors via Overpass; elevation AWS Terrain Tiles
  (Mapzen / Tilezen, open data).
- Crowd sound: ["AF Crowd Cheer Clapping LOOP"](https://freesound.org/people/mglennsound/sounds/678542/) by
  mglennsound on Freesound, CC0.

Offroad Companion itself is under the MIT License (`LICENSE`).

The companion identifies itself, waits at least a second between requests to each service and caches what it
downloads in `OffroadCompanion/cache/` (`--offline` uses only the cache).

## For developers

```
OffroadCompanion/earth_gpsd.py        the companion (asyncio, standard library only); protocol in its docstring
OffroadCompanion/gpsd/trackparse.py   GPX / KML / KMZ / GeoJSON -> course line + classified waypoints
OffroadCompanion/gpsd/routing.py      OSRM with steps -> instructions (en / es)
OffroadCompanion/gpsd/sources/        score, racemx, osm, files
OffroadCompanion/gpsd/courseroads.py  where to lay the dirt track and how wide (pure Python: shared by both ways)
OffroadCompanion/gpsd/paintsource.py  the plan from OpenStreetMap + AWS terrain tiles (the .exe way)
OffroadCompanion/gpsd/earthpatch.py   hooks BeamNG.Earth's MapData.cell to add the track to its road data (the source way)
OffroadCompanion/gpsd/corridor.py     the clear course / route: buildings, short and low bridges, walls across it left out
OffroadCompanion/gpsd/streets.py      streets with names for the map (Overpass tiles)
OffroadCompanion/gpsd/overpass.py     the Overpass servers: in turn, the last good one first, cached answers
OffroadCompanion/gpsd/geocode.py      the app's search: coordinates, Photon, Nominatim on Enter
OffroadCompanion/gpsd/ruts.py         wheel ruts where the track blends into the ground (imagery contrast)
OffroadCompanion/gpsd/relief.py       the track's relief: whoops, washes, berms, ledges, boulders (global hashes)
OffroadCompanion/gpsd/variety.py      the track's sections: sand traps, rock sections, gravel, rock crawls
OffroadCompanion/gpsd/terrain.py      the ground's version and seal (the rule for changing the ground: in its docstring)
OffroadCompanion/gpsd/spots.py        where spectators gather: the jumps (relief's kickers, bit for bit) and paved crossings
OffroadCompanion/gpsd/urban.py        how urban the course is along it (towns from OpenStreetMap): the Lots crowds' size
OffroadCompanion/app_launcher.py      the .exe's start: BeamNG.Earth's launcher with the painter and the helper in it
OffroadCompanion/setup_earth_source.py  BeamNG.Earth from source next to the companion, once
OffroadCompanion/start_earth_with_tracks.py, earth_tracks_server.py   BeamNG.Earth's start.py with the painter
mod/offroad_companion/lua/ge/extensions/offroadCompanion/
    main.lua    the extension (offroadCompanion_main): BeamNG.Earth hookup, the app's calls, the UI hook
    nav.lua     turn-by-turn along the route
    course.lua  course guidance: progress, race mile, VCPs, zones, corner calls, timing
    poly.lua    polyline maths (pure)
    ribbon.lua  the course line on the ground (debugDrawer)
    tracks.lua  the dirt track drawn on BeamNG.Earth's road tiles (the .exe way)
    link.lua    socket client to the companion
    replaysync.lua  replays: where the world was while recording, the world moved there on playback, and the
                    ground it was recorded on
    crowds.lua  spectators: where they gather, their groups, watching the car, their lights after dark (models:
                tools/make_crowds.py)
    crowdsound.lua  the crowds' sound near the car, looping (the loops: tools/make_crowd_sounds.py)
    mphold.lua  BeamMP: our car kept still while BeamNG.Earth holds it for the ground
    earthfix.lua  small fixes to BeamNG.Earth's own code while it runs (its big map's player list in BeamMP)
    markers.lua  course signs (VCP, STOP, banners, arrows, stakes) near the car (models: art/offroadcompanion, made by
                 tools/make_markers.py, then as BeamNG's own .cdae by tools/make_cdae.py with BeamNG.Earth's writer)
    streetmap.lua  the streets near the car for the map (selection sent on its own hook when it changes)
    editor.lua  making a track: record / tap / checkpoints, saved by the companion as GPX
mod/offroad_companion/ui/modules/apps/OffroadCompanion/   the app (AngularJS, like BeamNG.Earth's HUD apps)
```

Release zips: `python3 tools/package.py` (named after `OffroadCompanion/VERSION`, which is also the game app's
`M.VERSION`: raise both for a release). Then the .exe: `python tools/build_exe.py --earth PATH --bootloader run.exe`
with a Windows Python 3.12 that has pyinstaller and BeamNG.Earth's `server/requirements.txt` (on Windows, or under
Wine), PATH the BeamNG.Earth source folder of the version the release is made for. It is built like BeamNG.Earth's
own .exe (PyInstaller, one file, its own bootloader, a version resource; its docstring has the details) and ends by
running the .exe's `--selftest`: the course painter in the server and in a worker process, with the same code
fingerprint (ground code) as a source install.

Tests: `cd OffroadCompanion && python3 -m unittest tests.test_*` (each file) (the painter's tests also need numpy and a
BeamNG.Earth checkout: `EARTH_ROOT=/path/to/BeamNG.Earth`) and
`cd mod/tests && luajit test_guidance.lua && luajit test_main.lua && luajit test_tracks.lua && luajit test_markers.lua && luajit test_replay.lua && luajit test_crowds.lua && luajit test_crowdsound.lua`.

In the game console, `dump(offroadCompanion_main.debug())` shows the app's state.
