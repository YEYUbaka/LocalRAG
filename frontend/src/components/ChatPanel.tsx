import { useState, useRef, useEffect } from 'react';
import { Input, Button, message, Spin, Tooltip, Upload } from 'antd';
import { SendOutlined, PlusOutlined, BulbOutlined, PictureOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Message, Source, Conversation } from '../types';
import { getConversation } from '../services/api';
import { streamChat, streamImageAnalysis } from '../services/sse';
import SourcePanel from './SourcePanel';
import DocumentPreviewPanel from './DocumentPreviewPanel';

interface Props {
  conversationId: number | null;
  onNewConversation: (id: number) => void;
  previewDocId: number | null;
  onPreviewDocChange: (docId: number | null, snippet?: string) => void;
  currentKbId: number;
}

export default function ChatPanel({ conversationId, onNewConversation, previewDocId, onPreviewDocChange, currentKbId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [pendingSources, setPendingSources] = useState<Source[] | null>(null);
  const [highlightSnippet, setHighlightSnippet] = useState<string | undefined>();
  const [thinkingMode, setThinkingMode] = useState(false);
  const [thinkingStatus, setThinkingStatus] = useState<string | null>(null);
  const [uploadedImage, setUploadedImage] = useState<{ base64: string; filename: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleImageUpload = (file: File) => {
    // 检查文件类型
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      message.error('仅支持 JPEG、PNG、GIF、WebP 格式的图片');
      return false;
    }

    // 检查文件大小（最大 10MB）
    if (file.size > 10 * 1024 * 1024) {
      message.error('图片大小不能超过 10MB');
      return false;
    }

    // 转换为 Base64
    const reader = new FileReader();
    reader.onload = (e) => {
      const base64 = e.target?.result as string;
      setUploadedImage({ base64, filename: file.name });
      message.success(`已上传图片: ${file.name}`);
    };
    reader.readAsDataURL(file);

    return false; // 阻止自动上传
  };

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
    setThinkingStatus(null);

    // 判断是否有图片上传
    const hasImage = uploadedImage !== null;
    const displayContent = hasImage
      ? `[图片分析] ${question}`
      : thinkingMode
      ? `[深度思考] ${question}`
      : question;

    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: displayContent,
      sources: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    let fullContent = '';
    let convId = conversationId;

    const callbacks = {
      onToken: (content: string) => {
        fullContent += content;
        setStreamingContent(fullContent);
      },
      onSources: (sources: Source[]) => {
        setPendingSources(sources);
      },
      onDone: (data: { conversation_id: number }) => {
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
        setThinkingStatus(null);
        setUploadedImage(null); // 清除已上传的图片

        if (!conversationId && data.conversation_id) {
          onNewConversation(data.conversation_id);
        }
      },
      onError: (error: string) => {
        message.error(error);
        setLoading(false);
        setStreamingContent('');
        setThinkingStatus(null);
      },
      onThinking: (status: string, msg: string) => {
        setThinkingStatus(msg);
      },
    };

    if (hasImage) {
      // 图片分析模式
      streamImageAnalysis(question, uploadedImage!.base64, conversationId, callbacks, currentKbId);
    } else {
      // 普通或深度思考模式
      streamChat(question, conversationId, callbacks, currentKbId, thinkingMode);
    }
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
              <Spin description="思考中..." />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ padding: 16, borderTop: '1px solid #f0f0f0' }}>
          {thinkingStatus && (
            <div style={{ marginBottom: 8, color: '#1677ff', fontSize: 13 }}>
              <Spin size="small" /> {thinkingStatus}
            </div>
          )}
          {uploadedImage && (
            <div style={{ marginBottom: 8, padding: '8px 12px', background: '#f0f7ff', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ color: '#1677ff' }}>
                <PictureOutlined /> 已上传图片: {uploadedImage.filename}
              </span>
              <Button type="link" size="small" onClick={() => setUploadedImage(null)}>
                移除
              </Button>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <Upload
              showUploadList={false}
              beforeUpload={handleImageUpload}
              accept="image/jpeg,image/png,image/gif,image/webp"
            >
              <Tooltip title="上传图片进行分析（支持视觉模型）">
                <Button icon={<PictureOutlined />} />
              </Tooltip>
            </Upload>
            <Tooltip title={thinkingMode ? '深度思考模式已开启（使用更强模型，响应更慢）' : '开启深度思考模式'}>
              <Button
                icon={<BulbOutlined />}
                onClick={() => setThinkingMode(!thinkingMode)}
                style={{
                  color: thinkingMode ? '#1677ff' : undefined,
                  borderColor: thinkingMode ? '#1677ff' : undefined,
                }}
              />
            </Tooltip>
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={
                uploadedImage
                  ? '输入关于图片的问题...'
                  : thinkingMode
                  ? '输入问题（深度思考模式）...'
                  : '输入问题... (Shift+Enter 换行)'
              }
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
