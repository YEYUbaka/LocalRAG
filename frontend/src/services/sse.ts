import type { Source } from '../types';

interface SSECallbacks {
  onToken?: (content: string) => void;
  onSources?: (sources: Source[]) => void;
  onDone?: (data: { conversation_id: number }) => void;
  onError?: (error: string) => void;
  onThinking?: (status: string, message: string) => void;
}

export function streamChat(
  question: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
  thinkingMode: boolean = false,
): EventSource {
  const params = new URLSearchParams();
  // We use fetch with ReadableStream for POST SSE since EventSource only supports GET
  const controller = new AbortController();

  const token = localStorage.getItem('token');
  fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      kb_id: kbId,
      thinking_mode: thinkingMode,
    }),
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

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (eventType === 'token') {
                callbacks.onToken?.(parsed.content);
              } else if (eventType === 'sources') {
                callbacks.onSources?.(parsed.sources);
              } else if (eventType === 'done') {
                callbacks.onDone?.(parsed);
              } else if (eventType === 'error') {
                callbacks.onError?.(parsed.message || '发生未知错误');
              } else if (eventType === 'thinking') {
                callbacks.onThinking?.(parsed.status, parsed.message);
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message);
      }
    });

  // Return a dummy EventSource-like object for compatibility
  return {
    close: () => controller.abort(),
  } as unknown as EventSource;
}


export function streamImageAnalysis(
  question: string,
  imageBase64: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
): EventSource {
  const controller = new AbortController();
  const token = localStorage.getItem('token');

  fetch('/api/chat/image', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      image_base64: imageBase64,
      conversation_id: conversationId,
      kb_id: kbId,
    }),
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

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (eventType === 'token') {
                callbacks.onToken?.(parsed.content);
              } else if (eventType === 'sources') {
                callbacks.onSources?.(parsed.sources);
              } else if (eventType === 'done') {
                callbacks.onDone?.(parsed);
              } else if (eventType === 'error') {
                callbacks.onError?.(parsed.message || '发生未知错误');
              } else if (eventType === 'thinking') {
                callbacks.onThinking?.(parsed.status, parsed.message);
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message);
      }
    });

  return {
    close: () => controller.abort(),
  } as unknown as EventSource;
}
