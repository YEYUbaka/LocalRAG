import type { Source, SSEDoneV1 } from '../types';

export interface SSECallbacks {
  onToken?: (content: string) => void;
  onSources?: (sources: Source[]) => void;
  onDone?: (data: SSEDoneV1, sources: Source[]) => void;
  onError?: (error: string) => void;
  onThinking?: (status: string, message: string) => void;
}

export async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: SSECallbacks,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let latestSources: Source[] = [];
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const lines = frame.split('\n');
      const eventType = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
      const data = lines.find((line) => line.startsWith('data:'))?.slice(5).trim();
      if (!eventType || !data) continue;
      const parsed: unknown = JSON.parse(data);
      if (eventType === 'token') callbacks.onToken?.((parsed as { content: string }).content);
      if (eventType === 'sources') {
        latestSources = (parsed as { sources: Source[] }).sources;
        callbacks.onSources?.(latestSources);
      }
      if (eventType === 'done') callbacks.onDone?.(parsed as SSEDoneV1, latestSources);
      if (eventType === 'error') callbacks.onError?.((parsed as { message: string }).message);
      if (eventType === 'thinking') {
        const thinking = parsed as { status: string; message: string };
        callbacks.onThinking?.(thinking.status, thinking.message);
      }
    }
    if (done) break;
  }
}

function streamChatImpl(
  url: string,
  body: Record<string, unknown>,
  callbacks: SSECallbacks,
): EventSource {
  const controller = new AbortController();
  const token = localStorage.getItem('token');

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        callbacks.onError?.(err.detail || '请求失败');
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) return;

      await consumeSSEStream(reader, callbacks);
    })
    .catch((err: unknown) => {
      if (err instanceof Error && err.name !== 'AbortError') {
        callbacks.onError?.(err.message);
      }
    });

  return {
    close: () => controller.abort(),
  } as unknown as EventSource;
}

export function streamChat(
  question: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
  thinkingMode: boolean = false,
): EventSource {
  return streamChatImpl('/api/chat', {
    question,
    conversation_id: conversationId,
    kb_id: kbId,
    thinking_mode: thinkingMode,
  }, callbacks);
}

export function streamImageAnalysis(
  question: string,
  imageBase64: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
): EventSource {
  return streamChatImpl('/api/chat/image', {
    question,
    image_base64: imageBase64,
    conversation_id: conversationId,
    kb_id: kbId,
  }, callbacks);
}
