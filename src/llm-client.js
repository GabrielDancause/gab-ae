/**
 * LLM Client — OpenRouter-powered (model-agnostic)
 * Drop-in replacement for direct Anthropic API calls.
 * Uses OpenRouter to route to any model. Default: Gemini 2.0 Flash.
 */

const DEFAULT_MODEL = 'google/gemini-2.0-flash-001';

export async function callLLM(apiKey, prompt, { maxTokens = 4096, model = DEFAULT_MODEL } = {}) {
  const resp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://gab.ae',
      'X-Title': 'gab.ae',
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(`LLM error: ${JSON.stringify(data.error)}`);
  return data.choices?.[0]?.message?.content || '';
}
