import { useState, useRef, useEffect } from 'react';
import { Input, Button, message, Spin } from 'antd';
import { SendOutlined, PlusOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Message, Source, Conversation } from '../types';
import { getConversation } from '../services/api';
import { streamChat } from '../services/sse';
import SourcePanel from './SourcePanel';
import DocumentPreviewPanel from './DocumentPreviewPanel';

interface Props {
  conversationId: number | null;
  onNewConversation: (id: number) => void;
  previewDocId: number | null;
  onPreviewDocChange: (docId: number | null, snippet?: string) => void;
}

export default function ChatPanel({ conversationId, onNewConversation, previewDocId, onPreviewDocChange }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [pendingSources, setPendingSources] = useState<Source[] | null>(null);
  const [highlightSnippet, setHighlightSnippet] = useState<string | undefined>();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleSourceClick = (docId: number, snippet: string) => {
    setHighlightSnippet(snippet);
    onPreviewDocChange(docId, snippet);
  };

  const MarkdownComponents = {
    code({ node, inline, className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className || '');
      return !inline && match ? (
        <SyntaxHighlighter
          style={oneDark}
          language={match[1]}
          PreTag="div"
          {...props}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
  };

  useEffect(() => {
    if (conversationId) {
      getConversation(conversationId).then((conv) => {
        setMessages(conv.messages || []);
      });
    } else {
      setMessages([]);
    }
  }, [conversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput('');
    setLoading(true);
    setStreamingContent('');
    setPendingSources(null);

    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: question,
      sources: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    let fullContent = '';
    let convId = conversationId;

    streamChat(question, conversationId, {
      onToken: (content) => {
        fullContent += content;
        setStreamingContent(fullContent);
      },
      onSources: (sources) => {
        setPendingSources(sources);
      },
      onDone: (data) => {
        const assistantMsg: Message = {
          id: Date.now() + 1,
          role: 'assistant',
          content: fullContent,
          sources: pendingSources,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamingContent('');
        setPendingSources(null);
        setLoading(false);

        if (!conversationId && data.conversation_id) {
          onNewConversation(data.conversation_id);
        }
      },
      onError: (error) => {
        message.error(error);
        setLoading(false);
        setStreamingContent('');
      },
    });
  };

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          {messages.length === 0 && !streamingContent && (
            <div style={{ textAlign: 'center', color: '#999', marginTop: 100 }}>
              <h2>LocalRAG 个人知识库</h2>
              <p>上传文档后，在这里提问</p>
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                marginBottom: 16,
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  maxWidth: '80%',
                  padding: '10px 14px',
                  borderRadius: 12,
                  background: msg.role === 'user' ? '#1677ff' : '#f5f5f5',
                  color: msg.role === 'user' ? '#fff' : '#333',
                }}
              >
                {msg.role === 'assistant' ? (
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  msg.content
                )}
                {msg.sources && msg.sources.length > 0 && (
                  <SourcePanel sources={msg.sources} onSourceClick={handleSourceClick} />
                )}
              </div>
            </div>
          ))}
          {streamingContent && (
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-start' }}>
              <div
                style={{
                  maxWidth: '80%',
                  padding: '10px 14px',
                  borderRadius: 12,
                  background: '#f5f5f5',
                }}
              >
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{streamingContent}</ReactMarkdown>
                </div>
                {pendingSources && pendingSources.length > 0 && (
                  <SourcePanel sources={pendingSources} onSourceClick={handleSourceClick} />
                )}
              </div>
            </div>
          )}
          {loading && !streamingContent && (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin tip="思考中..." />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ padding: 16, borderTop: '1px solid #f0f0f0', display: 'flex', gap: 8 }}>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="输入问题... (Shift+Enter 换行)"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            style={{ height: 'auto' }}
          />
        </div>
      </div>

      {/* Preview panel */}
      {previewDocId && (
        <div
          style={{
            width: '40%',
            borderLeft: '1px solid #f0f0f0',
            flexShrink: 0,
          }}
        >
          <DocumentPreviewPanel
            docId={previewDocId}
            highlightSnippet={highlightSnippet}
            onClose={() => {
              setHighlightSnippet(undefined);
              onPreviewDocChange(null);
            }}
          />
        </div>
      )}
    </div>
  );
}
