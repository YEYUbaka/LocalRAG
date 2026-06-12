import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Spin, Typography } from 'antd';
import { CloseOutlined, FileTextOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { DocumentContent } from '../types';
import { getDocumentContent } from '../services/api';

const { Text } = Typography;

interface Props {
  docId: number;
  highlightSnippet?: string;
  onClose: () => void;
}

export default function DocumentPreviewPanel({ docId, highlightSnippet, onClose }: Props) {
  const [content, setContent] = useState<DocumentContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadContent = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDocumentContent(docId);
      setContent(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadContent();
  }, [loadContent]);

  // Highlight and scroll after content loads
  useEffect(() => {
    if (!content || !highlightSnippet || !containerRef.current) return;

    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      const searchStr = highlightSnippet.length > 50 ? highlightSnippet.slice(0, 50) : highlightSnippet;

      // Walk all text nodes and find the one containing the search string
      const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      while (walk.nextNode()) {
        const node = walk.currentNode as Text;
        const nodeText = node.textContent || '';
        const idx = nodeText.indexOf(searchStr);
        if (idx === -1) continue;

        // Found — use extractContents/insertNode (safe across node boundaries)
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + searchStr.length);

        const mark = document.createElement('mark');
        mark.style.backgroundColor = '#fff3b0';
        mark.style.transition = 'background-color 2s ease';

        const frag = range.extractContents();
        mark.appendChild(frag);
        range.insertNode(mark);
        mark.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
          mark.style.backgroundColor = 'transparent';
        }, 3000);
        break;
      }
    }, 100);

    return () => clearTimeout(timer);
  }, [content, highlightSnippet]);

  // Build display content with page breaks for PDFs
  const buildDisplayContent = (): string => {
    if (!content) return '';
    if (!content.page_breaks || content.page_breaks.length <= 1) {
      return content.parsed_content || '';
    }

    const text = content.parsed_content || '';
    const parts: string[] = [];
    content.page_breaks.forEach((offset, i) => {
      const end = i + 1 < content.page_breaks!.length ? content.page_breaks![i + 1] : text.length;
      parts.push(`\n\n--- **第 ${i + 1} 页** ---\n\n`);
      parts.push(text.slice(offset, end));
    });
    return parts.join('');
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'center', alignItems: 'center' }}>
        <Spin tip="加载文档内容..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        <Text type="danger">{error}</Text>
        <Button style={{ marginTop: 16 }} onClick={loadContent}>重试</Button>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '8px 12px',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <FileTextOutlined />
          <Text strong ellipsis style={{ maxWidth: 200 }}>{content.filename}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{content.chunk_count} chunks</Text>
        </div>
        <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} />
      </div>

      {/* Content */}
      <div ref={containerRef} style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {!content.parsed_content ? (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            <p>该文档在功能上线前处理，无法预览。</p>
            <p>请重新上传以启用预览。</p>
          </div>
        ) : content.parsed_content.trim() === '' ? (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            文档无可提取内容
          </div>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{buildDisplayContent()}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
