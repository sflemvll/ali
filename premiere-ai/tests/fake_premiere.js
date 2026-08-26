// محاكي مبسّط لبيئة ExtendScript داخل بريمير — لاختبار host.jsx خارج التطبيق.
const fs = require('fs'), vm = require('vm');

function T(sec){ return { seconds: sec, ticks: String(Math.round(sec*254016000000)),
  getFormatted(){ return '00:00:0'+Math.floor(sec)+':00'; } }; }

function mkClip(name, start, dur){
  return { name, start:T(start), end:T(start+dur), duration:T(dur),
           inPoint:T(0), outPoint:T(dur), isSelected:()=>false,
           remove(){ removed.push(name); }, move(){}, components:{numItems:0} };
}
const removed = [], markers = [];

const clips = [mkClip('a.mp4',0,5), mkClip('b.mp4',5,4)];
const track = { name:'V1', isMuted:()=>false,
  clips: Object.assign([...clips], {numItems: clips.length}),
  overwriteClip(item, t){ added.push([item.name, t.seconds]); },
  insertClip(item, t){ added.push([item.name, t.seconds]); } };
const added = [];

const seq = {
  name:'Sequence 01', sequenceID:'abc', end:String(9*254016000000),
  videoTracks: Object.assign([track], {numTracks:1}),
  audioTracks: Object.assign([], {numTracks:0}),
  getPlayerPosition:()=>T(2.5),
  setPlayerPosition(ticks){ this._pos = ticks; },
  getSettings:()=>({ videoFrameRate:{seconds:1/25} }),
  videoDisplayFormat: 110,
  markers: { createMarker(sec){ const m={start:T(sec),end:T(sec),name:'',comments:''}; markers.push(m); return m; },
             getFirstMarker(){ return markers[0]; },
             getNextMarker(m){ return markers[markers.indexOf(m)+1]; } }
};

const rootItem = { name:'Root', children: Object.assign(
  [{name:'a.mp4', type:1, getMediaPath:()=>'C:/v/a.mp4', children:{numItems:0}},
   {name:'b.mp4', type:1, getMediaPath:()=>'C:/v/b.mp4', children:{numItems:0}}],
  {numItems:2}) };

const ctx = {
  Time: function(){ this.seconds = 0; },
  ProjectItemType: { CLIP:1, BIN:2, FILE:4 },
  app: { version:'25.1.0', appName:'Premiere Pro',
         project: { name:'Test.prproj', path:'C:/p/Test.prproj', rootItem,
                    activeSequence: seq,
                    sequences: Object.assign([seq], {numSequences:1}),
                    importFiles:()=>true, save(){ saved.push(1); } },
         enableQE(){}, encoder:{ ENCODE_ENTIRE:0 } },
  qe: { project: { getActiveSequence:()=>({}) } },
  __probe: { removed, added, markers }
};
const saved = [];
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'), ctx);

// نقرأ الكود من stdin وننفّذه عبر AI_run، ونطبع JSON على stdout
let input='';
process.stdin.on('data', d=>input+=d);
process.stdin.on('end', ()=>{
  const out = vm.runInContext('AI_run(' + JSON.stringify(input) + ')', ctx);
  process.stdout.write(out);
});
