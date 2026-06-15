import { useState, useEffect } from 'react';
import { ConfigProvider, theme, Button, Drawer } from 'antd';
import { MenuOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';

export default function App() {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [currentKbId, setCurrentKbId] = useState<number>(1);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [previewDocId, setPreviewDocId] = useState<number | null>(null);

  const handlePreviewChange = (docId: number | null, _snippet?: string) => {
    setPreviewDocId(docId);
  };

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleNewConversation = (id: number) => {
    setConversationId(id);
    setRefreshTrigger((prev) => prev + 1);
    if (isMobile) setDrawerOpen(false);
  };

  const sidebarContent = (
    <>
      <div
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid #f0f0f0',
          fontWeight: 600,
          fontSize: 16,
        }}
      >
        LocalRAG
      </div>
      <Sidebar
        currentConversationId={conversationId}
        onSelectConversation={(id) => {
          setConversationId(id);
          if (isMobile) setDrawerOpen(false);
        }}
        refreshTrigger={refreshTrigger}
        onDocumentClick={(docId) => handlePreviewChange(docId)}
        currentKbId={currentKbId}
        onKbChange={setCurrentKbId}
      />
    </>
  );

  return (
    <ConfigProvider locale={zhCN} theme={{ algorithm: theme.defaultAlgorithm }}>
      <div style={{ display: 'flex', height: '100vh', background: '#fff' }}>
        {!isMobile && (
          <div
            style={{
              width: 280,
              borderRight: '1px solid #f0f0f0',
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
            }}
          >
            {sidebarContent}
          </div>
        )}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          {isMobile && (
            <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setDrawerOpen(true)}
              />
              <span style={{ fontWeight: 600 }}>LocalRAG</span>
            </div>
          )}
          <ChatPanel
            conversationId={conversationId}
            onNewConversation={handleNewConversation}
            previewDocId={previewDocId}
            onPreviewDocChange={handlePreviewChange}
            currentKbId={currentKbId}
          />
        </div>
      </div>
      <Drawer
        placement="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={280}
        styles={{ body: { padding: 0 } }}
      >
        {sidebarContent}
      </Drawer>
    </ConfigProvider>
  );
}
