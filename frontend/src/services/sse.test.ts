import { expect, it, vi } from 'vitest';
import { consumeSSEStream } from './sse';

it('delivers sources received immediately before done', async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(
        'event: sources\ndata: {"schema_version":1,"sources":[{"file":"a.pdf","page":1,"snippet":"证据","doc_id":9}]}\n\n' +
        'event: done\ndata: {"schema_version":1,"conversation_id":4}\n\n',
      ));
      controller.close();
    },
  });
  const onDone = vi.fn();

  await consumeSSEStream(stream.getReader(), { onDone });

  expect(onDone).toHaveBeenCalledWith(
    { schema_version: 1, conversation_id: 4 },
    [{ file: 'a.pdf', page: 1, snippet: '证据', doc_id: 9 }],
  );
});
