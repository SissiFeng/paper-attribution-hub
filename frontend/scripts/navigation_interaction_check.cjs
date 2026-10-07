const assert=require('node:assert/strict');
const path=require('node:path');
const {buildSync}=require('esbuild');
const result=buildSync({entryPoints:[path.resolve(__dirname,'../src/components/navigation.ts')],bundle:true,write:false,platform:'node',format:'cjs'});
const output={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,output,output.exports);
const {navigationItems,navigationActive,findNavigation,navigationShortcut}=output.exports;
const member=navigationItems(false),admin=navigationItems(true);
assert.equal(new Set(admin.map(i=>i.to)).size,admin.length);
assert.ok(!member.some(i=>i.label==='Manage access'));
assert.ok(member.some(i=>i.to==='/institution-comparison'&&i.access==='admin'));
assert.deepEqual(findNavigation(member,'机构').map(i=>i.to),['/institution-comparison']);
assert.deepEqual(findNavigation(member,'INSTITUTION').map(i=>i.to),['/institution-comparison']);
assert.deepEqual(findNavigation(member,'project method').map(i=>i.to),['/research']);
assert.deepEqual(findNavigation(member,'  '),member);
assert.deepEqual(findNavigation(member,'['),[]);
assert.deepEqual(findNavigation(member,'<script>'),[]);
for(const [isAdmin,path,search,wanted] of [
  [false,'/','','/papers'],[true,'/','','/attribution'],[false,'/papers/P1','','/papers'],
  [true,'/research','?manage=members','/research?manage=members'],[false,'/research','?manage=members','/research'],
  [true,'/research','?project=123','/research'],[true,'/transfer-studio','','/transfer-studio'],
  [true,'/geographic/country/CA','','/geographic'],
])assert.deepEqual(navigationItems(isAdmin).filter(i=>navigationActive(i,path,search,isAdmin)).map(i=>i.to),[wanted]);
const key={key:'k',metaKey:false,ctrlKey:true,altKey:false,shiftKey:false,isComposing:false,repeat:false};
assert.equal(navigationShortcut(key),true);
assert.equal(navigationShortcut({...key,key:'K',metaKey:true,ctrlKey:false}),true);
for(const patch of [{ctrlKey:false},{altKey:true},{shiftKey:true},{isComposing:true},{repeat:true},{key:'x'}])assert.equal(navigationShortcut({...key,...patch}),false);
console.log('Navigation interactions: literal English/Chinese search, unique active destinations, role visibility and keyboard guards passed');
