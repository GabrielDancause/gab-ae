import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { callLLM } from '../llm-client.js';

const FALLBACK_CHAIN = [
  'google/gemini-2.0-flash-001',
  'deepseek/deepseek-chat-v3-0324',
  'openai/gpt-4.1-mini',
];

function makeOkResponse(text) {
  return {
    ok: true,
    json: async () => ({ choices: [{ message: { content: text } }] }),
  };
}

function makeErrorResponse(errorObj) {
  return {
    ok: false,
    json: async () => ({ error: errorObj }),
  };
}

function makeEmptyContentResponse() {
  return {
    ok: true,
    json: async () => ({ choices: [{ message: { content: '' } }] }),
  };
}

describe('callLLM()', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns text from the first model on success', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('Hello world'));
    const result = await callLLM('test-key', 'Say hello');
    expect(result).toBe('Hello world');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('calls the OpenRouter endpoint', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('my-api-key', 'prompt');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://openrouter.ai/api/v1/chat/completions',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('sends the Authorization header with the API key', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('secret-key-123', 'prompt');
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer secret-key-123');
  });

  it('sends the prompt in request body as a user message', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('key', 'my prompt text');
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.messages).toEqual([{ role: 'user', content: 'my prompt text' }]);
  });

  it('respects custom maxTokens option', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('key', 'prompt', { maxTokens: 1024 });
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.max_tokens).toBe(1024);
  });

  it('defaults to 4096 max tokens', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('key', 'prompt');
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.max_tokens).toBe(4096);
  });

  it('uses the specified model when model option is given', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('key', 'prompt', { model: 'openai/gpt-4o' });
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.model).toBe('openai/gpt-4o');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls back to second model when first returns an error response', async () => {
    fetchMock
      .mockResolvedValueOnce(makeErrorResponse({ message: 'quota exceeded' }))
      .mockResolvedValueOnce(makeOkResponse('Fallback response'));
    const result = await callLLM('key', 'prompt');
    expect(result).toBe('Fallback response');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const secondBody = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(secondBody.model).toBe(FALLBACK_CHAIN[1]);
  });

  it('falls back to third model when first two fail', async () => {
    fetchMock
      .mockResolvedValueOnce(makeErrorResponse({ message: 'err1' }))
      .mockResolvedValueOnce(makeErrorResponse({ message: 'err2' }))
      .mockResolvedValueOnce(makeOkResponse('Third model response'));
    const result = await callLLM('key', 'prompt');
    expect(result).toBe('Third model response');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('throws when all models fail with error responses', async () => {
    fetchMock
      .mockResolvedValueOnce(makeErrorResponse({ message: 'err1' }))
      .mockResolvedValueOnce(makeErrorResponse({ message: 'err2' }))
      .mockResolvedValueOnce(makeErrorResponse({ message: 'err3' }));
    await expect(callLLM('key', 'prompt')).rejects.toThrow(/All models failed/);
  });

  it('falls back when a model returns empty content', async () => {
    fetchMock
      .mockResolvedValueOnce(makeEmptyContentResponse())
      .mockResolvedValueOnce(makeOkResponse('Non-empty response'));
    const result = await callLLM('key', 'prompt');
    expect(result).toBe('Non-empty response');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('throws when all models return empty content', async () => {
    fetchMock
      .mockResolvedValue(makeEmptyContentResponse());
    await expect(callLLM('key', 'prompt')).rejects.toThrow(/All models failed/);
  });

  it('falls back when fetch throws a network error', async () => {
    fetchMock
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce(makeOkResponse('Recovered'));
    const result = await callLLM('key', 'prompt');
    expect(result).toBe('Recovered');
  });

  it('throws when all models throw network errors', async () => {
    fetchMock.mockRejectedValue(new Error('Network error'));
    await expect(callLLM('key', 'prompt')).rejects.toThrow(/All models failed/);
  });

  it('does not fall back when a specific model is provided and it fails', async () => {
    fetchMock.mockResolvedValueOnce(makeErrorResponse({ message: 'err' }));
    await expect(callLLM('key', 'prompt', { model: 'openai/gpt-4o' })).rejects.toThrow(/All models failed/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uses the first model of the fallback chain by default', async () => {
    fetchMock.mockResolvedValueOnce(makeOkResponse('OK'));
    await callLLM('key', 'prompt');
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.model).toBe(FALLBACK_CHAIN[0]);
  });
});
