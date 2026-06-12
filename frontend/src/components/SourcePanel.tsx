import { Tag, Popover } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import type { Source } from '../types';

interface Props {
  sources: Source[];
  onSourceClick?: (docId: number, snippet: string) => void;
}

export default function SourcePanel({ sources, onSourceClick }: Props) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid #e8e8e8', paddingTop: 8 }}>
      {sources.map((src, i) => (
        <Popover
          key={i}
          content={
            <div style={{ maxWidth: 300, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
              {src.snippet}
            </div>
          }
          title="原文片段"
          trigger="hover"
        >
          <Tag
            icon={<FileTextOutlined />}
            color="blue"
            style={{ cursor: 'pointer', marginBottom: 4 }}
            onClick={() => onSourceClick?.(src.doc_id, src.snippet)}
          >
            [{i + 1}] {src.file}
            {src.page ? ` (p.${src.page})` : ''}
          </Tag>
        </Popover>
      ))}
    </div>
  );
}
