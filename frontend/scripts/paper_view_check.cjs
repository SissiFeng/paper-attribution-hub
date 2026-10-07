const assert = require('node:assert/strict');
const path = require('node:path');
const { buildSync } = require('esbuild');
const root = path.resolve(__dirname, '..');
const result = buildSync({absWorkingDir: root, bundle: true, write: false, outfile: 'paper-view-check.js',
  platform: 'node', format: 'cjs', jsx: 'automatic', loader: {'.css':'empty'},
  define: {'import.meta.env':'{}','process.env.NODE_ENV':'"production"'},
  stdin: {resolveDir:root, loader:'tsx', contents:`
    import {renderToStaticMarkup} from 'react-dom/server';
    import {StaticRouter} from 'react-router-dom/server';
    import {EvidencePanel} from './src/components/EvidencePanel';
    import {WikiPanel} from './src/components/WikiPanel';
    import {PaperCatalogue} from './src/pages/PaperPage';
    const paper={id:'P1',title:'Published paper',authors:[],provenance:'openalex',full_text_available:false,
      abstract:'Public abstract',review:{human_label:'INCLUDE',reviewer:'PRIVATE-REVIEWER',notes:'PRIVATE-NOTE'}};
    export const shared=renderToStaticMarkup(<EvidencePanel paper={paper} readOnly/>);
    export const admin=renderToStaticMarkup(<EvidencePanel paper={paper}/>);
    export const wiki=renderToStaticMarkup(<WikiPanel paperId="P1" readOnly/>);
    export const catalogue=renderToStaticMarkup(<StaticRouter location="/papers"><PaperCatalogue/></StaticRouter>);
  `}});
const output={exports:{}};
new Function('require','module','exports',result.outputFiles[0].text)(require,output,output.exports);
const {shared,admin,wiki,catalogue}=output.exports;
assert.match(shared,/Public abstract/);
assert.match(shared,/Wiki/);
assert.doesNotMatch(shared,/Human decision|PRIVATE-REVIEWER|PRIVATE-NOTE|placeholder="notes"/);
assert.match(admin,/Human decision/);
assert.match(admin,/PRIVATE-NOTE/);
assert.doesNotMatch(wiki,/Verify freshness|Compiling|Refresh/);
assert.match(catalogue,/Shared evidence filters/);
assert.match(catalogue,/Classification labels/);
assert.doesNotMatch(catalogue,/Human review|Advanced evidence scope|SDL and AC analysis scope/);
console.log('Shared original paper UI: filters, Wiki, hidden review fields and preserved admin controls passed');
