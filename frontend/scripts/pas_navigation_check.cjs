// Regression: adding a reader workspace must not remove the existing PAS UI.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildSync } = require('esbuild');
const root = path.resolve(__dirname, '..');
const originalPages = [
  ['/multi-graph/embed', 'MultiGraphEmbed'], ['/papers/:paperId/evidence-map', 'EvidenceMapPage'],
  ['/queue', 'ReviewQueuePage'], ['/insights', 'InsightsPage'], ['/pipeline', 'PipelineStatusPage'],
  ['/evidence-gaps', 'EvidenceGapsPage'], ['/lint', 'LintReportPage'], ['/duplicates', 'DuplicateCandidatesPage'],
  ['/discovery', 'DiscoveryPage'], ['/report', 'ReportPage'], ['/eval', 'EvalPage'],
  ['/sankey', 'SankeyPage'], ['/timeline', 'TimelinePage'], ['/network', 'CoauthorNetworkPage'],
  ['/network-v1', 'NetworkPage'], ['/impact', 'ImpactPage'], ['/drift', 'DriftPage'],
  ['/transfer', 'KnowledgeTransferPage'], ['/transfer-studio', 'TransferStudioPage'], ['/kb', 'KnowledgeBasePage'],
  ['/labs/:labId', 'LabProfilePage'], ['/people', 'PeopleGridPage'], ['/multi-graph', 'MultiGraphPage'],
  ['/geographic', 'GeographicPage'], ['/growth', 'NetworkGrowthPage'], ['/retrieval', 'RetrievalPage'],
  ['/institution-comparison', 'InstitutionAuthorshipPage'], ['/geographic/country/:countryCode', 'GeographicCountryPage'],
  ['/attribution', 'PaperReviewPage'],
];
const main = fs.readFileSync(path.join(root, 'src/main.tsx'), 'utf8');
for (const [route, component] of originalPages) {
  assert.ok(main.includes(`path="${route}" element={<${component} />}`), `Missing original page: ${route} → ${component}`);
  assert.ok(fs.existsSync(path.join(root, `src/pages/${component}.tsx`)), `Missing source: ${component}`);
}
assert.match(main, /path="\/" element={<PapersHome \/>}/);
assert.match(main, /user\?\.role==='admin' \? <PaperReviewPage\/>/);

// Render with no account: the full navigation must remain discoverable before login.
const result = buildSync({ absWorkingDir: root, bundle: true, write: false, outfile: 'navigation-check.js', platform: 'node', format: 'cjs',
  jsx: 'automatic', loader: { '.css': 'empty' }, define: { 'import.meta.env': '{}', 'process.env.NODE_ENV': '"production"' },
  stdin: { contents: `import {renderToStaticMarkup} from 'react-dom/server';
    import {StaticRouter} from 'react-router-dom/server'; import {Sidebar} from './src/components/Sidebar';
    export const html=renderToStaticMarkup(<StaticRouter location="/"><Sidebar/></StaticRouter>);`,
    resolveDir: root, loader: 'tsx' },
});
const output = { exports: {} };
new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, output, output.exports);
const html = output.exports.html;
for (const [route] of originalPages.filter(([route]) => !route.includes(':') && !['/multi-graph/embed','/network-v1'].includes(route))) {
  assert.ok(html.includes(`href="${route}"`), `Page hidden from anonymous navigation: ${route}`);
}
for (const route of ['/papers', '/research']) assert.ok(html.includes(`href="${route}"`));
assert.ok(html.includes('Institution Compare — Administrator access'));
assert.ok(!html.includes('Admin analytics'), 'Do not collapse all PAS pages into a single link');
assert.ok(html.includes('aria-controls="pas-navigation"'), 'Small screens need an expandable menu');
console.log(`PAS preservation: ${originalPages.length} original page components, admin home and complete anonymous navigation verified`);
