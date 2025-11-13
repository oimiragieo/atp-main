// Minimal JS SDK POC: builds a frame and serializes/deserializes similar to Python SDK.
function buildFrame(type, payload){
  return {type, ts: Date.now(), payload};
}
function serialize(frame){
  return JSON.stringify(frame);
}
function deserialize(s){
  return JSON.parse(s);
}
function roundTrip(){
  const f = buildFrame('ping', {n:1});
  const s = serialize(f);
  const d = deserialize(s);
  if(d.type !== 'ping' || d.payload.n !== 1) throw new Error('Round trip failed');
  return 'OK: js sdk POC passed';
}
if(require.main === module){
  console.log(roundTrip());
}
module.exports = { buildFrame, serialize, deserialize, roundTrip };
