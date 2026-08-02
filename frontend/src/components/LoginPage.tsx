import { useState } from 'react';
import { Card, Form, Input, Button, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { login, register } from '../services/api';
import { getErrorMessage } from '../services/errors';

const { Title, Text } = Typography;

interface Props {
  onLogin: (user: { id: number; username: string }) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const fn = isRegister ? register : login;
      const result = await fn(values.username, values.password);
      message.success(isRegister ? '注册成功' : '登录成功');
      onLogin(result.user);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '操作失败'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f5f5f5',
      }}
    >
      <Card style={{ width: 380, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>LocalRAG</Title>
          <Text type="secondary">本地知识库系统</Text>
        </div>

        <Form onFinish={handleSubmit} autoComplete="off" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>

          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>

          {isRegister && (
            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
            </Form.Item>
          )}

          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>
              {isRegister ? '注册' : '登录'}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Space>
            <Text type="secondary">
              {isRegister ? '已有账号？' : '没有账号？'}
            </Text>
            <Button type="link" size="small" onClick={() => setIsRegister(!isRegister)}>
              {isRegister ? '去登录' : '去注册'}
            </Button>
          </Space>
        </div>
      </Card>
    </div>
  );
}
