/**
 * LLM Client — OpenRouter with automatic fallback chain
 * Tries models in order. First success wins. All fail = throws.
 */

const FALLBACK_CHAIN = [
  'google/gemini-2.0-flash-001',     // Fast, cheap, good for content
  'deepseek/deepseek-chat-v3-0324',  // Cheap backup, solid quality
  'openai/gpt-4.1-mini',             // Reliable fallback
];

export async function callLLM(apiKey, prompt, { maxTokens = 4096, model = null } = {}) {
  const models = model ? [model] : FALLBACK_CHAIN;
  let lastError;

  for (const m of models) {
    console.log(`🤖 Trying model: ${m}`);
    try {
      const resp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://gab.ae',
          'X-Title': 'gab.ae',
        },
        body: JSON.stringify({
          model: m,
          max_tokens: maxTokens,
          messages: [{ role: 'user', content: prompt }],
        }),
        signal: AbortSignal.timeout(60000),
      });

      const data = await resp.json();

      if (data.error) {
        console.log(`⚠️ ${m} failed: ${JSON.stringify(data.error).slice(0, 200)}`);
        lastError = data.error;
        continue;
      }

      const text = data.choices?.[0]?.message?.content || '';
      if (!text) {
        console.log(`⚠️ ${m} returned empty response`);
        continue;
      }

      if (models.length > 1 && m !== models[0]) {
        console.log(`🔄 Fell back to ${m}`);
      }

      return text;
    } catch (e) {
      console.log(`⚠️ ${m} error: ${e.message}`);
      lastError = e;
      continue;
    }
  }

  throw new Error(`All models failed. Last error: ${JSON.stringify(lastError).slice(0, 300)}`);
}
