import { Tag, Popover } from 'antd';
import { FileTextOutlined, GlobalOutlined } from '@ant-design/icons';
import type { Source } from '../types';

interface Props {
  sources: Source[];
  onSourceClick?: (docId: number, snippet: string) => void;
}

function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function SourcePanel({ sources, onSourceClick }: Props) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid #e8e8e8', paddingTop: 8 }}>
      {sources.map((src, i) => {
        const isWeb = src.type === 'web';

        const tag = (
          <Tag
            icon={isWeb ? <GlobalOutlined /> : <FileTextOutlined />}
            color={isWeb ? 'green' : 'blue'}
            style={{ cursor: 'pointer', marginBottom: 4 }}
            onClick={() => {
              if (isWeb && src.url) {
                window.open(src.url, '_blank', 'noopener');
              } else if (!isWeb && src.doc_id != null) {
                onSourceClick?.(src.doc_id, src.snippet);
              }
            }}
          >
            [{i + 1}] {isWeb && src.url ? getDomain(src.url) : src.file}
            {!isWeb && src.page ? ` (p.${src.page})` : ''}
          </Tag>
        );

        return (
          <Popover
            key={i}
            content={
              <div style={{ maxWidth: 300, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                {src.snippet}
              </div>
            }
            title={isWeb ? '搜索结果' : '原文片段'}
            trigger="hover"
          >
            {tag}
          </Popover>
        );
      })}
    </div>
  );
}
