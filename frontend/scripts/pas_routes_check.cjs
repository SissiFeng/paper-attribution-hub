const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.resolve(__dirname,'../../tools/author-paper-monitor/deploy/access/routing.js'),'utf8');
const context={};vm.createContext(context);vm.runInContext(script,context);
function route(uri){return context.handler({request:{uri,querystring:{doi:{value:'10.1234/a'}}}});}
for(const uri of ['/', '/papers', '/papers/DOI%3A10.1234_test', '/papers/monitor_123', '/research', '/institution-comparison']){
  assert.equal(route(uri).uri,'/index.html');
  assert.equal(route(uri).querystring.doi.value,'10.1234/a');
}
for(const uri of ['/assets/index-abc.js','/assets/index-abc.css','/reading/assets/reading-abc.js'])assert.equal(route(uri).uri,uri);
for(const uri of ['/data/private.json','/report.html','/assets/private.json'])assert.equal(route(uri).headers.location.value,'/api/access/files'+uri);
assert.equal(route('/protected-legacy/index.html').statusCode,404);
assert.equal(route('/reading/').uri,'/reading/index.html');
console.log('PAS routing: paper IDs, query preservation, UI assets and protected data checks passed');
