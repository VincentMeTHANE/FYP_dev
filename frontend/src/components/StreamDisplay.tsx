import React from 'react';
import { Card, Typography, Button, Space } from 'antd';
import { SaveOutlined, LoadingOutlined } from '@ant-design/icons';

const { Title } = Typography;

interface StreamDisplayProps {
  title: string;
  content: string;
  loading?: boolean;
  onSave?: () => void;
  saveLoading?: boolean;
  children?: React.ReactNode;
}

export const StreamDisplay: React.FC<StreamDisplayProps> = ({
  title,
  content,
  loading = false,
  onSave,
  saveLoading = false,
  children,
}) => {
  return (
    <Card
      title={
        <Space>
          <Title level={5} style={{ margin: 0 }}>{title}</Title>
          {loading && <LoadingOutlined spin />}
        </Space>
      }
      extra={onSave && <Button type="primary" icon={<SaveOutlined />} onClick={onSave} loading={saveLoading} disabled={!content || loading}>保存</Button>}
      style={{ marginBottom: '16px' }}
    >
      <div style={{ minHeight: '200px', maxHeight: '500px', overflow: 'auto' }}>{children}</div>
    </Card>
  );
};

export default StreamDisplay;
