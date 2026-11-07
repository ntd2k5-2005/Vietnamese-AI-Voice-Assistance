// Run the shipped JS, not a reimplementation of the endpoint/playout logic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'voice_app', 'web_assets');

function browser() {
  const elements = new Map();
  const context = vm.createContext({
    console, performance, setTimeout, clearTimeout, Float32Array, ArrayBuffer,
    DataView, Blob, FormData, window: {}, sessionStorage: {setItem() {}},
    document: {readyState: 'loading', addEventListener() {}, getElementById(id) {
      if (!elements.has(id)) elements.set(id, {style: {}, classList: {add() {}, remove() {}}, removeAttribute() {}});
      return elements.get(id);
    }},
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'app.js'), 'utf8'), context);
  vm.runInContext(`
    setStatus = () => {}; setText = () => {};
    setTurnBusy = value => {turnBusy = value};
    audioCtx = {sampleRate: 1000}; pcmNode = {port: {postMessage() {}}};
    postBrowserMetrics = async () => {};
  `, context);
  return context;
}

async function main() {
  const results = [];
  const c = browser();
  vm.runInContext(`
    pttRecording = true;
    sent = 0;
    toggleMic = async () => {pttRecording = false; sent++};
    for (let i=0; i<10; i++) handleMicFrame(new Float32Array(100));
  `, c);
  assert.equal(vm.runInContext('sent', c), 0, 'silence alone must not send a question');
  vm.runInContext(`
    for (let i=0; i<3; i++) handleMicFrame(new Float32Array(100).fill(0.1));
    for (let i=0; i<7; i++) handleMicFrame(new Float32Array(100));
    for (let i=0; i<7; i++) handleMicFrame(new Float32Array(100));
  `, c);
  assert.equal(vm.runInContext('sent', c), 1, 'speech followed by silence submits exactly once');
  results.push('PTT auto endpoint, no empty request or duplicate submission');

  vm.runInContext(`
    vadEnabled = true; turnBusy = true; currentTurn = 'answer';
    vadConfig.barge_in_enabled = false; interrupts = 0;
    interruptCurrentTurn = async () => {interrupts++; currentTurn=null};
    for (let i=0; i<30; i++) handleMicFrame(new Float32Array(100).fill(0.1));
  `, c);
  assert.equal(vm.runInContext('interrupts', c), 0, 'speaker echo must not cancel a turn');
  vm.runInContext(`
    vadConfig.barge_in_enabled = true;
    for (let i=0; i<3; i++) handleMicFrame(new Float32Array(30).fill(0.1));
  `, c);
  assert.equal(vm.runInContext('interrupts', c), 0, 'barge-in must wait for sustained speech');
  vm.runInContext(`for (let i=0; i<8; i++) handleMicFrame(new Float32Array(30).fill(0.1));`, c);
  assert.equal(vm.runInContext('interrupts', c), 1);
  results.push('speaker isolation and explicit debounced barge-in');

  const p = browser();
  vm.runInContext(`
    ensureConversation = async () => {conversationId='test'};
    ensureAudioWorklet = async () => audioCtx;
    appendMessage = () => ({dataset:{}});
    connectControl = async () => {serverTurnDone=true};
    streamAudio = async () => {};
    task = startTurn(async () => ({ok:true, json:async()=>({turn_id:'one',generation:1,conversation_id:'test',sample_rate:1000})}));
  `, p);
  await new Promise(setImmediate);
  assert.equal(vm.runInContext('turnBusy', p), true, 'network end must not finish playout');
  const epoch = vm.runInContext('playbackEpoch', p);
  vm.runInContext(`handleWorkletMessage({type:'drained',epoch:${epoch-1}})`, p);
  assert.equal(vm.runInContext('playbackDrained', p), false, 'ignore old player completion');
  vm.runInContext(`handleWorkletMessage({type:'drained',epoch:${epoch}})`, p);
  await p.task;
  assert.equal(vm.runInContext('turnBusy', p), false);
  results.push('turn ownership waits for real FIFO drain and ignores stale epochs');

  vm.runInContext(`
    task = startTurn(async () => ({ok:true, json:async()=>({turn_id:'two',generation:1,conversation_id:'test',sample_rate:1000})}));
  `, p);
  await new Promise(setImmediate);
  vm.runInContext('flushPlayback()', p);
  await p.task;
  results.push('cancel/flush releases playout waiter');

  const streaming = browser();
  let attempts = 0;
  const queued = [];
  function packet(sequence) {
    const buffer = new ArrayBuffer(74), view = new DataView(buffer);
    for(let i=0;i<4;i++)view.setUint8(i,'V10P'.charCodeAt(i));
    view.setUint16(4,1,true);view.setUint16(6,72,true);
    view.setUint32(8,sequence,true);view.setUint32(12,1,true);view.setUint32(20,1,true);
    return buffer;
  }
  streaming.WebSocket = class {
    constructor() {
      const attempt = ++attempts;
      queueMicrotask(()=>{
        for(const seq of (attempt===1 ? [1,1,3] : [2,3]))this.onmessage({data:packet(seq)});
        if(attempt===2)this.onmessage({data:JSON.stringify({type:'end'})});
      });
    }
    close(code) {queueMicrotask(()=>this.onclose?.({code}));}
  };
  streaming.location={protocol:'http:',host:'fixture'};
  streaming.capture=message=>{if(message.type==='pcm')queued.push(message.sequence)};
  vm.runInContext(`
    currentTurn='stream'; currentGeneration=1;
    ensureAudioWorklet=async()=>audioCtx;
    pcmNode.port.postMessage=capture;
    task=streamAudio('stream',1,playbackEpoch,1000);
  `,streaming);
  await streaming.task;
  assert.deepEqual(queued,[1,2,3],'resume missing packets without skipping or repeating speech');
  assert.equal(attempts,2);
  results.push('PCM duplicate rejection and lossless cursor resume after a gap');

  const textSync = browser();
  textSync.captureText = [];
  vm.runInContext(`
    currentTurn='sync'; currentGeneration=1;
    updateAssistant=(_id,text)=>captureText.push(text);
    handleEvent({type:'llm_delta',answer:'Xin chào bạn.'},'sync',1);
  `, textSync);
  assert.equal(textSync.captureText.length,0,'LLM text must not appear ahead of audio');
  vm.runInContext(`
    speechUnit(1).startFrame=0;
    handleEvent({type:'speech_unit_queued',unit_index:1,speech_text:'Xin chào bạn.'},'sync',1);
    handleEvent({type:'tts_unit_done',unit:1,speech_text:'Xin chào bạn.',audio_duration_ms:1000},'sync',1);
    handleWorkletMessage({type:'metrics',epoch:playbackEpoch,cumulativeConsumedFrames:500});
  `,textSync);
  assert.equal(textSync.captureText.at(-1),'Xin ch','half the audio reveals half the Unicode characters');
  vm.runInContext(`handleWorkletMessage({type:'metrics',epoch:playbackEpoch,cumulativeConsumedFrames:500,playing:false})`,textSync);
  assert.equal(textSync.captureText.at(-1),'Xin ch','rebuffering must not advance text');
  vm.runInContext(`handleWorkletMessage({type:'metrics',epoch:playbackEpoch-1,cumulativeConsumedFrames:1000})`,textSync);
  assert.equal(textSync.captureText.at(-1),'Xin ch','ignore stale player clocks');
  vm.runInContext(`handleWorkletMessage({type:'drained',epoch:playbackEpoch})`,textSync);
  assert.equal(textSync.captureText.at(-1),'Xin chào bạn.');
  assert.equal(vm.runInContext(`friendlyError('<!DOCTYPE html><html>524</html>')`,textSync).includes('<html>'),false);
  results.push('text follows consumed audio frames, pauses with buffering and flushes final punctuation');

  let Worklet;
  const messages = [];
  const worklet = vm.createContext({sampleRate:1000, Float32Array, Uint8Array, ArrayBuffer, DataView,
    AudioWorkletProcessor: class {constructor(){this.port={postMessage:m=>messages.push(m)}}},
    registerProcessor(name, type){Worklet=type;},
  });
  vm.runInContext(fs.readFileSync(path.join(root,'pcm-player-worklet.js'),'utf8'),worklet);
  const player = new Worklet();
  player.port.onmessage({data:{type:'reset',epoch:2}});
  player.port.onmessage({data:{type:'end',epoch:1}});
  assert.equal(player.ended,false,'stale end must not truncate a new stream');
  player.port.onmessage({data:{type:'pcm',epoch:2,sequence:1,buffer:new Int16Array(1000).fill(4096).buffer}});
  player.port.onmessage({data:{type:'end',epoch:2}});
  let heard = 0;
  for(let i=0;i<12;i++){
    const out=new Float32Array(128);
    player.process([],[[out]]);
    heard += out.filter(v=>v!==0).length;
  }
  assert.equal(heard,1000,'all buffered audio must be consumed exactly once');
  assert.equal(player.underrunCount,0,'a complete buffered unit must not stutter internally');
  assert.equal(messages.filter(m=>m.type==='drained').length,1);
  results.push('actual PCM worklet: sample preservation, no interior starvation, stale end rejected');
  console.log(JSON.stringify({passed:results.length, checks:results},null,2));
}
main().catch(error=>{console.error(error);process.exit(1)});
