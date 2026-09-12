import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const code = ts.transpileModule(fs.readFileSync('src/lib/research.ts','utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText;
const compiled={exports:{}};
new Function('require','module','exports',code)(require,compiled,compiled.exports);
const connection={base:'http://127.0.0.1:8000',workspace:'personal',token:''};
const availabilityCode=ts.transpileModule(fs.readFileSync('src/lib/research-availability.ts','utf8'), {
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText;
for(const [env,expected] of [
 [{NODE_ENV:'production'},false],
 [{NODE_ENV:'development'},true],
 [{NODE_ENV:'production',NEXT_PUBLIC_RESEARCH_API_URL:'https://research.example.test'},true],
]){
 const availability={exports:{}};
 new Function('module','exports','process',availabilityCode)(availability,availability.exports,{env});
 assert.equal(availability.exports.researchEnabled,expected);
}
(async()=>{
 const original=global.fetch;
 try{
  for(const path of ['/analyses','/analyses/saved/runs','/ingestions']){
   const calls=[];
   global.fetch=async(url,options)=>{calls.push(options);if(calls.length===1)throw new TypeError('connection reset');return new Response('{}',{status:200});};
   await compiled.exports.request(connection,path,'POST',{value:1});
   assert.equal(calls.length,2);
   assert.ok(calls[0].headers['Idempotency-Key']);
   assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);
  }
  let count=0;
  global.fetch=async()=>{count++;throw new TypeError('connection reset');};
  await assert.rejects(()=>compiled.exports.request(connection,'/annotations','POST',{text:'note'}));
  assert.equal(count,1);
  count=0;
  global.fetch=async()=>{count++;return new Response('{"detail":"invalid recipe"}',{status:422});};
  await assert.rejects(()=>compiled.exports.request(connection,'/analyses','POST',{}),/invalid recipe/);
  assert.equal(count,1);
  console.log('Research client: 5 retry/idempotency and 3 deployment availability checks passed');
 }finally{global.fetch=original;}
})().catch(error=>{console.error(error);process.exitCode=1;});
