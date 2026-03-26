/**
 * Calculator Engine
 * 
 * Config shape:
 * {
 *   inputs: [{ id, label, type, prefix, suffix, default, min, max, step, options }],
 *   outputs: [{ id, label, format }],  // format: number, currency, percent, text
 *   formula: "tip = bill * tipPct / 100; total = bill + tip; perPerson = total / people",
 *   presets: { inputId: [10, 15, 18, 20, 25] },  // optional preset buttons
 *   verdicts: [{ max: 70, label: "Easy", color: "green" }, ...],  // optional verdict based on output
 *   verdictOutput: "outputId",  // which output drives the verdict
 * }
 */
export function renderCalculator(page) {
  const config = JSON.parse(page.config);
  const content = page.content ? JSON.parse(page.content) : [];
  const faqs = page.faqs ? JSON.parse(page.faqs) : [];
  
  const inputsHtml = config.inputs.map(inp => {
    if (inp.type === 'preset') {
      const buttons = (inp.options || []).map(opt => 
        `<button type="button" class="preset-btn px-4 py-2 rounded-lg border border-surface-border text-sm font-medium hover:bg-accent hover:text-white hover:border-accent transition-all" data-input="${inp.id}" data-value="${opt}">${opt}${inp.suffix || '%'}</button>`
      ).join('\n              ');
      
      return `
          <div class="space-y-2">
            <label class="block text-sm font-medium text-gray-300">${esc(inp.label)}</label>
            <div class="flex flex-wrap gap-2">
              ${buttons}
            </div>
            <input type="number" id="${inp.id}" value="${inp.default || ''}" 
              class="w-full px-4 py-3 bg-surface border border-surface-border rounded-lg text-white text-lg focus:border-accent focus:outline-none transition-colors"
              placeholder="Custom ${inp.label.toLowerCase()}"
              ${inp.min !== undefined ? `min="${inp.min}"` : ''} ${inp.max !== undefined ? `max="${inp.max}"` : ''} ${inp.step ? `step="${inp.step}"` : ''}>
          </div>`;
    }
    
    const prefix = inp.prefix ? `<span class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">${inp.prefix}</span>` : '';
    const suffix = inp.suffix ? `<span class="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400">${inp.suffix}</span>` : '';
    const padLeft = inp.prefix ? 'pl-8' : 'pl-4';
    const padRight = inp.suffix ? 'pr-12' : 'pr-4';
    
    return `
          <div class="space-y-2">
            <label for="${inp.id}" class="block text-sm font-medium text-gray-300">${esc(inp.label)}</label>
            <div class="relative">
              ${prefix}
              <input type="number" id="${inp.id}" value="${inp.default || ''}"
                class="w-full ${padLeft} ${padRight} py-3 bg-surface border border-surface-border rounded-lg text-white text-lg focus:border-accent focus:outline-none transition-colors"
                placeholder="${esc(inp.label)}"
                ${inp.min !== undefined ? `min="${inp.min}"` : ''} ${inp.max !== undefined ? `max="${inp.max}"` : ''} ${inp.step ? `step="${inp.step}"` : ''}>
              ${suffix}
            </div>
          </div>`;
  }).join('');

  const outputsHtml = config.outputs.map(out => `
        <div class="text-center p-4 bg-surface rounded-lg border border-surface-border">
          <div class="text-sm text-gray-400 mb-1">${esc(out.label)}</div>
          <div id="out-${out.id}" class="text-3xl font-bold text-white">—</div>
        </div>`).join('');

  const verdictHtml = config.verdicts ? `
        <div id="verdict" class="text-center py-3 px-6 rounded-lg text-lg font-semibold hidden"></div>` : '';

  const sectionsHtml = content.map(section => `
      <div class="bg-surface-card border border-surface-border rounded-xl p-6 md:p-8">
        <h2 class="text-xl font-semibold text-white mb-4">${esc(section.heading)}</h2>
        <div class="text-gray-300 leading-relaxed space-y-3">${section.body}</div>
      </div>`).join('');

  const faqsHtml = faqs.length ? `
      <div class="bg-surface-card border border-surface-border rounded-xl p-6 md:p-8">
        <h2 class="text-xl font-semibold text-white mb-4">Frequently Asked Questions</h2>
        <div class="space-y-3">
          ${faqs.map(faq => `
          <details class="group border border-surface-border rounded-lg">
            <summary class="flex justify-between items-center cursor-pointer px-4 py-3 text-gray-200 font-medium hover:text-white transition-colors">
              ${esc(faq.q)}
              <svg class="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </summary>
            <div class="px-4 pb-4 text-gray-400 leading-relaxed">${esc(faq.a)}</div>
          </details>`).join('')}
        </div>
      </div>` : '';

  const formulaStr = JSON.stringify(config.formula);
  const outputIds = JSON.stringify(config.outputs.map(o => ({ id: o.id, format: o.format })));
  const inputIds = JSON.stringify(config.inputs.map(i => i.id));
  const verdictsStr = config.verdicts ? JSON.stringify(config.verdicts) : 'null';
  const verdictOutput = config.verdictOutput ? `"${config.verdictOutput}"` : 'null';

  const body = `
    <!-- Tool Card -->
    <div class="bg-surface-card border border-surface-border rounded-xl p-6 md:p-8 mb-12">
      <h1 class="text-2xl md:text-3xl font-bold text-white mb-2">${esc(page.title)}</h1>
      <p class="text-gray-400 mb-8">${esc(page.description)}</p>
      
      <!-- Inputs -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        ${inputsHtml}
      </div>

      <!-- Outputs -->
      <div class="grid grid-cols-1 md:grid-cols-${Math.min(config.outputs.length, 3)} gap-4 mb-4">
        ${outputsHtml}
      </div>

      ${verdictHtml}
    </div>

    <!-- Content Sections -->
    <div class="max-w-3xl mx-auto space-y-8">
      ${sectionsHtml}
      ${faqsHtml}
    </div>

    <script>
    (function() {
      const inputs = ${inputIds};
      const outputs = ${outputIds};
      const verdicts = ${verdictsStr};
      const verdictOutput = ${verdictOutput};

      function getValues() {
        const vals = {};
        inputs.forEach(id => {
          vals[id] = parseFloat(document.getElementById(id)?.value) || 0;
        });
        return vals;
      }

      function calculate() {
        const vals = getValues();
        try {
          const fn = new Function(...inputs, ${formulaStr});
          // Actually eval the formula as statements
          const results = {};
          const code = ${formulaStr};
          // Build function body that returns all outputs
          const body = code + '; return {' + outputs.map(o => o.id).join(',') + '};';
          const calcFn = new Function(...inputs, body);
          const result = calcFn(...inputs.map(id => vals[id]));
          
          outputs.forEach(o => {
            const el = document.getElementById('out-' + o.id);
            if (!el) return;
            const val = result[o.id];
            if (val === undefined || isNaN(val)) { el.textContent = '—'; return; }
            
            if (o.format === 'currency') el.textContent = '$' + val.toFixed(2);
            else if (o.format === 'percent') el.textContent = val.toFixed(1) + '%';
            else if (o.format === 'integer') el.textContent = Math.round(val).toLocaleString();
            else el.textContent = val.toFixed(2);
          });

          // Verdict
          if (verdicts && verdictOutput) {
            const verdictEl = document.getElementById('verdict');
            const val = result[verdictOutput];
            if (verdictEl && val !== undefined && !isNaN(val)) {
              let matched = verdicts[verdicts.length - 1];
              for (const v of verdicts) {
                if (val <= v.max) { matched = v; break; }
              }
              verdictEl.textContent = matched.label;
              verdictEl.className = 'text-center py-3 px-6 rounded-lg text-lg font-semibold';
              const colors = { green: 'bg-green-500/20 text-green-400', yellow: 'bg-yellow-500/20 text-yellow-400', orange: 'bg-orange-500/20 text-orange-400', red: 'bg-red-500/20 text-red-400', blue: 'bg-blue-500/20 text-blue-400' };
              verdictEl.classList.add(...(colors[matched.color] || colors.blue).split(' '));
            }
          }
        } catch(e) { console.error('Calc error:', e); }
      }

      // Bind events
      inputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', calculate);
      });

      // Preset buttons
      document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const input = document.getElementById(this.dataset.input);
          if (input) { input.value = this.dataset.value; calculate(); }
          // Highlight active preset
          this.parentElement.querySelectorAll('.preset-btn').forEach(b => {
            b.classList.remove('bg-accent', 'text-white', 'border-accent');
          });
          this.classList.add('bg-accent', 'text-white', 'border-accent');
        });
      });

      // Initial calculation
      calculate();
    })();
    </script>`;

  return body;
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
