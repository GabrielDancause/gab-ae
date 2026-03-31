const fs = require('fs');
const path = require('path');

const fileContent = fs.readFileSync(path.join(__dirname, 'src', 'seed-pages.js'), 'utf-8');
const withoutExport = fileContent.replace('export async function seedPages(env) {', 'async function seedPages(env) {');

const mockKw = {
  primary_keyword: 'how to build credit',
  secondary_keywords: '["credit score", "credit cards"]',
  total_volume: 15000,
  target_site: 'westmount',
  page_type: 'educational'
};

const scriptCode = `
${withoutExport}
const kw = ${JSON.stringify(mockKw)};
console.log('Educational output length:', generateEducational(kw).length);
console.log('Sample Educational snippet:\\n', generateEducational(kw).substring(3000, 3500));
console.log('Comparison output length:', generateComparison(kw).length);
console.log('Sample Comparison snippet:\\n', generateComparison(kw).substring(3000, 3500));
`;

eval(scriptCode);
