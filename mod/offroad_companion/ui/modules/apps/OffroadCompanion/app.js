// Offroad Companion (the in-game app; lua/ge/extensions/offroadCompanion/main.lua): turn-by-turn road navigation and race-course guidance.
// The game's UI browser cannot make web requests, so everything goes through the game's Lua (bngApi.engineLua);
// the Lua side pushes 'OffroadCompanionUpdate' five times a second while this app is on screen.
var EGPS_APP_BUILD = '2026-11-06 02:00'   // (main.lua M.BUILD: the same, or the game kept an older copy of one of them)
angular.module('beamng.apps')
.directive('offroadCompanion', ['$sce', function ($sce) {
  'use strict'

  // -- tulip arrows (rally roadbook style): a dot where you are, a stem, an arrow out at the turn's angle ----------
  var ANGLE = { 'straight': 0, 'slight-right': 40, 'right': 90, 'sharp-right': 135, 'uturn': 180,
                'slight-left': -40, 'left': -90, 'sharp-left': -135 }
  var GRADE_ANGLE = { 6: 25, 5: 40, 4: 60, 3: 85, 2: 110, 1: 135, hairpin: 175 }

  function tulip (angle, kind) {
    // 100x100 box; stem from (50,88) to (50,52), then out at `angle` (0 = straight on, + = right)
    var a = (angle || 0) * Math.PI / 180
    var ex = 50 + 34 * Math.sin(a), ey = 52 - 34 * Math.cos(a)
    var hx = Math.sin(a), hy = -Math.cos(a)            // arrow direction
    var px = -hy, py = hx                               // perpendicular
    var tip = [ex + hx * 8, ey + hy * 8]
    var l = [ex - px * 9, ey - py * 9], r = [ex + px * 9, ey + py * 9]
    var path = 'M50 88 L50 52 L' + ex.toFixed(1) + ' ' + ey.toFixed(1)
    var head = 'M' + l[0].toFixed(1) + ' ' + l[1].toFixed(1) + ' L' + tip[0].toFixed(1) + ' ' + tip[1].toFixed(1) +
               ' L' + r[0].toFixed(1) + ' ' + r[1].toFixed(1) + ' Z'
    var extra = ''
    if (kind === 'roundabout') {
      extra = '<circle cx="50" cy="52" r="14" fill="none" stroke="currentColor" stroke-width="6"/>'
    }
    if (kind === 'arrive') {
      return '<svg viewBox="0 0 100 100"><circle cx="50" cy="88" r="7" fill="currentColor"/>' +
        '<path d="M50 88 L50 30" stroke="currentColor" stroke-width="8" stroke-linecap="round"/>' +
        '<path d="M50 14 L76 26 L50 38 Z" fill="currentColor"/></svg>'
    }
    return '<svg viewBox="0 0 100 100">' + extra +
      '<circle cx="50" cy="88" r="7" fill="currentColor"/>' +
      '<path d="' + path + '" fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="' + head + '" fill="currentColor"/></svg>'
  }

  function luaStr (s) {
    return JSON.stringify(String(s == null ? '' : s)).replace(/\\u([0-9a-fA-F]{4})/g, '\\u{$1}')
  }
  function luaNum (n) { var f = Number(n); return isFinite(f) ? String(f) : 'nil' }

  // The game's Lua JSON writes an empty table as {}: every empty object from Lua becomes [] here (the lists the app
  // walks: no waypoints near, no route, no draft; nothing here expects an empty object), in place
  function lists (v) {
    if (Array.isArray(v)) {
      for (var i = 0; i < v.length; i++) { if (v[i] && typeof v[i] === 'object') v[i] = lists(v[i]) }
      return v
    }
    if (v && typeof v === 'object') {
      var keys = Object.keys(v)
      if (!keys.length) return []
      for (var k = 0; k < keys.length; k++) { var x = v[keys[k]]; if (x && typeof x === 'object') v[keys[k]] = lists(x) }
    }
    return v
  }

  var KIND_LABEL = { vcp: 'VCP', checkpoint: 'Checkpoint', danger: 'Danger', speed_start: 'Speed zone',
                     speed_end: 'Zone ends', start: 'Start', finish: 'Finish', pit: 'Pit' }

  return {
    restrict: 'E',
    scope: {},
    template:
'<div class="bngApp egps" ng-class="[{\'egps-off\': !d.earth, ovbig: d.map.ov && ovv.big, mapbig: mapBigOn(), nocourse: !d.course, hid: ui.hidden}, \'notes-\' + (ui.notes || \'top\')]">' +
'<style>' +
'.egps{--bg:rgba(20,27,43,.86);--line:#2A3550;--cyan:#27D9FF;--sand:#E8B44A;--red:#FF4D3D;--green:#5BE38A;--ink:#EEF2F8;--mute:#93A0B8;' +
'  --s:1;position:relative;width:100%;height:100%;display:flex;flex-direction:column;background:var(--bg);color:var(--ink);border-radius:calc(10px*var(--s));' +
'  border:1px solid var(--line);overflow:hidden;font-family:"Noto Sans","Segoe UI",Roboto,sans-serif;font-size:calc(13px*var(--s));line-height:1.35;box-shadow:none}' +
'.egps *{box-sizing:border-box}' +
'.egps button{font:inherit;color:var(--ink);background:#22304A;border:1px solid #33425F;border-radius:calc(6px*var(--s));padding:calc(4px*var(--s)) calc(9px*var(--s));cursor:pointer}' +
'.egps button:hover{background:#2B3B5A}.egps button:focus-visible,.egps input:focus-visible{outline:calc(2px*var(--s)) solid var(--cyan);outline-offset:1px}' +
'.egps button.on{background:var(--cyan);color:#06222C;border-color:var(--cyan)}' +
'.egps button.quiet{background:transparent;border-color:transparent;color:var(--mute)}' +
'.egps input{font:inherit;color:var(--ink);background:#0F1524;border:1px solid #33425F;border-radius:calc(6px*var(--s));padding:calc(5px*var(--s)) calc(8px*var(--s));width:100%}' +
'.egps .num{font-variant-numeric:tabular-nums}' +
/* the roadbook box */
'.egps .call{display:flex;gap:calc(12px*var(--s));align-items:center;padding:calc(10px*var(--s)) calc(12px*var(--s));border-bottom:1px solid var(--line);min-height:calc(96px*var(--s))}' +
'.egps .tulip{flex:0 0 calc(76px*var(--s));height:calc(76px*var(--s));border:calc(2px*var(--s)) solid var(--ink);border-radius:calc(6px*var(--s));padding:calc(6px*var(--s));color:var(--ink);background:rgba(255,255,255,.04)}' +
'.egps .tulip svg{width:100%;height:100%;display:block}' +
'.egps .call.zone .tulip{border-color:var(--sand);color:var(--sand)}.egps .call.warn .tulip{border-color:var(--red);color:var(--red)}' +
'.egps .callTxt{min-width:0;flex:1}' +
'.egps .dist{font-size:calc(34px*var(--s));font-weight:800;letter-spacing:calc(-.5px*var(--s));line-height:1}' +
'.egps .what{font-size:calc(15px*var(--s));font-weight:600;margin-top:calc(4px*var(--s));overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}' +
'.egps .then{color:var(--mute);font-size:calc(12px*var(--s));margin-top:calc(3px*var(--s));display:flex;align-items:center;gap:calc(5px*var(--s))}' +
'.egps .then i{display:inline-block;width:calc(16px*var(--s));height:calc(16px*var(--s));color:var(--mute)}.egps .then i svg{width:100%;height:100%}' +
'.egps .idle{color:var(--mute);font-size:calc(14px*var(--s))}' +
/* map */
'.egps .mapWrap{position:relative;flex:1 1 0;min-height:calc(110px*var(--s));min-width:0}' +
'.egps .rest{flex:1 1 0;min-height:0;min-width:0;display:flex;flex-direction:column;position:relative}' +
'.egps.notes-top .rest{position:static}' +
'.egps.notes-bottom{flex-direction:column-reverse}.egps.notes-bottom .call{border-bottom:0;border-top:1px solid var(--line)}' +
'.egps.notes-left{flex-direction:row}.egps.notes-right{flex-direction:row-reverse}' +
/* the roadbook box beside the whole app: the arrow above the text, all down one column */
'.egps.notes-left .call,.egps.notes-right .call{flex:0 0 calc(124px*var(--s));flex-direction:column;align-items:stretch;justify-content:flex-start;gap:calc(8px*var(--s));min-height:0;border-bottom:0;padding:calc(12px*var(--s)) calc(10px*var(--s))}' +
'.egps.notes-left .call{border-right:1px solid var(--line)}.egps.notes-right .call{border-left:1px solid var(--line)}' +
'.egps.notes-left .tulip,.egps.notes-right .tulip{flex:0 1 calc(100px*var(--s));min-height:calc(36px*var(--s));width:auto;height:auto;aspect-ratio:1/1;align-self:center}' +
'.egps.notes-left .call,.egps.notes-right .call{overflow:hidden}' +
'.egps.notes-left .callTxt,.egps.notes-right .callTxt{flex:0 1 auto;text-align:center}' +
'.egps.notes-left .dist,.egps.notes-right .dist{font-size:calc(28px*var(--s))}' +
'.egps.notes-left .what,.egps.notes-right .what{font-size:calc(14px*var(--s));-webkit-line-clamp:3}' +
'.egps.notes-left .then,.egps.notes-right .then{justify-content:center;flex-wrap:wrap}' +
'.egps .zlab{display:flex;flex-direction:column;align-items:center;background:rgba(10,14,24,.75);border-radius:calc(5px*var(--s));padding:calc(2px*var(--s)) calc(3px*var(--s));line-height:1.15;pointer-events:auto}' +
'.egps .zlab b{font-size:calc(10px*var(--s));font-weight:700;white-space:nowrap}.egps .zlab span{font-size:calc(9px*var(--s));color:var(--mute);white-space:nowrap}' +
'.egps .call{flex:0 0 auto}.egps .lower{flex:0 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden}' +
'.egps .lower::-webkit-scrollbar{width:6px}.egps .lower::-webkit-scrollbar-thumb{background:#33425F;border-radius:3px}' +
'.egps canvas{position:absolute;inset:0;width:100%;height:100%}' +
'.egps .spd{position:absolute;left:calc(10px*var(--s));bottom:calc(10px*var(--s));background:rgba(10,14,24,.75);border-radius:calc(8px*var(--s));padding:calc(4px*var(--s)) calc(10px*var(--s));text-align:center}' +
'.egps .spd b{font-size:calc(24px*var(--s));font-weight:800;display:block;line-height:1}.egps .spd small{color:var(--mute);font-size:calc(11px*var(--s))}' +
'.egps .spd.fast{box-shadow:inset 0 0 0 calc(2px*var(--s)) var(--red)}' +
'.egps .limit{position:absolute;left:calc(10px*var(--s));bottom:calc(62px*var(--s));width:calc(46px*var(--s));height:calc(46px*var(--s));border-radius:50%;background:#fff;border:calc(5px*var(--s)) solid var(--red);color:#111;' +
'  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:calc(15px*var(--s))}' +
'.egps .zoom{position:absolute;right:calc(8px*var(--s));bottom:calc(8px*var(--s));display:flex;flex-direction:column;gap:calc(4px*var(--s))}.egps .zoom button{width:calc(28px*var(--s));padding:calc(2px*var(--s)) 0}' +
'.egps .toasts{position:absolute;left:calc(8px*var(--s));right:calc(8px*var(--s));top:calc(8px*var(--s));display:flex;flex-direction:column;gap:calc(4px*var(--s));pointer-events:none}' +
'.egps .toast{background:rgba(10,14,24,.85);border-left:calc(3px*var(--s)) solid var(--cyan);padding:calc(4px*var(--s)) calc(8px*var(--s));border-radius:calc(4px*var(--s));font-weight:600}' +
'.egps .toast.good{border-color:var(--green)}.egps .toast.bad{border-color:var(--red)}' +
'.egps .banner{position:absolute;left:calc(8px*var(--s));right:calc(8px*var(--s));top:calc(8px*var(--s));background:var(--red);color:#fff;font-weight:700;padding:calc(6px*var(--s)) calc(10px*var(--s));border-radius:calc(6px*var(--s));text-align:center}' +
/* status line */
'.egps .where{padding:calc(7px*var(--s)) calc(12px*var(--s));border-top:1px solid var(--line)}' +
'.egps .street{font-weight:700;font-size:calc(14px*var(--s));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
'.egps .sub{color:var(--mute);font-size:calc(12px*var(--s));display:flex;gap:calc(10px*var(--s));align-items:center;flex-wrap:wrap}' +
'.egps .row{display:flex;gap:calc(6px*var(--s));align-items:center;margin-top:calc(6px*var(--s));flex-wrap:wrap}' +
'.egps .grow{flex:1}' +
/* course strip */
'.egps .strip{padding:calc(7px*var(--s)) calc(12px*var(--s));border-top:1px solid var(--line)}' +
'.egps .bar{height:calc(4px*var(--s));background:#26324B;border-radius:calc(2px*var(--s));margin:calc(5px*var(--s)) 0;overflow:hidden}.egps .bar i{display:block;height:100%;background:var(--cyan)}' +
'.egps .ahead{display:flex;gap:calc(6px*var(--s));flex-wrap:wrap;margin-top:calc(4px*var(--s))}' +
'.egps .chip{border:1px solid #33425F;border-radius:calc(12px*var(--s));padding:1px calc(8px*var(--s));font-size:calc(12px*var(--s));white-space:nowrap}' +
'.egps .chip.vcp,.egps .chip.checkpoint{border-color:var(--cyan)}.egps .chip.danger{border-color:var(--red);color:#FFB3AA}' +
'.egps .chip.speed_start,.egps .chip.speed_end{border-color:var(--sand);color:#F6D99B}' +
/* tabs + drawer */
'.egps .tabs{display:flex;flex:0 0 calc(34px*var(--s));border-top:1px solid var(--line)}' +
'.egps .tabs button{flex:1;min-width:0;border:0;border-radius:0;background:transparent;color:var(--mute);padding:calc(7px*var(--s)) calc(2px*var(--s));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
'.egps .tabs .sm{display:none}.egps.narrow .tabs .sm{display:inline}.egps.narrow .tabs .lg{display:none}.egps.narrow .tabs button{font-size:calc(11.5px*var(--s))}' +
'.egps .tabs button.sel{color:var(--ink);box-shadow:inset 0 calc(2px*var(--s)) 0 var(--cyan);background:rgba(39,217,255,.06)}' +
'.egps .drawer{position:absolute;left:0;right:0;top:0;bottom:calc(34px*var(--s));background:#0F1524;padding:calc(10px*var(--s)) calc(12px*var(--s));overflow:auto;z-index:3}' +
'.egps .list{margin-top:calc(8px*var(--s));display:flex;flex-direction:column;gap:calc(2px*var(--s))}' +
'.egps .item{text-align:left;background:transparent;border:0;border-radius:calc(6px*var(--s));padding:calc(6px*var(--s)) calc(8px*var(--s));width:100%}' +
'.egps .item:hover{background:#1E2A42}.egps .item b{display:block;font-weight:600}.egps .item small{color:var(--mute)}' +
'.egps .warnText{color:#FFB3AA}' +
'.egps .note{color:var(--mute);font-size:calc(12px*var(--s));margin-top:calc(8px*var(--s))}.egps .err{color:#FFB3AA;font-size:calc(12px*var(--s));margin-top:calc(6px*var(--s))}' +
'.egps .set{display:flex;justify-content:space-between;align-items:center;gap:calc(10px*var(--s));margin:calc(10px*var(--s)) 0}' +
'.egps .codein{flex:1;min-width:0;width:auto;font-family:Consolas,monospace;letter-spacing:.03em}.egps b.code{font-family:Consolas,monospace;font-weight:600;letter-spacing:.03em;user-select:text}' +
'.egps .seg{display:inline-flex;border:1px solid #33425F;border-radius:calc(6px*var(--s));overflow:hidden;flex:0 0 auto}' +
'.egps .seg button{border:0;border-radius:0;background:#0F1524;color:var(--mute);padding:calc(4px*var(--s)) calc(9px*var(--s))}' +
'.egps .seg button+button{border-left:1px solid #33425F}.egps .seg button.on{background:var(--cyan);color:#06222C}' +
'.egps .set.stack{flex-wrap:wrap}.egps .set.stack .seg{flex:1 1 100%;display:flex}' +   /* (the label above, the choices the row's width: Track terrain's six) */
'.egps .set.stack .seg button{flex:1 1 0;padding-left:calc(2px*var(--s));padding-right:calc(2px*var(--s));white-space:nowrap}' +
'.egps .pick{width:100%;display:flex;justify-content:space-between;align-items:center;gap:calc(8px*var(--s));text-align:left;background:#0F1524;padding:calc(6px*var(--s)) calc(10px*var(--s))}' +
'.egps .pick span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.egps .pick.open{border-color:var(--cyan)}' +
'.egps .caret{flex:0 0 auto;width:0;height:0;border-left:calc(5px*var(--s)) solid transparent;border-right:calc(5px*var(--s)) solid transparent;border-top:calc(6px*var(--s)) solid var(--mute)}' +
'.egps .pick.open .caret{border-top:0;border-bottom:calc(6px*var(--s)) solid var(--cyan)}' +
'.egps .menu{margin-top:calc(4px*var(--s));border:1px solid #33425F;border-radius:calc(6px*var(--s));background:#0F1524;padding:calc(3px*var(--s))}' +
'.egps .item.cur{box-shadow:inset calc(3px*var(--s)) 0 0 var(--cyan)}' +
'.egps-off .call,.egps-off .strip{opacity:.6}' +
'.egps .strip.edit{border-top:1px solid #FF6AD5}.egps button.rec{background:#FF4D3D;border-color:#FF4D3D;color:#fff}' +
'.egps button[disabled]{opacity:.45;cursor:default}' +
'.egps .osm{position:absolute;right:calc(44px*var(--s));bottom:calc(6px*var(--s));font-size:calc(10px*var(--s));color:rgba(201,209,222,.55);pointer-events:none}' +
'.egps .mapMode{position:absolute;left:calc(8px*var(--s));top:calc(8px*var(--s));background:rgba(10,14,24,.8);border-left:calc(3px*var(--s)) solid #FF6AD5;padding:calc(3px*var(--s)) calc(8px*var(--s));border-radius:calc(4px*var(--s));font-size:calc(12px*var(--s));pointer-events:none}' +
'.egps .centre{position:absolute;right:calc(8px*var(--s));top:calc(8px*var(--s))}' +
'.egps .ovbtn{position:absolute;right:calc(8px*var(--s));top:calc(8px*var(--s));padding:calc(2px*var(--s)) calc(8px*var(--s));font-size:calc(12px*var(--s))}' +
'.egps canvas.plan{cursor:crosshair}' +
'.egps canvas.ov{cursor:grab}.egps canvas.ov.dragging{cursor:grabbing}' +
'.egps .ovbar{position:absolute;left:calc(8px*var(--s));top:calc(8px*var(--s));display:flex;gap:calc(4px*var(--s))}' +
'.egps .ovbar button{padding:calc(2px*var(--s)) calc(7px*var(--s));font-size:calc(11px*var(--s))}' +
'.egps .north{position:absolute;left:calc(10px*var(--s));top:calc(38px*var(--s));width:calc(22px*var(--s));height:calc(22px*var(--s));border-radius:50%;background:rgba(10,14,24,.8);display:flex;align-items:center;justify-content:center;font-size:calc(11px*var(--s));font-weight:700;color:#FF6A5C;cursor:pointer}' +
'.egps .north span{display:inline-block}' +
'.egps.ovbig .lower{display:none}' +
/* (Big on the map around the car: the turn notes and the course's top line and progress bar stay, the rest goes) */
'.egps.mapbig .lower .strip>.sub,.egps.mapbig .lower .strip>.ahead,.egps.mapbig .lower .strip>.row:not(:first-child),.egps.mapbig .lower .where{display:none}' +
/* (Big with no course: the street and the route's line stay, the rest under the map goes) */
'.egps.mapbig.nocourse .lower .where{display:block}.egps.mapbig.nocourse .lower .where>.row{display:none}' +
/* hidden (the Hide button, or the bindable key): only a small pill to bring it back, the game seen through the rest */
'.egps .pill{display:none}' +
'.egps.hid{background:transparent;border-color:transparent;pointer-events:none}' +
'.egps.hid>*:not(.pill):not(style){display:none!important}' +
'.egps.hid .pill{display:inline-flex;align-items:center;gap:calc(8px*var(--s));position:absolute;top:0;right:0;pointer-events:auto;' +
'  background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:calc(6px*var(--s)) calc(14px*var(--s));' +
'  font-weight:700;letter-spacing:.08em;font-size:calc(12px*var(--s));color:var(--ink);text-transform:uppercase;white-space:nowrap}' +
'.egps.hid .pill:hover{background:#2B3B5A}' +
'.egps .pill i{width:calc(9px*var(--s));height:calc(9px*var(--s));border-radius:2px;background:var(--sand);display:inline-block}' +
'.egps .tabs button.hideBtn{flex:0 0 calc(34px*var(--s));color:var(--mute);font-size:calc(15px*var(--s));line-height:1}' +
'.egps .mapbtns{position:absolute;right:calc(8px*var(--s));top:calc(8px*var(--s));display:flex;gap:calc(4px*var(--s))}' +
'.egps .mapbtns button{padding:calc(2px*var(--s)) calc(8px*var(--s));font-size:calc(12px*var(--s))}' +
'</style>' +
'<button class="pill" ng-click="toggleHidden()" title="Show the Offroad Companion (or the key you bind: Options, Controls, Offroad Companion: hide or show the app)"><i></i>Offroad Companion</button>' +

/* -- roadbook box: corner call on a course, else the next maneuver, else idle -- */
'<div class="call" ng-class="{zone: call.zone, warn: call.warn}">' +
'  <div class="tulip" ng-bind-html="call.svg"></div>' +
'  <div class="callTxt">' +
'    <div ng-if="call.dist" class="dist num">{{ call.dist }}</div>' +
'    <div ng-if="call.what" class="what">{{ call.what }}</div>' +
'    <div ng-if="call.then" class="then"><i ng-bind-html="call.thenSvg"></i><span>{{ call.then }}</span></div>' +
'    <div ng-if="call.idle" class="idle">{{ call.idle }}</div>' +
'  </div>' +
'</div>' +
'<div class="rest">' +

/* -- map -- */
'<div class="mapWrap">' +
'  <canvas></canvas>' +
'  <div class="banner" ng-if="d.course.wrongWay">{{ d.lang === \'es\' ? \'Sentido contrario\' : \'Wrong way\' }}</div>' +
'  <div class="toasts" ng-if="!d.course.wrongWay"><div class="toast" ng-repeat="t in toasts" ng-class="t.level">{{ t.text }}</div></div>' +
'  <div class="limit num" ng-if="d.course.zone.limit">{{ limitNum(d.course.zone.limit) }}</div>' +
'  <div class="spd" ng-if="d.car" ng-class="{fast: d.course.zone.speeding}"><b class="num">{{ d.car.speed }}</b><small>{{ d.units === \'imperial\' ? \'mph\' : \'km/h\' }}</small></div>' +
'  <div class="zoom" ng-if="!d.map.ov"><div class="zlab num" title="Zoom: the map reaches about this far ahead of the car; the ring around the car is this wide (its radius)"><b>{{ zoomText() }}</b><span>&#9675; {{ ringText() }}</span></div><button ng-click="zoom(0.6)" title="Zoom in">+</button><button ng-click="zoom(1.6)" title="Zoom out">&minus;</button></div>' +
'  <div class="zoom ovctl" ng-if="d.map.ov">' +
'    <div class="zlab num" title="Zoom (Fit = 1)"><b>&times;{{ ovZoomText() }}</b></div>' +
'    <button ng-click="ovZoom(1.6)" title="Zoom in (or the mouse wheel; double-click a place)">+</button>' +
'    <button ng-click="ovZoom(1 / 1.6)" title="Zoom out">&minus;</button>' +
'    <button ng-click="ovTurn(-15)" title="Turn the map left (or drag with the right mouse button)">&#x27F2;</button>' +
'    <button ng-click="ovTurn(15)" title="Turn the map right">&#x27F3;</button>' +
'  </div>' +
'  <div class="ovbar" ng-if="d.map.ov">' +
'    <button ng-click="ovFit()" ng-class="{on: ovFitted()}" title="The whole course, north up">Fit</button>' +
'    <button ng-click="ovCar()" ng-class="{on: ovv.follow}" title="Keep the car in the middle">Car</button>' +
'    <button ng-click="ovHeading()" ng-class="{on: ovv.headingUp}" title="Turn the map with the car (heading up)">&#x2191;</button>' +
'    <button ng-click="ovBig()" ng-class="{on: ovv.big}" title="A bigger map: the strips below hidden while it is open">Big</button>' +
'  </div>' +
'  <div class="north" ng-if="d.map.ov && ovv.eff" ng-click="ovNorth()" title="North (click: north up)"><span ng-style="{transform: \'rotate(\' + (-ovv.eff) + \'deg)\'}">N</span></div>' +
'  <div class="mapbtns" ng-if="d.editor.mode !== \'plan\' && !tab">' +
'    <button ng-if="!d.map.ov" ng-click="mapBig()" ng-class="{on: mapv.big}" title="A bigger map: the turn notes stay, and the course\'s race mile, time and progress (or, with no course, the street and the route), the rest below is hidden">Big</button>' +
'    <button ng-if="d.course" ng-class="{on: d.map.ov}" ng-click="overview()" title="{{ d.map.ov ? \'Back to the map around the car\' : \'The whole course\' }}">{{ d.map.ov ? \'Back\' : \'Course\' }}</button></div>' +
'  <div class="osm" ng-if="hasStreets">&copy; OpenStreetMap</div>' +
'  <div class="mapMode" ng-if="d.editor.mode === \'plan\' && !tab">Tap to add a point &middot; drag to move the map</div>' +
'  <button class="centre" ng-if="d.editor.mode === \'plan\' && panned() && !tab" ng-click="centre()">Centre</button>' +

'</div>' +

'<div class="lower">' +
/* -- BeamNG.Earth's game mod older than its server: orange dirt roads (main.lua earthModStale) -- */
'<div class="strip stale" ng-if="d.earthStale" title="BeamNG.Earth {{ d.earthStale.server }} draws dirt roads with materials its own game mod brings since 1.8; an older copy of that mod has none, so the game shows its orange missing-texture">' +
'  <div class="err">Orange dirt roads: BeamNG.Earth\'s game mod is older than its server ({{ d.earthStale.server }}).' +
'    <span ng-if="d.earthStale.mp"> On this BeamMP server everyone gets the server\'s copy: its owner replaces Resources/Client/beamng_earth.zip with BeamNG.Earth {{ d.earthStale.server }}\'s (the Offroad Companion BeamMP server zip has it), then everyone rejoins.</span>' +
'    <span ng-if="!d.earthStale.mp"> Remove the old beamng_earth zip or folder from your mods folder (keep BeamNG.Earth {{ d.earthStale.server }}\'s), or start the Offroad Companion .exe again (it installs the right one), then restart the game.</span>' +
'  </div>' +
'</div>' +
/* -- track editor -- */
'<div class="strip edit" ng-if="tab === \'make\' || (d.editor && d.editor.mode !== \'off\')">' +
'  <div class="row" style="margin-top:0"><b class="grow">Make a track</b><span class="num">{{ d.editor.n || 0 }} points &middot; {{ d.editor.length }}<span ng-if="d.editor.checkpoints"> &middot; {{ d.editor.checkpoints }} CP</span></span></div>' +
'  <div class="row">' +
'    <button ng-class="{rec: d.editor.mode === \'record\'}" ng-click="ed(d.editor.mode === \'record\' ? \'stop\' : \'record\')" title="A point every 8 m as you drive">{{ d.editor.mode === \'record\' ? \'Stop recording\' : \'Record drive\' }}</button>' +
'    <button ng-class="{on: d.editor.mode === \'plan\'}" ng-click="ed(d.editor.mode === \'plan\' ? \'stop\' : \'plan\')" title="Tap the map to add points">Tap on map</button>' +
'    <button ng-click="ed(\'add_here\')" title="A point where the car is">Add here</button>' +
'    <button ng-click="ed(\'checkpoint\')" title="A checkpoint where the car is">Checkpoint</button>' +
'    <button class="quiet" ng-click="ed(\'undo\')" ng-disabled="!(d.editor.n || d.editor.checkpoints)">Undo</button>' +
'    <button class="quiet" ng-click="clearDraft()" ng-disabled="!(d.editor.n || d.editor.checkpoints)">{{ ui.sure ? \'Clear all?\' : \'Clear\' }}</button>' +
'  </div>' +
'  <div class="row"><input class="grow" type="text" ng-model="ui.trackName" ng-focus="typing(true)" ng-blur="typing(false)" placeholder="Track name">' +
'    <button ng-click="saveTrack()" ng-disabled="(d.editor.n || 0) < 2 || d.editor.saving" title="Saved as GPX in the tracks folder, then loaded as the course">{{ d.editor.saving ? \'Saving…\' : \'Save and load\' }}</button></div>' +
'  <div class="note" ng-class="{err: d.editor.error}">{{ editNote() }}</div>' +
'</div>' +

/* -- course strip -- */
'<div class="strip" ng-if="d.course">' +
'  <div class="row" style="margin-top:0"><b class="grow" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ d.course.name }}</b>' +
'    <span class="num" ng-if="!d.course.waypoints">RM {{ d.course.rm }}</span>' +
'    <span class="num" ng-if="d.course.timing.current">{{ d.course.timing.current }}</span>' +
'    <span class="num" ng-if="d.course.timing.elapsed">{{ d.course.timing.elapsed }}</span></div>' +
'  <div class="bar" ng-if="!d.course.waypoints"><i ng-style="{width: (100 * (d.course.progress || 0)) + \'%\'}"></i></div>' +
'  <div class="sub">' +
'    <span ng-if="!d.course.waypoints" class="num">{{ d.course.done }} done, {{ d.course.left }} to go</span>' +
'    <span ng-if="d.course.waypoints && d.course.target" class="num">Waypoint {{ d.course.target.index }} of {{ d.course.total }}, {{ d.course.remaining }} left</span>' +
'    <span ng-if="d.course.vcp.hit || d.course.vcp.miss">VCPs {{ d.course.vcp.hit }} hit<span ng-if="d.course.vcp.miss">, {{ d.course.vcp.miss }} missed</span></span>' +
'    <span ng-if="d.course.timing.best">Best {{ d.course.timing.best }}</span>' +
'    <span ng-if="d.course.approximate" title="This file has no course line: drawn straight between race-mile markers">Rough line</span>' +
'    <span ng-if="trackLine()" ng-class="{warnText: trackWarn()}">{{ trackLine() }}</span>' +
'    <span ng-if="d.paint.markers.failed && d.settings.markers !== false && d.settings.markers !== \'off\'" class="warnText">Course markers: {{ d.paint.markers.failed }}</span>' +
'  </div>' +
'  <div class="ahead"><span class="chip num" ng-repeat="a in d.course.ahead" ng-class="a.kind">{{ kindLabel(a) }} {{ a.dist }}</span></div>' +
'  <div class="row">' +
'    <button ng-click="track(\'route_start\')" title="Road directions to the start">To start</button>' +
'    <button ng-click="track(\'teleport_start\')">Teleport to start</button>' +
'    <button ng-if="d.course.off || d.course.waypoints" ng-click="track(\'route_course\')">{{ d.course.waypoints ? \'Directions to waypoint\' : \'Back to course\' }}</button>' +
'    <button ng-if="d.course.waypoints" class="quiet" ng-click="track(\'skip\')">Skip</button>' +
'    <span class="grow"></span>' +
'    <button class="quiet" ng-click="track(\'restart\')">Restart</button>' +
'    <button class="quiet" ng-click="track(\'unload\')">Close</button>' +
'  </div>' +
'</div>' +

/* -- where am I / route -- */
'<div class="where">' +
'  <div class="street">{{ (d.car && d.car.street) || (d.nav && d.nav.road) || (d.earth ? \'Off road\' : \'Load the BeamNG.Earth level to start\') }}</div>' +
'  <div class="sub"><span>{{ placeLine() }}</span>' +
'    <span ng-if="d.nav && d.dest" class="num">{{ d.dest.name || \'Destination\' }}: {{ d.nav.remaining }}<span ng-if="d.nav.eta">, {{ d.nav.eta }}</span></span>' +
'    <span ng-if="d.planning">Planning route…</span><span ng-if="d.trackLoading">Loading course…<span ng-if="d.trackSlow"> (its source is slow right now, still trying)</span></span>' +
'    <span ng-if="d.trackError" class="err" style="margin:0">{{ d.trackError }}</span>' +
'    <span ng-if="d.dest && d.paint.route.on && d.paint.route.clearing && d.paint.painter" title="Buildings, walls and low overpasses on the route are left out as the world streams in">Route cleared</span></div>' +
'  <div class="row" ng-if="d.dest"><button ng-class="{on: d.autodrive}" ng-click="autodrive()" title="The car drives itself along the road route">Autodrive</button>' +
'    <button class="quiet" ng-click="stop()">End route</button></div>' +
'</div>' +

'</div>' +

'<div class="tabs">' +
'  <button ng-class="{sel: tab===\'search\'}" ng-click="setTab(\'search\')">Search</button>' +
'  <button ng-class="{sel: tab===\'courses\'}" ng-click="setTab(\'courses\')">Courses</button>' +
'  <button ng-class="{sel: tab===\'make\'}" ng-click="setTab(\'make\')" title="Make track"><span class="lg">Make track</span><span class="sm">Track</span></button>' +
'  <button ng-class="{sel: tab===\'settings\'}" ng-click="setTab(\'settings\')">Settings</button>' +
'  <button class="hideBtn" ng-click="toggleHidden()" title="Hide the app: a small button stays to bring it back (or bind a key: Options, Controls, Offroad Companion: hide or show the app)">&#x25BE;</button>' +
'</div>' +

/* -- drawers -- */
'<div class="drawer" ng-if="tab === \'search\'">' +
'    <div class="row" style="margin-top:0"><input class="grow" type="text" ng-model="ui.q" ng-change="searchChanged()" ng-keydown="searchKey($event)" ng-focus="typing(true)" ng-blur="typing(false)" placeholder="Search an address, a place or lat, lon">' +
'      <button ng-click="searchNow()" ng-disabled="!ui.q" title="Search now (Enter); also asks OpenStreetMap\'s Nominatim when Photon is slow">Search</button></div>' +
'    <div class="note" ng-if="ui.searching" style="margin-top:6px">Searching…</div>' +
'    <div class="err" ng-if="ui.searchError && !ui.searching">{{ ui.searchError }}</div>' +
'    <div class="list"><button class="item" ng-repeat="r in ui.results" ng-click="go(r)"><b>{{ r.name }}</b><small>{{ r.detail }}</small></button></div>' +
'    <div class="note" ng-if="!ui.results.length && !ui.q">Type a place or an address (results come as you type), press Enter to search harder, or type coordinates like 32.83, -117.19. Pick a result to get directions.</div>' +
'    <div class="note" ng-if="!ui.results.length && ui.q && ui.searched === ui.q && !ui.searching && !ui.searchError">Nothing found. Try adding the town or the country, then press Enter.</div>' +
'    <div class="note" ng-if="ui.results.length && ui.searchSource">Search: {{ ui.searchSource === \'nominatim\' ? \'Nominatim\' : (ui.searchSource === \'photon\' ? \'Photon by komoot\' : \'BeamNG.Earth\') }}, data &copy; OpenStreetMap contributors</div>' +
'  </div>' +

'<div class="drawer" ng-if="tab === \'courses\'">' +
'    <button class="pick" ng-class="{open: ui.pickOpen}" ng-click="ui.pickOpen = !ui.pickOpen" title="Choose where courses come from">' +
'      <span>{{ sourceTitle() }}</span><i class="caret"></i></button>' +
'    <div class="menu" ng-if="ui.pickOpen"><button class="item" ng-repeat="s in d.sources" ng-class="{cur: s.id === ui.source}" ng-click="pickSource(s.id)">' +
'      <b>{{ s.title }}</b><small>{{ s.hint }}</small></button></div>' +
'    <div ng-if="!ui.pickOpen">' +
'    <div class="row" ng-if="ui.source && ui.source !== \'url\' && ui.source !== \'bajatracker\'">' +
'      <input class="grow" type="text" ng-model="ui.filter" ng-focus="typing(true)" ng-blur="typing(false)" placeholder="Filter by name">' +
'      <span class="seg" ng-if="ui.source === \'osm\'" title="Search radius around the car">' +
'        <button ng-repeat="r in radii" ng-class="{on: ui.radius == r}" ng-click="setRadius(r)">{{ r / 1000 }}</button></span>' +
'      <button class="quiet" ng-click="listSource()" title="Refresh the list">Refresh</button>' +
'    </div>' +
'    <div class="row" ng-if="ui.source === \'url\' || ui.source === \'bajatracker\'">' +
'      <input class="grow" type="text" ng-model="ui.url" ng-focus="typing(true)" ng-blur="typing(false)" placeholder="https://… .gpx / .kml / .kmz">' +
'      <button ng-click="loadUrl()">Load course</button>' +
'    </div>' +
'    <div class="note" ng-if="ui.listing">Looking for courses…<span ng-if="ui.listSlow"> The source is slow right now (OpenStreetMap\'s servers are often busy): still trying, up to a few minutes.</span></div>' +
'    <div class="err" ng-if="ui.listError">{{ ui.listError }}</div>' +
'    <div class="list"><button class="item" ng-repeat="it in ui.items | filter:{name: ui.filter}" ng-click="load(it)"><b>{{ it.name }}</b><small>{{ it.detail }}</small></button></div>' +
'    <div class="note" ng-if="ui.note">{{ ui.note }}</div>' +
'    </div>' +
'    <div class="note" ng-if="!d.sources.length">Start the Offroad Companion (OffroadCompanion/run_companion_only) to browse courses.</div>' +
'  </div>' +

'<div class="drawer" ng-if="tab === \'settings\'">' +
'    <div class="set"><span title="Where the turn notes box (the arrow, the distance, the call) sits: over the map, under it, or beside it with the arrow above the text">Turn notes</span><span class="seg">' +
'      <button ng-class="{on: ui.notes === \'top\'}" ng-click="choose(\'notes\', \'top\')">Top</button>' +
'      <button ng-class="{on: ui.notes === \'bottom\'}" ng-click="choose(\'notes\', \'bottom\')">Bottom</button>' +
'      <button ng-class="{on: ui.notes === \'left\'}" ng-click="choose(\'notes\', \'left\')">Left</button>' +
'      <button ng-class="{on: ui.notes === \'right\'}" ng-click="choose(\'notes\', \'right\')">Right</button></span></div>' +
'    <div class="set"><span>Language</span><span class="seg">' +
'      <button ng-class="{on: ui.lang === \'en\'}" ng-click="choose(\'lang\', \'en\')">English</button>' +
'      <button ng-class="{on: ui.lang === \'es\'}" ng-click="choose(\'lang\', \'es\')">Español</button></span></div>' +
'    <div class="set"><span>Units</span><span class="seg">' +
'      <button ng-class="{on: ui.units === \'auto\'}" ng-click="choose(\'units\', \'auto\')" title="Follow the game setting">Game</button>' +
'      <button ng-class="{on: ui.units === \'metric\'}" ng-click="choose(\'units\', \'metric\')">km</button>' +
'      <button ng-class="{on: ui.units === \'imperial\'}" ng-click="choose(\'units\', \'imperial\')">mi</button></span></div>' +
'    <div class="set"><span>Course line on the ground</span><span class="seg">' +
'      <button ng-class="{on: ui.ribbon === \'on\'}" ng-click="choose(\'ribbon\', \'on\')">Shown</button>' +
'      <button ng-class="{on: ui.ribbon === \'off\'}" ng-click="choose(\'ribbon\', \'off\')">Hidden</button></span></div>' +
'    <div class="set"><span>Road directions between course waypoints</span><span class="seg">' +
'      <button ng-class="{on: ui.autoRoute === \'on\'}" ng-click="choose(\'autoRoute\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.autoRoute === \'off\'}" ng-click="choose(\'autoRoute\', \'off\')">Off</button></span></div>' +
'    <div class="set"><span>Dirt track along the course</span><span class="seg">' +
'      <button ng-class="{on: ui.paint === \'on\'}" ng-click="choose(\'paint\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.paint === \'off\'}" ng-click="choose(\'paint\', \'off\')">Off</button></span></div>' +
'    <div class="set" ng-if="ui.paint === \'on\'"><span title="Width follows the room the terrain gives; this scales it">Track size</span><span class="seg">' +
'      <button ng-class="{on: ui.paintSize == 0.75}" ng-click="chooseSize(0.75)">Narrower</button>' +
'      <button ng-class="{on: ui.paintSize == 1}" ng-click="chooseSize(1)">Auto</button>' +
'      <button ng-class="{on: ui.paintSize == 1.35}" ng-click="chooseSize(1.35)">Wider</button></span></div>' +
'    <div class="set" ng-if="ui.paint === \'on\'"><span title="Two darker wheel ruts along the dirt track, so it shows on ground of its own colour (light desert sand)">Wheel ruts on the dirt track</span><span class="seg">' +
'      <button ng-class="{on: ui.ruts === \'auto\'}" ng-click="choose(\'ruts\', \'auto\')" title="Only where the track blends into the ground (light desert sand)">Auto</button>' +
'      <button ng-class="{on: ui.ruts === \'on\'}" ng-click="choose(\'ruts\', \'on\')" title="All along the dirt track">Always</button>' +
'      <button ng-class="{on: ui.ruts === \'off\'}" ng-click="choose(\'ruts\', \'off\')">Off</button></span></div>' +
'    <div class="set stack" ng-if="ui.paint === \'on\'"><span title="Whoops, washes, kickers, sand berms on the outside of turns, broken ground and rock ledges along the course on dirt (never on asphalt; dry and salt lakes stay smooth), with boulders beside it in canyons; sand traps in the washes, rock sections in the canyons and on rocky hillsides, gravel on the alluvial fans, only where the place has them. The same on every computer for the same course and place">Track terrain</span><span class="seg">' +
'      <button ng-class="{on: ui.rough === \'auto\'}" ng-click="choose(\'rough\', \'auto\')" title="Baja: changes along the course: fast smooth stretches, mild, rough and very rough sections, extra rough with a ditch, a kicker or a rock garden at the DANGER markers (in a canyon often a rock crawl), and boulder fields here and there. Picked from the place, so the same for everyone. Other dirt roads lean to one side only rarely">Baja</button>' +
'      <button ng-class="{on: ui.rough === \'default\'}" ng-click="choose(\'rough\', \'default\')" title="BeamNG.Earth\'s own: the track worn like any dirt track (potholes, broken patches, deep pits and leans, BeamNG.Earth 1.8.2 and newer)">Default</button>' +
'      <button ng-class="{on: ui.rough === \'mild\'}" ng-click="choose(\'rough\', \'mild\')" title="The same roughness all along the course. Other dirt roads lean to one side only rarely">Mild</button>' +
'      <button ng-class="{on: ui.rough === \'on\'}" ng-click="choose(\'rough\', \'on\')" title="The same roughness all along the course. Other dirt roads lean to one side only rarely">Rough</button>' +
'      <button ng-class="{on: ui.rough === \'extra\'}" ng-click="choose(\'rough\', \'extra\')" title="The same roughness all along the course. Other dirt roads lean to one side only rarely">Extra</button>' +
'      <button ng-class="{on: ui.rough === \'off\'}" ng-click="choose(\'rough\', \'off\')" title="As the elevation data has it (graded smooth), and every dirt road without BeamNG.Earth 1.8.2\'s potholes and leans, as before 1.8.2">Flat</button></span></div>' +
'    <div class="note" ng-if="ui.paint === \'on\'">{{ paintNote() }}</div>' +
'    <div class="set" ng-if="d.paint.seal"><span title="The name of exactly this ground: the course, its track settings and the terrain version. The same code on another computer is the same ground, bump for bump. Copy it to send to friends: pasted here with the same course loaded, it sets their track settings to yours">Ground code <b class="code">{{ d.paint.code || d.paint.seal }}</b>{{ d.paint.replayGround ? \' (as the replay was recorded)\' : \'\' }}</span><span class="seg">' +
'      <button ng-click="copyCode()" ng-disabled="!d.paint.code" title="To the clipboard, to send to your friends">Copy</button></span></div>' +
'    <div class="row" ng-if="d.course"><input class="codein" type="text" ng-model="ui.pasteCode" placeholder="Paste a friend\'s ground code" ng-focus="typing(true)" ng-blur="typing(false)" ng-keyup="$event.keyCode === 13 && pasteCode()">' +
'      <button ng-click="pasteCode()" ng-disabled="!ui.pasteCode || d.paint.codeBusy" title="Load the same course first: this sets your track settings to the ones that made that ground">Use</button></div>' +
'    <div class="note" ng-if="d.paint.codeNote" ng-class="{err: d.paint.codeErr}">{{ d.paint.codeNote }}</div>' +
'    <div class="set"><span title="After rain (the real rain of the last days where you are, or the game\'s own rain falling): the ground grips less, more the wetter it is, and the track\'s closed dips hold water when it is soaked. The same for everyone near at the same time">Wet ground after rain</span><span class="seg">' +
'      <button ng-class="{on: ui.wetGround === \'on\'}" ng-click="choose(\'wetGround\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.wetGround === \'off\'}" ng-click="choose(\'wetGround\', \'off\')">Off</button></span></div>' +
'    <div class="note" ng-if="ui.wetGround === \'on\' && d.paint.wet">{{ wetNote() }}</div>' +
'    <div class="set"><span title="Signs on stakes as desert races are marked: VCP boards, a STOP sign at checkpoints, START / FINISH banners, a painted stake about every 8 km. Full: also orange turn arrows, DANGER AHEAD boards and speed zone signs">Course markers</span><span class="seg">' +
'      <button ng-class="{on: ui.markers === \'checkpoints\'}" ng-click="choose(\'markers\', \'checkpoints\')" title="VCPs, checkpoints, start / finish, stakes far apart">Checkpoints</button>' +
'      <button ng-class="{on: ui.markers === \'full\'}" ng-click="choose(\'markers\', \'full\')" title="Also turn arrows, danger and speed zone signs">Full</button>' +
'      <button ng-class="{on: ui.markers === \'off\'}" ng-click="choose(\'markers\', \'off\')">Off</button></span></div>' +
'    <div class="set"><span title="People watching where they gather at desert races: crowds and canopies at the start and finish, checkpoint crews, fans at the jumps, danger spots, paved road crossings and hairpins. They stand back from the track, turn to watch you go by, and never get in the way (nothing collides). The same crowds for everyone on the same course">Spectators</span><span class="seg">' +
'      <button ng-class="{on: ui.spectators === \'some\'}" ng-click="choose(\'spectators\', \'some\')">Some</button>' +
'      <button ng-class="{on: ui.spectators === \'lots\'}" ng-click="choose(\'spectators\', \'lots\')" title="The course lined like a Baja race: people packed behind a fence, canopies and trucks behind them; bigger the nearer a town">Lots</button>' +
'      <button ng-class="{on: ui.spectators === \'off\'}" ng-click="choose(\'spectators\', \'off\')">Off</button></span></div>' +
'    <div class="set" ng-if="ui.spectators !== \'off\'"><span title="After sunset (the game\'s time of day, where you are): campfires behind the crowds, lanterns under the canopies, light towers at the start, finish and checkpoints. The nearest ones light the ground">Night lights</span><span class="seg">' +
'      <button ng-class="{on: ui.nightLights === \'on\'}" ng-click="choose(\'nightLights\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.nightLights === \'bright\'}" ng-click="choose(\'nightLights\', \'bright\')" title="More light from each">Bright</button>' +
'      <button ng-class="{on: ui.nightLights === \'off\'}" ng-click="choose(\'nightLights\', \'off\')">Off</button></span></div>' +
'    <div class="set" ng-if="ui.spectators !== \'off\'"><span title="The crowds near you cheer and whistle, a loop from where each stands: louder as you come near, fading as you leave (bigger crowds louder)">Crowd sound</span><span class="seg">' +
'      <button ng-class="{on: ui.crowdSound === \'on\'}" ng-click="choose(\'crowdSound\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.crowdSound === \'off\'}" ng-click="choose(\'crowdSound\', \'off\')">Off</button></span></div>' +
'    <div class="note" ng-if="ui.spectators !== \'off\' && d.paint.crowds">{{ crowdNote() }}</div>' +
'    <div class="row" ng-if="ui.spectators !== \'off\' && ui.crowdSound === \'on\'"><button class="quiet" ng-click="crowdTest()" title="A crowd\'s sound 25 m ahead of the car for a few seconds">Test crowd sound</button></div>' +
'    <div class="note" ng-if="ui.markers !== \'off\' && d.course" ng-class="{err: d.paint.markers.failed}">{{ markerNote() }}</div>' +
'    <div class="row" ng-if="ui.markers !== \'off\'"><button class="quiet" ng-click="markerTest()" title="Two VCP signs 12 m ahead of the car for a minute, facing you, one of each model file">Test markers</button></div>' +
'    <div class="set"><span title="Watching a replay: BeamNG.Earth\'s world moved to where the recording was, the ground loaded under the car before it plays on. Works for replays recorded with this on">Replays in BeamNG.Earth</span><span class="seg">' +
'      <button ng-class="{on: ui.replays === \'on\'}" ng-click="choose(\'replays\', \'on\')">Follow the recording</button>' +
'      <button ng-class="{on: ui.replays === \'off\'}" ng-click="choose(\'replays\', \'off\')">Off</button></span></div>' +
'    <div class="note" ng-if="ui.replays === \'on\' && d.paint.replay && d.paint.replay.mode !== \'idle\'">{{ replayNote() }}</div>' +
'    <div class="note" ng-if="d.paint.markers.test">Test, 12 m ahead (left: .cdae, right: .dae): <span ng-repeat="t in d.paint.markers.test.items">{{ testLine(t) }}{{ $last ? \'\' : \'; \' }}</span>. Materials: {{ d.paint.markers.test.materials }} of 15. Both boards should face you.</div>' +
'    <div class="row" ng-if="ui.paint === \'on\' && d.paint.painting && d.paint.mode === \'server\'"><button class="quiet" ng-click="track(\'refresh_roads\')" title="Send the roads around the car again">Repaint roads here</button></div>' +
'    <div class="set"><span title="Buildings on the course, low bridges it crosses and walls along it are left out">Clear the course (buildings, walls)</span><span class="seg">' +
'      <button ng-class="{on: ui.clearCourse === \'on\'}" ng-click="choose(\'clearCourse\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.clearCourse === \'off\'}" ng-click="choose(\'clearCourse\', \'off\')">Off</button></span></div>' +
'    <div class="note" ng-if="ui.clearCourse === \'on\'">{{ clearNote() }}</div>' +
'    <div class="set"><span title="The road route you follow (a search here, BeamNG.Earth\'s search or a marker on its big map): buildings and walls on it and low overpasses over it are left out">Clear the GPS route (buildings, walls)</span><span class="seg">' +
'      <button ng-class="{on: ui.clearRoute === \'on\'}" ng-click="choose(\'clearRoute\', \'on\')">On</button>' +
'      <button ng-class="{on: ui.clearRoute === \'off\'}" ng-click="choose(\'clearRoute\', \'off\')">Off</button></span></div>' +
'    <div class="note" ng-if="ui.clearRoute === \'on\'">{{ routeNote() }}</div>' +
'    <div class="set"><span>Streets and names on the map</span><span class="seg">' +
'      <button ng-class="{on: ui.streets === \'on\'}" ng-click="choose(\'streets\', \'on\')">Shown</button>' +
'      <button ng-class="{on: ui.streets === \'off\'}" ng-click="choose(\'streets\', \'off\')">Hidden</button></span></div>' +
'    <div class="note">Companion: {{ d.link === \'connected\' ? \'connected\' : (d.linkError || \'not running\') }}<span ng-if="d.tracksDir">. Course files folder: {{ d.tracksDir }}</span></div>' +
'    <div class="note" ng-class="{err: buildNote()}">Offroad Companion {{ d.version || \'\' }} (build {{ appBuild }})<span ng-if="buildNote()">: {{ buildNote() }}</span></div>' +
'    <div class="note" ng-if="d.course.attribution">{{ d.course.attribution }}</div>' +
'  </div>' +

'</div>' +
'</div>',
    replace: true,
    link: function (scope, element) {
      var lua = function (code, cb) { if (window.bngApi && bngApi.engineLua) bngApi.engineLua(code, cb) }
      var trust = function (s) { return $sce.trustAsHtml(s) }
      scope.d = { sources: [] }
      scope.tab = null
      scope.toasts = []
      scope.call = { svg: trust(tulip(0)), idle: 'Search for a place or load a course' }
      scope.ui = { q: '', results: [], source: null, items: [], filter: '', radius: '25000', url: '',
                   lang: 'en', units: 'auto', ribbon: 'on', autoRoute: 'on', clearRoute: 'on', streets: 'on',
                   rough: 'auto', notes: 'top', spectators: 'some', nightLights: 'on', crowdSound: 'on', wetGround: 'on',
                   pasteCode: '', trackName: '', sure: false }
      var settingsSynced = false

      scope.radii = [10000, 25000, 75000, 150000]
      scope.sourceTitle = function () {
        var s = (scope.d.sources || []).filter(function (x) { return x.id === scope.ui.source })[0]
        return s ? s.title : 'Choose a course source'
      }
      scope.pickSource = function (id) {
        scope.ui.pickOpen = false
        if (id === scope.ui.source && scope.ui.items.length) return
        scope.ui.source = id
        scope.ui.filter = ''
        scope.listSource()
      }
      scope.setRadius = function (r) { scope.ui.radius = String(r); scope.listSource() }
      // settings: on / off choices go to Lua as booleans
      var BOOL = { ribbon: true, autoRoute: true, paint: true, clearCourse: true, clearRoute: true, streets: true, replays: true, crowdSound: 1, wetGround: 1 }
      scope.copyCode = function () { lua('offroadCompanion_main.uiCopyCode()') }
      scope.pasteCode = function () {
        if (!scope.ui.pasteCode) return
        lua('offroadCompanion_main.uiPasteCode(' + luaStr(scope.ui.pasteCode) + ')')
        scope.ui.pasteCode = ''
      }
      scope.wetNote = function () {
        var w = (scope.d.paint || {}).wet || {}
        if (w.failed) return 'Wet ground: ' + w.failed
        var lvl = { dry: 'Dry', damp: 'Damp', wet: 'Wet', soaked: 'Soaked' }[w.level] || (w.w > 0 ? 'Wet' : 'Dry')
        var s = lvl + ' ground (' + Math.round((w.w || 0) * 100) + ' %)'
        if (w.rainNow) s += ', raining'
        if (w.last24 != null) s += ', ' + w.last24 + ' mm of rain in the last 24 h'
        if (w.puddles) s += ', ' + w.puddles + ' puddle' + (w.puddles === 1 ? '' : 's') + ' near you'
        return s + '.'
      }
      var lastCodeNote = null
      scope.chooseSize = function (v) { scope.ui.paintSize = v; scope.set('paintSize', v) }
      // the course strip's one line: what the dirt track is doing right here
      scope.trackLine = function () {
        var p = scope.d.paint || {}
        if (!scope.d.course || !p.on) return ''
        if (p.outdated) return 'Dirt track: restart OffroadCompanion\\run_companion_only (it is an older version)'
        if (p.mode === 'server') return 'Dirt track: laid by the BeamNG.Earth server'
        if (p.mode === 'wait') return 'Dirt track: waiting for the companion'
        if (p.mode !== 'game') return ''
        var g = p.game || {}
        if (g.errors && g.errors.length) return 'Dirt track: no map data (' + g.errors[0] + ')'
        if (g.hooked === false) return 'Dirt track: waiting for BeamNG.Earth\'s roads'
        if (g.pending) return 'Dirt track: planning ' + g.pending + ' km near you'
        if (g.planned && !g.pieces) return 'Dirt track: none needed near you (the course is on mapped roads)'
        if (g.pieces && !g.tiles) return 'Dirt track: waiting for BeamNG.Earth\'s road tiles'
        if (g.queued) return 'Dirt track: drawing'
        if (g.roads) return 'Dirt track: drawn (' + g.roads + ' pieces on ' + g.tiles + ' tiles)'
        if (g.pieces) return 'Dirt track: planned here, not on these road tiles yet'
        return 'Dirt track: starting'
      }
      scope.trackWarn = function () {
        var p = scope.d.paint || {}, g = p.game || {}
        return !!(p.outdated || (g.errors && g.errors.length) || g.drawErrors)
      }
      scope.paintNote = function () {
        var p = scope.d.paint || {}
        if (p.error) return p.error
        if (p.outdated) return 'The Offroad Companion window is an older version: close it and start OffroadCompanion\\run_companion_only again.'
        if (scope.d.link !== 'connected') return 'Needs the Offroad Companion running.'
        if (!scope.d.course) return 'Load a course: a dirt track is laid where it leaves the roads, wide on open ground, narrow on hillsides and in canyons.'
        if (!p.canPaint) return 'This course has no course line (waypoints only), so there is no track to lay.'
        if (p.mode === 'server') return 'Laid by the BeamNG.Earth server as the world streams in: graded ground, dirt surface. Ground already loaded is regraded at the next world shift. Wheel ruts on Auto: darker wheel tracks only where the track blends into the ground (light sand), judged from BeamNG.Earth\'s satellite imagery. Track terrain: whoops, washes and berms in the ground along the course on dirt, rocks in canyons; a change shows on ground loaded after it.'
        if (p.mode === 'game') {
          var g = p.game || {}
          var s = 'Drawn by the game on BeamNG.Earth\'s road tiles (the .exe can\'t be extended): on the natural ground, not graded. Wheel ruts need BeamNG.Earth\'s server from source (run_offroad_companion).'
          if (g.drawErrors) s += ' Drawing errors: ' + g.drawErrors + (g.lastError ? ' (' + g.lastError + ')' : '') + '.'
          return s
        }
        return 'Starting…'
      }
      scope.clearNote = function () {
        var p = scope.d.paint || {}
        if (p.mode === 'server' || (p.painter && scope.d.course)) return 'Buildings on the course, short bridges it crosses off-road (built as decks with walls) and retaining walls along it are left out as the world streams in.'
        return 'Needs BeamNG.Earth\'s server from source: run OffroadCompanion\\setup_offroad_companion once, then start it with OffroadCompanion\\run_offroad_companion instead of the .exe. The .exe\'s server is sealed, so it builds every building and wall.'
      }

      scope.markerTest = function () { lua('offroadCompanion_main.uiMarkerTest()') }
      scope.crowdTest = function () { lua('offroadCompanion_main.uiCrowdTest()') }
      scope.crowdNote = function () {
        var c = (scope.d.paint || {}).crowds || {}
        var snd = (scope.d.paint || {}).crowdSound || {}
        if (c.failed) return 'Spectators not shown: ' + c.failed + ' (tried again in 30 s).'
        var s = (c.live || 0) + ' spectators and things near you.'
        if (c.lights !== 'off') {
          if (c.sun == null) s += ' Night lights: the time of day is not known.'
          else if (c.night) s += ' Night: ' + (c.lit || 0) + ' lights on near you (sun ' + c.sun + '\u00b0).'
          else s += ' Day (sun ' + c.sun + '\u00b0 up): the lights come on after sunset.'
          if (c.lightError) s += ' Light trouble: ' + c.lightError
        }
        if (snd.on) {
          if (snd.method === '3D') s += ' Crowd sound: ' + snd.playing + ' playing near you, from where they stand.'
          else if (snd.method === '2D') s += ' Crowd sound: ' + snd.playing + ' playing near you (as ordinary sounds: the game would not place them).'
          if (snd.error && !snd.method) s += ' Sound trouble: ' + snd.error
        }
        return s
      }
      scope.testLine = function (t) {
        var f = String(t.shape || '').split('.').pop()
        if (t.exists === false) return f + ' missing from the mod'
        if (!t.made) return f + ' not made (' + (t.error || '?') + ')'
        var h = t.height == null ? 'size unknown' : (t.height >= 1 ? 'loaded, ' + t.height.toFixed(1) + ' m' : 'NOT loaded (' + t.height.toFixed(2) + ' m)')
        return f + ' ' + h + (t.turned === false ? ', not turned' : '') + (t.ground ? '' : ', ground not found')
      }
      scope.markerNote = function () {
        var m = (scope.d.paint || {}).markers || {}
        if (m.failed) return 'Not shown: ' + m.failed + ' (tried again in 30 s).'
        if (m.bad && m.bad.length && !m.shape) return 'Model trouble: ' + m.bad.join('; ')
        var s = (m.planned || 0) + ' signs on this course (' + (m.gates || 0) + ' at VCPs, checkpoints, start / finish' + (m.mode === 'full' ? '; the rest arrows, danger, zones, stakes' : '; the rest stakes ~8 km apart') + '), ' + (m.live || 0) + ' standing near you.'
        var n = m.nearest
        if (n) {
          var kind = { vcp: 'VCP', checkpoint: 'checkpoint', start: 'start', finish: 'finish' }[n.kind] || 'checkpoint'
          s += ' Nearest ' + kind + ' sign ' + n.dist + ' m'
          if (n.live) s += n.dz != null && n.dist < 350 ? ' (up, ' + (Math.abs(n.dz) < 0.3 ? 'on the ground' : n.dz.toFixed(1) + ' m off the ground') + ').' : ' (up).'
          else s += n.dist < 600 ? ' (waiting for the ground there).' : '.'
        }
        if (m.fixed) s += ' ' + m.fixed + ' put back on the ground.'
        return s
      }
      scope.appBuild = EGPS_APP_BUILD
      // a stale copy: the game still runs an older app or Lua (restart it), or an older copy of the mod is installed
      scope.buildNote = function () {
        var d = scope.d || {}
        if (d.build && d.build !== EGPS_APP_BUILD) return 'the game is running two versions of the Offroad Companion app (' + d.build + ' in its Lua). Restart BeamNG.drive; if it stays, an older offroad_companion zip is in your mods folder: remove it'
        if (d.modBuild && d.build && d.modBuild > d.build) return 'the companion has a newer Offroad Companion app (' + d.modBuild + '): restart run_offroad_companion (it installs it), then BeamNG.drive'
        return ''
      }
      scope.replayNote = function () {
        var r = (scope.d.paint || {}).replay || {}
        if (r.mode === 'recording') {
          var t = 'Recording: the world\'s places logged (' + (r.recording || 0) + ')'
          if (r.recSeconds != null) t += ', ' + Math.floor(r.recSeconds / 60) + ' min'
          if (r.recBytes) t += ', about ' + (r.recBytes / 1e9).toFixed(2) + ' GB (split at 1.8 GB: BeamNG cannot play back a replay over 2 GB)'
          if (r.splits) t += '; split ' + r.splits + ' time' + (r.splits > 1 ? 's' : '')
          return t + '.'
        }
        if (r.mode !== 'playback') return ''
        var g = r.terrain ? ' Ground: ' + r.terrain + '.' : ''
        if (r.switching && r.grading) return 'Replay: waiting for the levelled ground (BeamNG.Earth builds it a little after a jump)…' + g
        if (r.switching) return 'Replay: loading the ground where it was recorded…' + g
        if (r.matched) return 'Replay: the world is where it was recorded.' + g
        return 'Replay: ' + (r.note || 'looking for this moment in the logs') + '.'
      }
      scope.routeNote = function () {
        var p = scope.d.paint || {}
        if (p.mode === 'server' || p.painter) {
          return 'Searches here, BeamNG.Earth\'s search and markers on its big map: buildings and walls on the route and overpasses too low to pass under are left out as the world streams in.' +
            (p.route && p.route.error ? ' ' + p.route.error : '')
        }
        return 'Needs BeamNG.Earth\'s server from source started with OffroadCompanion\\run_offroad_companion (the .exe\'s server is sealed).'
      }

      // -- the track editor ---------------------------------------------------------------------------------------
      scope.ed = function (action, a, b) {
        var args = [luaStr(action)]
        if (a != null) args.push(typeof a === 'number' ? luaNum(a) : luaStr(a))
        if (b != null) args.push(luaNum(b))
        lua('offroadCompanion_main.uiEditor(' + args.join(', ') + ')')
        if (action === 'plan' || action === 'stop') { pan.x = 0; pan.y = 0 }
        if (action === 'plan') scope.tab = 'make'
      }
      var sureTimer = null
      scope.clearDraft = function () {
        if (!scope.ui.sure) {
          scope.ui.sure = true
          clearTimeout(sureTimer)
          sureTimer = setTimeout(function () { scope.$evalAsync(function () { scope.ui.sure = false }) }, 3000)
          return
        }
        scope.ui.sure = false
        scope.ed('clear')
      }
      scope.saveTrack = function () {
        scope.ed('save', scope.ui.trackName || '')
        scope.ui.trackName = ''
      }
      scope.editNote = function () {
        var e = scope.d.editor || {}
        if (e.error) return e.error
        if (e.saving) return 'Saving to the tracks folder…'
        if (e.mode === 'record') return 'Recording: drive the line you want. Stop when you are done, then save.'
        if (e.mode === 'plan') return 'Tap the map to add points in order; drag the map to look around, +/− to zoom.'
        if (e.note) return 'Saved: ' + e.note + '. Loaded as the course: cleared of buildings and walls, with its dirt track. Find it later under Courses > My files.'
        return 'Record a drive or tap points on the map, then save. It is saved to the tracks folder and loaded as the course, so blocked spots get cleared and a dirt track laid.'
      }
      var pan = { x: 0, y: 0 }
      // Big on the map around the car (the user, 2026-10-25): kept for next time in this game's browser
      var mapv = scope.mapv = { big: false }
      try { mapv.big = window.localStorage.getItem('offroadCompanion.mapBig') === '1' } catch (e) {}
      scope.mapBigOn = function () {
        var d = scope.d || {}
        return !!(mapv.big && !(d.map && d.map.ov) && !scope.tab && !(d.editor && d.editor.mode && d.editor.mode !== 'off'))
      }
      // Hidden (the user, 2026-11-01): the Hide button or the bindable key (OffroadCompanionToggle) leaves only a pill
      // to bring it back; while hidden the game sends it nothing (uiMounted false), kept for next time
      try { scope.ui.hidden = window.localStorage.getItem('offroadCompanion.hidden') === '1' } catch (e) {}
      scope.toggleHidden = function () {
        scope.ui.hidden = !scope.ui.hidden
        try { window.localStorage.setItem('offroadCompanion.hidden', scope.ui.hidden ? '1' : '0') } catch (e) {}
        if (scope.ui.hidden) { scope.tab = null; hello(false) } else hello(true, true)
        ;(window.requestAnimationFrame || setTimeout)(function () { fit(); safeDraw() })
      }
      scope.$on('OffroadCompanionToggle', function () { scope.$evalAsync(scope.toggleHidden) })
      scope.mapBig = function () {
        mapv.big = !mapv.big
        try { window.localStorage.setItem('offroadCompanion.mapBig', mapv.big ? '1' : '0') } catch (e) {}
        ;(window.requestAnimationFrame || setTimeout)(function () { fit(); safeDraw() })
      }
      scope.overview = function () { lua('offroadCompanion_main.uiOverview(' + (scope.d.map && scope.d.map.ov ? 'false' : 'true') + ')') }
      scope.panned = function () { return Math.abs(pan.x) + Math.abs(pan.y) > 1 }
      scope.centre = function () { pan.x = 0; pan.y = 0; safeDraw() }

      scope.choose = function (k, v) {
        scope.ui[k] = v
        scope.set(k, BOOL[k] ? v === 'on' : v)
        if (k === 'notes') (window.requestAnimationFrame || setTimeout)(safeDraw)
      }
      scope.typing = function (on) { lua('if setCEFTyping then setCEFTyping(' + (on ? 'true' : 'false') + ') end') }
      scope.setTab = function (t) {
        scope.tab = scope.tab === t ? null : t
        if (t === 'make') return
        if (scope.tab === 'courses' && !scope.ui.source && scope.d.sources.length) {
          scope.ui.source = scope.d.sources[0].id
          scope.listSource()
        }
      }
      scope.kindLabel = function (a) {
        if (a.kind === 'speed_start' && a.limit) return a.limit
        if (a.kind === 'vcp' || a.kind === 'checkpoint' || a.kind === 'danger') return a.name
        return KIND_LABEL[a.kind] || a.name
      }
      scope.limitNum = function (s) { return String(s).split(' ')[0] }
      scope.placeLine = function () {
        var c = scope.d.car
        if (!c) return ''
        return [c.place, c.country].filter(function (x) { return x }).join(', ')
      }

      // -- poll a Lua result until it arrives (the companion answers a few frames later) ------------------------
      function poll (code, done, tries, max) {
        tries = tries || 0
        max = max || 120                  // (x 250 ms)
        lua(code, function (r) {
          if (r || tries > max) { scope.$evalAsync(function () { done(lists(r)) }) } else setTimeout(function () { poll(code, done, tries + 1, max) }, 250)
        })
      }

      // -- search ------------------------------------------------------------------------------------------------
      // One search at a time: the text typed meanwhile waits, and only the newest is searched next (BeamNG.Earth's
      // search allows one Photon request at a time and refused the rest: the user's "no free request slot").
      // Typing searches after a pause (Photon only); Enter / the button search at once, and may also ask Nominatim.
      var searchTimer = null, inFlight = false, queued = null
      var TYPE_PAUSE_MS = 650
      function friendly (err, submitted) {
        var e = String(err || '')
        if (/RateLimited|no free request slot|rate limited|HTTP 429/i.test(e)) return 'The search service is busy. ' + (submitted ? 'Try again in a few seconds.' : 'Press Enter to search again.')
        if (/timed out|Timeout|cannot reach|HTTP 5\d\d|FetchFailed/i.test(e)) return 'The search service is not answering right now. ' + (submitted ? 'Try again in a moment.' : 'Press Enter to try OpenStreetMap\'s other search.')
        return e
      }
      function runSearch (q, submitted) {
        if (inFlight) { queued = { q: q, submitted: submitted || (queued && queued.q === q && queued.submitted) }; return }
        inFlight = true
        scope.ui.searching = true
        var done = function (res) {
          inFlight = false
          if (scope.ui.q === q) {
            scope.ui.searching = false
            scope.ui.searched = q
            if (res && res.results) {
              scope.ui.results = res.results
              scope.ui.searchSource = res.source || (res.via === 'earth' ? 'earth' : null)
            }
            scope.ui.searchError = res ? (res.error ? friendly(res.error, submitted) : '') : 'No answer: is BeamNG.Earth (or the Offroad Companion) running?'
          }
          var next = queued
          queued = null
          if (next && next.q === scope.ui.q && (next.q !== q || next.submitted !== submitted)) runSearch(next.q, next.submitted)
          else if (scope.ui.q !== q && scope.ui.q && scope.ui.q.length >= 3) runSearch(scope.ui.q, false)
          else if (scope.ui.q !== q) scope.ui.searching = false
        }
        lua('offroadCompanion_main and offroadCompanion_main.uiSearch(' + luaStr(q) + ', ' + (submitted ? 'true' : 'false') + ')', function (r) {
          if (!r || r.error) { scope.$evalAsync(function () { done(r ? { error: r.error } : null) }); return }
          var via = r.via === 'companion' ? ', "companion"' : ''
          poll('offroadCompanion_main.uiSearchResult(' + luaNum(r.id) + via + ')', function (res) {
            if (res && r.via) res.via = r.via
            done(res)
          })
        })
      }
      scope.searchChanged = function () {
        clearTimeout(searchTimer)
        var q = scope.ui.q
        scope.ui.searchError = ''
        if (!q || q.length < 3) { scope.ui.results = []; scope.ui.searching = false; return }
        searchTimer = setTimeout(function () { scope.$evalAsync(function () { runSearch(q, false) }) }, TYPE_PAUSE_MS)
      }
      scope.searchNow = function () {
        clearTimeout(searchTimer)
        if (scope.ui.q) runSearch(scope.ui.q, true)
      }
      scope.searchKey = function (e) { if (e.keyCode === 13 || e.key === 'Enter') { e.preventDefault(); scope.searchNow() } }
      scope.go = function (r) {
        lua('offroadCompanion_main.uiGo(' + luaNum(r.lat) + ', ' + luaNum(r.lon) + ', ' + luaStr(r.name) + ')')
        scope.tab = null
      }
      scope.stop = function () { lua('offroadCompanion_main.uiStop()') }
      scope.autodrive = function () { lua('offroadCompanion_main.uiAutodrive(' + (scope.d.autodrive ? 'false' : 'true') + ')') }

      // -- courses ----------------------------------------------------------------------------------------------
      scope.listSource = function () {
        var src = scope.ui.source
        scope.ui.items = []; scope.ui.note = ''; scope.ui.listError = ''
        var s = (scope.d.sources || []).filter(function (x) { return x.id === src })[0]
        if (!s) return
        scope.ui.listing = true
        scope.ui.listSlow = false
        var slowTimer = setTimeout(function () { scope.$evalAsync(function () { scope.ui.listSlow = true }) }, 15000)
        lua('offroadCompanion_main.uiTrackList(' + luaStr(src) + ', "", ' + luaNum(scope.ui.radius) + ')', function (r) {
          if (!r || r.error) { clearTimeout(slowTimer); scope.$evalAsync(function () { scope.ui.listing = false; scope.ui.listError = r && r.error }); return }
          // (OpenStreetMap's Overpass servers can take minutes on a busy day: the companion tries each, twice)
          poll('offroadCompanion_main.uiTrackListResult(' + r.id + ')', function (res) {
            clearTimeout(slowTimer)
            scope.ui.listing = false
            if (scope.ui.source !== src) return
            if (!res) { scope.ui.listError = 'No answer from the companion. Is it still running?'; return }
            scope.ui.items = res.items || []
            scope.ui.note = res.note || ''
            scope.ui.listError = res.error || ''
          }, 0, 960)
        })
      }
      scope.load = function (it) {
        lua('offroadCompanion_main.uiTrackLoad(' + luaStr(scope.ui.source) + ', ' + luaStr(it.id) + ')')
        scope.tab = null
      }
      scope.loadUrl = function () {
        if (!scope.ui.url) return
        lua('offroadCompanion_main.uiTrackLoad("url", ' + luaStr(scope.ui.url) + ')')
        scope.tab = null
      }
      scope.track = function (action) { lua('offroadCompanion_main.uiTrackAction(' + luaStr(action) + ')') }
      scope.set = function (k, v) { lua('offroadCompanion_main.uiSet(' + luaStr(k) + ', ' + (typeof v === 'boolean' ? String(v) : luaStr(v)) + ')') }
      // the zoom's label over + / -: how far the map reaches ahead of the car, and the ring around the car (its radius)
      function shortDist (m) {
        if (!isFinite(m)) return ''
        if (scope.d.units === 'imperial') {
          var ft = m / 0.3048
          if (ft < 1000) return Math.round(ft / 50) * 50 + ' ft'
          var mi = m / 1609.344
          return (mi < 10 ? mi.toFixed(1) : Math.round(mi)) + ' mi'
        }
        if (m < 1000) return Math.round(m / 10) * 10 + ' m'
        return (m < 10000 ? (m / 1000).toFixed(1) : Math.round(m / 1000)) + ' km'
      }
      scope.zoomText = function () {
        var m = scope.d.map
        if (!m || !m.radius) return ''
        var plan = planMode()
        return shortDist(plan ? m.radius / 0.45 * 0.5 : m.radius / 0.62 * 0.68)   // (the car to the top edge)
      }
      scope.ringText = function () { var m = scope.d.map; return m && m.radius ? shortDist(m.radius * 0.5) : '' }
      scope.ovZoomText = function () { var z = ovv.zoom; return z < 10 ? (Math.round(z * 10) / 10) : Math.round(z) }
      scope.zoom = function (f) {
        var z = Math.max(150, Math.min(5000, Math.round(((scope.d.map && scope.d.map.radius) || 600) * f)))
        lua('offroadCompanion_main.uiSet("zoom", ' + z + ')')
      }

      // -- the roadbook box ---------------------------------------------------------------------------------------
      function buildCall (d) {
        var c = d.course, n = d.nav
        // danger and speed zones first, then the corner call, then road maneuvers
        if (c && c.off && !c.waypoints) {
          var rel = c.off.bearing != null && d.car && d.car.heading != null ? ((c.off.bearing - d.car.heading + 540) % 360) - 180 : 0
          return { svg: tulip(rel), dist: c.off.dist, what: c.off.text, warn: true }
        }
        if (c && c.danger) return { svg: tulip(0), dist: c.danger.dist, what: c.danger.name, warn: true }
        if (c && c.zoneAhead) return { svg: tulip(0), dist: c.zoneAhead.dist, what: (d.lang === 'es' ? 'Zona de velocidad' : 'Speed zone') + (c.zoneAhead.limit ? ' ' + c.zoneAhead.limit : ''), zone: true }
        if (c && c.corner && !(n && n.next && n.next.distM < 400)) {
          var ang = (GRADE_ANGLE[c.corner.grade] || 60) * (c.corner.dir === 'left' ? -1 : 1)
          var r = { svg: tulip(ang), dist: c.corner.dist, what: c.corner.text, zone: !!c.zone }
          if (c.corner.into) {
            r.then = (d.lang === 'es' ? 'y ' : 'into ') + c.corner.into
            r.thenSvg = trust(tulip(/^(Left|Izquierda)/.test(c.corner.into) ? -70 : 70))
          }
          return r
        }
        if (n && n.next) {
          var k = n.next.icon
          var r2 = { svg: tulip(ANGLE[k] || 0, k), dist: n.next.dist, what: n.next.text }
          if (n['then']) { r2.then = n['then'].text; r2.thenSvg = trust(tulip(ANGLE[n['then'].icon] || 0, n['then'].icon)) }
          return r2
        }
        if (c && c.waypoints && c.target) {
          var rel2 = d.car && d.car.heading != null ? ((c.target.bearing - d.car.heading + 540) % 360) - 180 : 0
          return { svg: tulip(rel2), dist: c.target.dist, what: c.target.name, then: c.after ? 'then ' + c.after : null }
        }
        if (n && n.basic) {
          var rel3 = d.car && d.car.heading != null && n.bearing != null ? ((n.bearing - d.car.heading + 540) % 360) - 180 : 0
          return { svg: tulip(rel3), dist: n.remaining, what: d.dest && d.dest.name }
        }
        if (c && c.corner == null && !c.waypoints) return { svg: tulip(0), what: d.lang === 'es' ? 'Sigue el curso' : 'Follow the course', dist: c.left }
        if (!d.earth) return { svg: tulip(0), idle: 'Load the BeamNG.Earth level to start' }
        return { svg: tulip(0), idle: d.lang === 'es' ? 'Busca un lugar o carga un curso' : 'Search for a place or load a course' }
      }

      // -- the map: heading-up while driving, north-up when tapping points for a track ----------------------------
      // Streets (OpenStreetMap, from the companion) in the style of Google Maps' dark map, names along them.
      var CLS = {
        motorway: { w: 16, px: 3.4, fill: '#8A7650', rank: 1, major: true },
        trunk: { w: 14, px: 3.2, fill: '#7E6C4C', rank: 2, major: true },
        primary: { w: 12, px: 2.8, fill: '#5C6474', rank: 3 },
        secondary: { w: 11, px: 2.5, fill: '#535B6B', rank: 4 },
        tertiary: { w: 10, px: 2.2, fill: '#4A5262', rank: 5 },
        unclassified: { w: 8, px: 1.8, fill: '#414958', rank: 6 },
        residential: { w: 8, px: 1.8, fill: '#414958', rank: 6 },
        living_street: { w: 6, px: 1.4, fill: '#3B4351', rank: 7 },
        road: { w: 7, px: 1.5, fill: '#3B4351', rank: 7 },
        pedestrian: { w: 5, px: 1.2, fill: '#363E4B', rank: 8 },
        service: { w: 5, px: 1.1, fill: '#363E4B', rank: 8 },
        track: { w: 4, px: 1.1, fill: '#6E5E45', rank: 9, dash: [5, 4] }
      }
      var streets = { version: -1, ways: [] }
      scope.hasStreets = false
      scope.$on('OffroadCompanionStreets', function (event, sel) {
        sel = lists(sel)
        if (!sel || !sel.ways) return
        var ways = []
        for (var i = 0; i < sel.ways.length; i++) {
          var w = sel.ways[i], p = w.p || []
          if (p.length < 4) continue
          var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
          for (var k = 0; k < p.length; k += 2) {
            if (p[k] < x0) x0 = p[k]; if (p[k] > x1) x1 = p[k]
            if (p[k + 1] < y0) y0 = p[k + 1]; if (p[k + 1] > y1) y1 = p[k + 1]
          }
          ways.push({ c: CLS[w.c] || CLS.road, n: w.n || '', p: p, x0: x0, y0: y0, x1: x1, y1: y1 })
        }
        streets = { version: sel.version, ways: ways }
      })

      var canvas = element[0].querySelector('canvas')
      var ctx = canvas.getContext('2d')

      // The whole course (the Course button): its line and checkpoints once, with their bounds. Fitted and north up at
      // first; drag to move it, the wheel (or + / -, a double-click) to zoom where the mouse is, the right button (or
      // shift + drag, the turn buttons) to turn it; Fit, Car (follow the car), heading up, Big (the strips hidden)
      var ov = { version: -1 }
      var ovv = scope.ovv = { zoom: 1, rot: 0, cx: null, cy: null, follow: false, headingUp: false, big: false, eff: 0 }
      var ovGeom = null
      scope.$on('OffroadCompanionOverview', function (event, o) {
        o = lists(o)
        if (!o || !o.pts) return
        var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
        for (var i = 0; i < o.pts.length; i += 2) {
          if (o.pts[i] < x0) x0 = o.pts[i]; if (o.pts[i] > x1) x1 = o.pts[i]
          if (o.pts[i + 1] < y0) y0 = o.pts[i + 1]; if (o.pts[i + 1] > y1) y1 = o.pts[i + 1]
        }
        if (!ov.pts || ov.pts.length < 2 || Math.abs(ov.x1 - ov.x0 - (x1 - x0)) > 1 || Math.abs(ov.y1 - ov.y0 - (y1 - y0)) > 1) {
          ovv.zoom = 1; ovv.rot = 0; ovv.cx = null; ovv.cy = null; ovv.follow = false; ovv.headingUp = false   // (another course)
        }
        ov = { version: o.version, pts: o.pts, wps: o.wps || [], closed: o.closed, step: Number(o.step) || 0,
               x0: x0, y0: y0, x1: x1, y1: y1 }
      })
      function ovShown () { return !!(ovGeom && scope.d.map && scope.d.map.ov) }
      scope.ovFitted = function () { return ovv.zoom === 1 && !ovv.rot && ovv.cx === null && !ovv.follow && !ovv.headingUp }
      scope.ovFit = function () { ovv.zoom = 1; ovv.rot = 0; ovv.cx = null; ovv.cy = null; ovv.follow = false; ovv.headingUp = false; safeDraw() }
      scope.ovCar = function () { ovv.follow = !ovv.follow; if (ovv.follow && ovv.zoom < 4) ovv.zoom = 4; safeDraw() }
      scope.ovHeading = function () { ovv.headingUp = !ovv.headingUp; if (!ovv.headingUp) ovv.rot = 0; safeDraw() }
      scope.ovNorth = function () { ovv.headingUp = false; ovv.rot = 0; safeDraw() }
      scope.ovBig = function () { ovv.big = !ovv.big; (window.requestAnimationFrame || setTimeout)(function () { fit(); safeDraw() }) }
      function ovSetZoom (z, sx, sy) {          // zoom to z keeping the place under the screen point (sx, sy) where it is
        var g = ovGeom
        z = Math.max(0.5, Math.min(3000, z))
        if (!g || sx == null || ovv.follow) { ovv.zoom = z; safeDraw(); return }
        var w0 = ovToWorld(sx, sy)
        var ns = g.fitScale * z
        var ux = (sx - g.w / 2) / ns, uy = -(sy - g.h / 2) / ns
        ovv.cx = w0[0] - (ux * g.cs + uy * g.sn)
        ovv.cy = w0[1] - (-ux * g.sn + uy * g.cs)
        ovv.zoom = z
        safeDraw()
      }
      scope.ovZoom = function (f) { ovSetZoom(ovv.zoom * f, null, null) }
      scope.ovTurn = function (deg) { ovv.headingUp = false; ovv.rot = ((ovv.rot + deg) % 360 + 360) % 360; safeDraw() }
      function ovToWorld (sx, sy) {             // canvas point -> metres (the overview's frame)
        var g = ovGeom
        var ux = (sx - g.w / 2) / g.scale, uy = -(sy - g.h / 2) / g.scale
        return [g.ccx + ux * g.cs + uy * g.sn, g.ccy - ux * g.sn + uy * g.cs]
      }
      function niceLen (m) {
        var steps = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]
        var out = steps[0]
        for (var i = 0; i < steps.length; i++) if (steps[i] <= m) out = steps[i]
        return out
      }
      function drawOverview (m, w, h) {
        var o = m.ov
        var x0 = Math.min(ov.x0, o.x), x1 = Math.max(ov.x1, o.x), y0 = Math.min(ov.y0, o.y), y1 = Math.max(ov.y1, o.y)
        var pad = 22 * S, padTop = 38 * S             // (room for the buttons along the top)
        var fitScale = Math.min((w - 2 * pad) / Math.max(1, x1 - x0), (h - pad - padTop) / Math.max(1, y1 - y0))
        var scale = fitScale * ovv.zoom
        var ccx = ovv.follow ? o.x : (ovv.cx !== null ? ovv.cx : (x0 + x1) / 2)
        var ccy = ovv.follow ? o.y : (ovv.cy !== null ? ovv.cy : (y0 + y1) / 2 + (padTop - pad) / 2 / scale)
        var rot = ovv.headingUp ? (m.heading || 0) : ovv.rot
        ovv.eff = Math.round(rot) % 360
        var a = rot * Math.PI / 180, cs = Math.cos(a), sn = Math.sin(a)
        ovGeom = { w: w, h: h, scale: scale, fitScale: fitScale, cs: cs, sn: sn, ccx: ccx, ccy: ccy }
        canvas.className = 'ov' + (ovDrag ? ' dragging' : '')
        function P (x, y) {
          var dx = x - ccx, dy = y - ccy
          return [w / 2 + (dx * cs - dy * sn) * scale, h / 2 - (dx * sn + dy * cs) * scale]
        }
        ctx.lineJoin = 'round'; ctx.lineCap = 'round'
        var n = ov.pts.length / 2, done = Math.max(0, Math.min(n - 1, o.done || 0))
        var lw = Math.max(3, Math.min(6, 3 * Math.pow(ovv.zoom, 0.2))) * S
        for (var pass = 0; pass < 2; pass++) {             // done part dim, the rest bright
          var aa = pass === 0 ? 0 : done, bb = pass === 0 ? done : n - 1
          if (bb <= aa) continue
          ctx.beginPath()
          var p0 = P(ov.pts[2 * aa], ov.pts[2 * aa + 1]); ctx.moveTo(p0[0], p0[1])
          for (var i = aa + 1; i <= bb; i++) { var q = P(ov.pts[2 * i], ov.pts[2 * i + 1]); ctx.lineTo(q[0], q[1]) }
          ctx.lineWidth = pass === 0 ? lw * 0.85 : lw
          ctx.strokeStyle = pass === 0 ? 'rgba(39,217,255,.35)' : '#27D9FF'
          ctx.stroke()
        }
        var col = { vcp: '#27D9FF', checkpoint: '#27D9FF', danger: '#FF4D3D', speed_start: '#E8B44A', speed_end: '#E8B44A',
                    start: '#5BE38A', finish: '#5BE38A', pit: '#93A0B8' }
        var doneS = ov.step > 0 ? done * ov.step : -1
        var r = Math.max(1.8, Math.min(5, 1.8 + 0.9 * Math.log(Math.max(1, ovv.zoom)) / Math.LN2)) * S
        var shown = []
        ov.wps.forEach(function (wp) {
          var p = P(wp[0], wp[1])
          if (p[0] < -20 || p[0] > w + 20 || p[1] < -20 || p[1] > h + 20) return
          var passed = wp[4] != null && wp[4] >= 0 && wp[4] < doneS
          ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 2 * Math.PI)
          ctx.globalAlpha = passed ? 0.45 : 1
          ctx.fillStyle = col[wp[2]] || '#fff'; ctx.fill(); ctx.strokeStyle = '#0F1524'; ctx.lineWidth = 1.2 * S; ctx.stroke()
          ctx.globalAlpha = 1
          shown.push({ p: p, wp: wp, passed: passed })
        })
        // names where there is room for them (zoomed in): never over another name
        if (shown.length <= 60) {
          ctx.font = '600 ' + (10 * S).toFixed(1) + 'px sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
          var boxes = []
          shown.forEach(function (it) {
            var name = String(it.wp[3] || '')
            if (!name) return
            var tw = ctx.measureText(name).width, th = 12 * S
            var bx = it.p[0] + r + 3 * S, by = it.p[1] - th / 2
            if (bx + tw > w - 4) bx = it.p[0] - r - 3 * S - tw
            var box = [bx - 2, by - 1, bx + tw + 2, by + th + 1]
            if (box[0] < 0 || box[1] < 0 || box[3] > h) return
            for (var k = 0; k < boxes.length; k++) {
              var q = boxes[k]
              if (box[0] < q[2] && box[2] > q[0] && box[1] < q[3] && box[3] > q[1]) return
            }
            for (var j = 0; j < shown.length; j++) {     // (nor over another dot)
              var d = shown[j].p
              if (shown[j] !== it && d[0] + r > box[0] && d[0] - r < box[2] && d[1] + r > box[1] && d[1] - r < box[3]) return
            }
            boxes.push(box)
            ctx.fillStyle = 'rgba(10,14,24,.75)'; ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1])
            ctx.fillStyle = it.passed ? 'rgba(201,209,222,.6)' : '#EEF2F8'
            ctx.fillText(name, bx, it.p[1])
          })
          ctx.textBaseline = 'alphabetic'
        }
        // a scale bar (bottom middle)
        var len = niceLen(0.28 * w / scale), bl = len * scale, bx0 = w / 2 - bl / 2, byy = h - 9 * S
        ctx.strokeStyle = 'rgba(201,209,222,.75)'; ctx.lineWidth = 2 * S
        ctx.beginPath(); ctx.moveTo(bx0, byy - 3 * S); ctx.lineTo(bx0, byy); ctx.lineTo(bx0 + bl, byy); ctx.lineTo(bx0 + bl, byy - 3 * S); ctx.stroke()
        ctx.fillStyle = 'rgba(201,209,222,.85)'; ctx.font = '500 ' + (10 * S).toFixed(1) + 'px sans-serif'; ctx.textAlign = 'center'
        ctx.fillText(len >= 1000 ? (len / 1000) + ' km' : len + ' m', w / 2, byy - 5 * S)
        // the car
        var c = P(o.x, o.y)
        ctx.save(); ctx.translate(c[0], c[1]); ctx.rotate(((m.heading || 0) - rot) * Math.PI / 180); ctx.scale(S, S)
        ctx.beginPath(); ctx.moveTo(0, -10); ctx.lineTo(7, 7); ctx.lineTo(0, 3.5); ctx.lineTo(-7, 7); ctx.closePath()
        ctx.fillStyle = '#EEF2F8'; ctx.fill(); ctx.strokeStyle = '#0F1524'; ctx.lineWidth = 2; ctx.stroke()
        ctx.restore()
        view = null
      }

      // moving, zooming and turning the overview with the mouse
      var ovDrag = null
      function canvasPt (e) { var rr = canvas.getBoundingClientRect(); return [e.clientX - rr.left, e.clientY - rr.top] }
      function ovDown (e) {
        if (!ovShown()) return false
        var pt = canvasPt(e)
        var turn = e.button === 2 || (e.button === 0 && e.shiftKey)
        if (e.button !== 0 && e.button !== 2) return false
        ovDrag = { turn: turn, x: pt[0], y: pt[1], cx: ovGeom.ccx, cy: ovGeom.ccy, rot: ovGeom ? ovv.eff : 0,
                   a0: Math.atan2(pt[1] - ovGeom.h / 2, pt[0] - ovGeom.w / 2), g: ovGeom }
        e.preventDefault()
        return true
      }
      function ovMove (e) {
        if (!ovDrag) return false
        var pt = canvasPt(e), g = ovDrag.g
        if (ovDrag.turn) {
          var a1 = Math.atan2(pt[1] - g.h / 2, pt[0] - g.w / 2)
          ovv.headingUp = false
          ovv.rot = ((ovDrag.rot - (a1 - ovDrag.a0) * 180 / Math.PI) % 360 + 360) % 360
        } else {
          var ux = (pt[0] - ovDrag.x) / g.scale, uy = -(pt[1] - ovDrag.y) / g.scale
          ovv.follow = false
          ovv.cx = ovDrag.cx - (ux * g.cs + uy * g.sn)
          ovv.cy = ovDrag.cy - (-ux * g.sn + uy * g.cs)
        }
        safeDraw()
        return true
      }
      function ovUp () { if (!ovDrag) return false; ovDrag = null; safeDraw(); return true }
      function onWheel (e) {
        if (!ovShown()) return
        e.preventDefault()
        var pt = canvasPt(e)
        ovSetZoom(ovv.zoom * (e.deltaY < 0 ? 1.25 : 0.8), pt[0], pt[1])
      }
      function onDbl (e) {
        if (!ovShown()) return
        e.preventDefault()
        var pt = canvasPt(e)
        ovSetZoom(ovv.zoom * 2, pt[0], pt[1])
      }
      function onCtx (e) { if (ovShown()) e.preventDefault() }
      canvas.addEventListener('wheel', onWheel)
      canvas.addEventListener('dblclick', onDbl)
      canvas.addEventListener('contextmenu', onCtx)

      // -- size: everything scales with the app's width (drag it bigger in the UI editor: bigger text); when the
      // app is too short for what is open, it shrinks to fit, down to MIN_S; below that only the strips under the
      // map scroll (the roadbook box, the map and the tabs always stay whole)
      var root = element[0], S = 1
      var BASE_W = 330, MIN_S = 0.85, MAX_S = 2.6, MAP_MIN = 110, TABS = 34, MAP_SHARE = 0.5, LOWER_FIT = 0.18
      function fit () {
        var w = root.clientWidth, h = root.clientHeight
        if (!w || !h) return
        var sw = Math.max(MIN_S, Math.min(MAX_S, w / BASE_W))
        root.style.setProperty('--s', sw.toFixed(3))
        var call = root.querySelector('.call'), lower = root.querySelector('.lower'), map = root.querySelector('.mapWrap')
        // the map keeps at least half of the app's height (the user, 2026-10-22); the strips under it scroll rather than
        // shrinking it (their first few lines count when the text is scaled to fit)
        // the map: at least half the app's height not counting the notes box (the user, 2026-10-22)
        var side = /notes-(left|right)/.test(root.className)
        var callH = call ? call.offsetHeight : 0
        var mapMin = Math.max(MAP_MIN * sw, MAP_SHARE * (h - (side ? 0 : callH)))
        var lowerH = lower ? Math.min(lower.scrollHeight, LOWER_FIT * h) : 0
        var need = (side ? 0 : callH) + lowerH + mapMin + TABS * sw + 2
        var s = need > h ? Math.max(MIN_S, sw * h / need) : sw
        if (s !== sw) root.style.setProperty('--s', s.toFixed(3))
        if (map) map.style.minHeight = Math.round(Math.max(MAP_MIN * s, MAP_SHARE * (h - (side ? 0 : (call ? call.offsetHeight : 0))))) + 'px'
        var rest = root.querySelector('.rest')     // (the tabs' short names when the app, or its part beside the notes, is narrow)
        if (rest) root.classList.toggle('narrow', rest.clientWidth < 290 * s)
        S = s
      }
      var view = null           // the last frame's transform, for taps
      function planMode () { return scope.d.editor && scope.d.editor.mode === 'plan' && !scope.tab }

      // Names along the streets: each on the longest nearly straight stretch of its street on screen, upright,
      // major roads first, never over another name or the car, one per street name nearby.
      function labels (list, W, H, carP, keepOut) {
        var placed = [], byName = {}, count = 0
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
        for (var i = 0; i < list.length && count < 32; i++) {
          var it = list[i], w = it.w
          if (!w.n) continue
          var font = w.c.rank <= 3 ? '600 ' + (12 * S).toFixed(1) + 'px sans-serif' : '500 ' + (11 * S).toFixed(1) + 'px sans-serif'
          ctx.font = font
          var tw = ctx.measureText(w.n).width
          var pts = it.s, best = null
          var a = 0
          while (a < pts.length - 1) {
            var b = a + 1
            var ang0 = Math.atan2(pts[b][1] - pts[a][1], pts[b][0] - pts[a][0])
            while (b + 1 < pts.length) {
              var ang = Math.atan2(pts[b + 1][1] - pts[b][1], pts[b + 1][0] - pts[b][0])
              var dd = Math.abs(((ang - ang0 + 3 * Math.PI) % (2 * Math.PI)) - Math.PI)
              if (dd > (w.c.rank <= 3 ? 0.4 : 0.26)) break
              b++
            }
            var dx = pts[b][0] - pts[a][0], dy = pts[b][1] - pts[a][1], len = Math.sqrt(dx * dx + dy * dy)
            if (len > tw + 18 * S && (!best || len > best.len)) best = { a: pts[a], b: pts[b], len: len }
            a = b
          }
          if (!best) continue
          var mx = (best.a[0] + best.b[0]) / 2, my = (best.a[1] + best.b[1]) / 2
          if (mx < 20 * S || my < 14 * S || mx > W - 20 * S || my > H - 14 * S) continue
          var an = Math.atan2(best.b[1] - best.a[1], best.b[0] - best.a[0])
          if (an > Math.PI / 2) an -= Math.PI
          if (an < -Math.PI / 2) an += Math.PI
          // the label as a row of circles along it
          var n = Math.max(1, Math.ceil(tw / (12 * S))), circles = [], ok = true
          for (var k = 0; k < n; k++) {
            var t = (k + 0.5) / n - 0.5
            circles.push([mx + Math.cos(an) * t * tw, my + Math.sin(an) * t * tw])
          }
          for (var c = 0; c < circles.length && ok; c++) {
            var cc = circles[c]
            if ((cc[0] - carP[0]) * (cc[0] - carP[0]) + (cc[1] - carP[1]) * (cc[1] - carP[1]) < 484 * S * S) ok = false
            for (var ko = 0; ko < keepOut.length && ok; ko++) {
              var R = keepOut[ko]
              if (cc[0] > R[0] - 8 * S && cc[0] < R[2] + 8 * S && cc[1] > R[1] - 8 * S && cc[1] < R[3] + 8 * S) ok = false
            }
            for (var q = 0; q < placed.length && ok; q++) {
              var pq = placed[q]
              if ((cc[0] - pq[0]) * (cc[0] - pq[0]) + (cc[1] - pq[1]) * (cc[1] - pq[1]) < 196 * S * S) ok = false
            }
          }
          var prev = byName[w.n]
          if (ok && prev) {
            for (var r = 0; r < prev.length && ok; r++) {
              if ((mx - prev[r][0]) * (mx - prev[r][0]) + (my - prev[r][1]) * (my - prev[r][1]) < 25600 * S * S) ok = false
            }
          }
          if (!ok) continue
          Array.prototype.push.apply(placed, circles)
          ;(byName[w.n] = byName[w.n] || []).push([mx, my])
          count++
          ctx.save()
          ctx.translate(mx, my); ctx.rotate(an)
          ctx.lineWidth = 3.5 * S; ctx.strokeStyle = 'rgba(17,23,34,.92)'; ctx.lineJoin = 'round'
          ctx.strokeText(w.n, 0, 0)
          ctx.fillStyle = w.c.major ? '#F3D19C' : '#C9D1DE'
          ctx.fillText(w.n, 0, 0)
          ctx.restore()
        }
      }

      var drawFailed = null
      function safeDraw () {
        try {
          fit(); draw()
          drawFailed = null
        } catch (e) {               // logged once per kind of failure, not every frame; the rest of the app goes on
          var msg = String(e && e.message || e)
          if (msg !== drawFailed && window.console) console.warn('OffroadCompanion map: ' + msg)
          drawFailed = msg
        }
      }
      function draw () {
        var d = scope.d, m = d.map
        var w = canvas.clientWidth, h = canvas.clientHeight
        var dpr = window.devicePixelRatio || 1
        if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
          canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        ctx.clearRect(0, 0, w, h)
        if (!m) { view = null; ovGeom = null; return }
        if (m.ov && ov.version === m.ov.v && ov.pts && ov.pts.length >= 2) { drawOverview(m, w, h); return }
        ovGeom = null
        var plan = planMode()
        canvas.className = plan ? 'plan' : ''
        var cx = w / 2, cy = plan ? h / 2 : h * 0.68
        var scale = (h * (plan ? 0.45 : 0.62)) / m.radius
        var mapHeading = plan ? 0 : (m.heading || 0)
        var hd = mapHeading * Math.PI / 180, cs = Math.cos(hd), sn = Math.sin(hd)
        var ox = plan ? pan.x : 0, oy = plan ? pan.y : 0
        function P (x, y) {
          x -= ox; y -= oy
          var rx = x * cs - y * sn, ry = x * sn + y * cs
          return [cx + rx * scale, cy - ry * scale]
        }
        view = { cx: cx, cy: cy, scale: scale, cs: cs, sn: sn, ox: ox, oy: oy }
        // streets: the selection is around (sx, sy); what is in view, minor ones first so main roads lie on top
        var shown = []
        if (m.sv != null && m.sv === streets.version && streets.ways.length) {
          var reach = Math.sqrt(w * w + h * h) / scale
          var vx = m.sx + ox, vy = m.sy + oy
          for (var i = streets.ways.length - 1; i >= 0; i--) {
            var sw = streets.ways[i]
            if (sw.x1 < vx - reach || sw.x0 > vx + reach || sw.y1 < vy - reach || sw.y0 > vy + reach) continue
            var sp = []
            for (var k = 0; k < sw.p.length; k += 2) sp.push(P(sw.p[k] - m.sx, sw.p[k + 1] - m.sy))
            shown.push({ w: sw, s: sp })
          }
          ctx.lineJoin = 'round'; ctx.lineCap = 'round'
          for (var pass = 0; pass < 2; pass++) {
            for (var j = 0; j < shown.length; j++) {
              var c = shown[j].w.c, pts = shown[j].s
              var px = Math.max(c.px * S, c.w * scale)
              ctx.beginPath()
              ctx.moveTo(pts[0][0], pts[0][1])
              for (var q = 1; q < pts.length; q++) ctx.lineTo(pts[q][0], pts[q][1])
              ctx.setLineDash(pass === 1 && c.dash ? [c.dash[0] * S, c.dash[1] * S] : [])
              ctx.lineWidth = pass === 0 ? px + 2 * S : px
              ctx.strokeStyle = pass === 0 ? '#121925' : c.fill
              if (pass === 0 && c.dash) continue
              ctx.stroke()
            }
          }
          ctx.setLineDash([])
        }
        // range ring and north
        ctx.strokeStyle = 'rgba(147,160,184,.14)'; ctx.lineWidth = 1
        var c0 = P(0, 0)
        ctx.beginPath(); ctx.arc(c0[0], c0[1], m.radius * scale * 0.5, 0, 2 * Math.PI); ctx.stroke()
        function line (pts, color, width, doneColor) {
          if (!pts || pts.length < 2) return
          ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.lineWidth = width
          for (var pass = 0; pass < 2; pass++) {
            ctx.beginPath()
            var started = false
            for (var i = 0; i < pts.length; i++) {
              var done = pts[i][2] === 1
              if ((pass === 0) !== done) { started = false; continue }
              var p = P(pts[i][0], pts[i][1])
              if (!started) { ctx.moveTo(p[0], p[1]); started = true } else ctx.lineTo(p[0], p[1])
            }
            ctx.strokeStyle = pass === 0 ? doneColor : color
            ctx.stroke()
          }
        }
        line(m.course, '#27D9FF', 5 * S, 'rgba(39,217,255,.3)')
        line(m.route, '#E8B44A', 4 * S, 'rgba(232,180,74,.3)')
        // the track being made, its points and checkpoints
        ;(m.draft || []).forEach(function (dl) {
          line(dl, '#FF6AD5', 4 * S, '#FF6AD5')
          if (dl.length < 80) {
            dl.forEach(function (q) {
              var p = P(q[0], q[1])
              ctx.beginPath(); ctx.arc(p[0], p[1], 3 * S, 0, 2 * Math.PI); ctx.fillStyle = '#FF6AD5'; ctx.fill()
            })
          }
        })
        ;(m.draftCps || []).forEach(function (cp) {
          var p = P(cp[0], cp[1])
          ctx.beginPath(); ctx.arc(p[0], p[1], 6 * S, 0, 2 * Math.PI)
          ctx.fillStyle = '#FFFFFF'; ctx.fill(); ctx.strokeStyle = '#FF6AD5'; ctx.lineWidth = 3 * S; ctx.stroke()
        })
        // street names
        var carP = P(0, 0)
        var north = P(0, m.radius * 0.95)
        if (shown.length) {
          // not under the speed box, the zoom buttons, the credit, the hint or the N
          var keepOut = [[0, h - 75 * S, 80 * S, h], [w - 46 * S, h - 82 * S, w, h], [w - 140 * S, h - 22 * S, w, h],
                         [north[0] - 8 * S, north[1] - 10 * S, north[0] + 8 * S, north[1] + 6 * S]]
          if (plan) keepOut.push([0, 0, w, 34 * S])
          shown.sort(function (a, b) { return a.w.c.rank - b.w.c.rank })
          labels(shown, w, h, carP, keepOut)
        }
        if (!plan) {
          ctx.fillStyle = 'rgba(147,160,184,.7)'; ctx.font = '600 ' + (11 * S).toFixed(1) + 'px sans-serif'; ctx.textAlign = 'center'
          ctx.fillText('N', north[0], north[1])
        }
        // course waypoints
        var col = { vcp: '#27D9FF', checkpoint: '#27D9FF', danger: '#FF4D3D', speed_start: '#E8B44A', speed_end: '#E8B44A',
                    start: '#5BE38A', finish: '#5BE38A', pit: '#93A0B8' }
        ;(m.wps || []).forEach(function (wp) {
          var p = P(wp[0], wp[1])
          ctx.beginPath(); ctx.arc(p[0], p[1], 5 * S, 0, 2 * Math.PI)
          ctx.fillStyle = wp[3] === 'hit' ? '#5BE38A' : wp[3] === 'miss' ? '#FF4D3D' : (col[wp[2]] || '#fff')
          ctx.fill(); ctx.strokeStyle = '#0F1524'; ctx.lineWidth = 2 * S; ctx.stroke()
        })
        // the car: pointing up when the map turns with it, else its heading
        ctx.save()
        ctx.translate(carP[0], carP[1])
        ctx.rotate(((m.heading || 0) - mapHeading) * Math.PI / 180)
        ctx.scale(S, S)
        ctx.beginPath()
        ctx.moveTo(0, -11); ctx.lineTo(8, 8); ctx.lineTo(0, 4); ctx.lineTo(-8, 8); ctx.closePath()
        ctx.fillStyle = '#EEF2F8'; ctx.fill(); ctx.strokeStyle = '#0F1524'; ctx.lineWidth = 2; ctx.stroke()
        ctx.restore()
      }

      // tapping (a point for the track) and dragging (moving the map) while making a track
      var drag = null
      function toMap (e) {
        var r = canvas.getBoundingClientRect()
        var rx = (e.clientX - r.left - view.cx) / view.scale, ry = -(e.clientY - r.top - view.cy) / view.scale
        return [rx * view.cs + ry * view.sn + view.ox, -rx * view.sn + ry * view.cs + view.oy]
      }
      function onDown (e) {
        if (ovDown(e)) return
        if (!planMode() || !view || e.button !== 0) return
        drag = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y, moved: false }
        e.preventDefault()
      }
      function onMove (e) {
        if (ovMove(e)) return
        if (!drag || !view) return
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y
        if (!drag.moved && dx * dx + dy * dy < 36) return
        drag.moved = true
        pan.x = drag.px - dx / view.scale
        pan.y = drag.py + dy / view.scale
        safeDraw()
      }
      function onUp (e) {
        if (ovUp(e)) return
        if (!drag) return
        var wasTap = !drag.moved
        drag = null
        if (wasTap && planMode() && view) {
          var q = toMap(e)
          scope.ed('add_rel', Math.round(q[0] * 10) / 10, Math.round(q[1] * 10) / 10)
        }
      }
      canvas.addEventListener('mousedown', onDown)
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)

      // -- updates from Lua --------------------------------------------------------------------------------------
      scope.$on('OffroadCompanionUpdate', function (event, data) {
        scope.$evalAsync(function () {
          scope.d = lists(data) || {}
          if (Array.isArray(scope.d)) scope.d = {}
          var cn = data && data.paint && data.paint.codeNote
          if (cn !== lastCodeNote) { lastCodeNote = cn; if (cn && !data.paint.codeErr) settingsSynced = false }  // (a pasted code set them)
          if (!settingsSynced && data && data.settings) {
            settingsSynced = true
            scope.ui.lang = data.settings.lang; scope.ui.units = data.settings.units
            scope.ui.ribbon = data.settings.ribbon ? 'on' : 'off'; scope.ui.autoRoute = data.settings.autoRoute ? 'on' : 'off'
            scope.ui.paint = data.settings.paint === false ? 'off' : 'on'; scope.ui.paintSize = Number(data.settings.paintSize) || 1
            scope.ui.clearCourse = data.settings.clearCourse === false ? 'off' : 'on'
            scope.ui.clearRoute = data.settings.clearRoute === false ? 'off' : 'on'
            scope.ui.streets = data.settings.streets === false ? 'off' : 'on'
            var mk = data.settings.markers
            scope.ui.markers = mk === false || mk === 'off' ? 'off' : (mk === 'full' ? 'full' : 'checkpoints')
            scope.ui.spectators = data.settings.spectators === 'off' || data.settings.spectators === 'lots' ? data.settings.spectators : 'some'
            scope.ui.nightLights = data.settings.nightLights === 'off' || data.settings.nightLights === 'bright' ? data.settings.nightLights : 'on'
            scope.ui.crowdSound = data.settings.crowdSound === false ? 'off' : 'on'
            scope.ui.wetGround = data.settings.wetGround === false ? 'off' : 'on'
            scope.ui.ruts = data.settings.ruts || 'auto'
            scope.ui.rough = data.settings.rough || 'auto'
            scope.ui.replays = data.settings.replays === false ? 'off' : 'on'
            scope.ui.notes = ({ top: 1, bottom: 1, left: 1, right: 1 })[data.settings.notes] ? data.settings.notes : 'top'
          }
          var c = buildCall(scope.d)
          c.svg = trust(c.svg)
          scope.call = c
          scope.toasts = (scope.d.course && scope.d.course.events) || []
          scope.hasStreets = !!(scope.d.map && scope.d.map.sv === streets.version && streets.ways.length)
          // after the digest has laid the panel out (the strips above and below change the map's height)
          ;(window.requestAnimationFrame || setTimeout)(safeDraw)
        })
      })

      var hello = function (on, fresh) {
        if (scope.ui.hidden) on = false
        lua('if offroadCompanion_main then offroadCompanion_main.uiMounted(' + on + (fresh ? ', true' : '') + ') end')
      }
      hello(true, true)                   // (fresh: the streets are sent again for this new app)
      var again = setInterval(function () { hello(true) }, 3000)
      scope.$on('$destroy', function () {
        clearInterval(again); clearTimeout(searchTimer); clearTimeout(sureTimer); hello(false); scope.typing(false)
        canvas.removeEventListener('mousedown', onDown)
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
        canvas.removeEventListener('wheel', onWheel)
        canvas.removeEventListener('dblclick', onDbl)
        canvas.removeEventListener('contextmenu', onCtx)
      })
    }
  }
}])
