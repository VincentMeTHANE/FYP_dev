import React from 'react';
import { Card, Typography, Statistic, Row, Col, Tag } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface StepStatsProps {
  executionTime?: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  compact?: boolean;
}

/**
 * 步骤统计组件
 * 显示单个步骤的执行时间和Token使用量
 */
export const StepStats: React.FC<StepStatsProps> = ({
  executionTime,
  promptTokens,
  completionTokens,
  totalTokens,
  compact = false
}) => {
  // 格式化时间
  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}秒`;
    } else {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = (seconds % 60).toFixed(1);
      return `${minutes}分${remainingSeconds}秒`;
    }
  };

  // 格式化数字（添加千分位）
  const formatNumber = (num: number): string => {
    return num.toLocaleString();
  };

  // 如果compact模式且没有任何数据，返回null
  if (compact && !executionTime && !totalTokens) {
    return null;
  }

  if (compact) {
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
        {executionTime !== undefined && executionTime > 0 && (
          <Tag icon={<ClockCircleOutlined />} color="blue">
            耗时: {formatTime(executionTime)}
          </Tag>
        )}
        {totalTokens !== undefined && totalTokens > 0 && (
          <Tag color="green">
            Token: {formatNumber(totalTokens)}
          </Tag>
        )}
      </div>
    );
  }

  return (
    <Card size="small" style={{ backgroundColor: '#fafafa' }}>
      <Row gutter={16}>
        {executionTime !== undefined && executionTime > 0 && (
          <Col span={8}>
            <Statistic
              title="执行时间"
              value={executionTime}
              suffix="秒"
              precision={1}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ fontSize: '16px' }}
            />
          </Col>
        )}
        {promptTokens !== undefined && promptTokens > 0 && (
          <Col span={8}>
            <Statistic
              title="输入Token"
              value={promptTokens}
              prefix={<Text type="secondary">📥</Text>}
              valueStyle={{ fontSize: '16px' }}
            />
          </Col>
        )}
        {completionTokens !== undefined && completionTokens > 0 && (
          <Col span={8}>
            <Statistic
              title="输出Token"
              value={completionTokens}
              prefix={<Text type="secondary">📤</Text>}
              valueStyle={{ fontSize: '16px' }}
            />
          </Col>
        )}
        {totalTokens !== undefined && totalTokens > 0 && (
          <Col span={8}>
            <Statistic
              title="总Token"
              value={totalTokens}
              prefix={<Text type="secondary">📊</Text>}
              valueStyle={{ fontSize: '16px', color: '#1890ff' }}
            />
          </Col>
        )}
      </Row>
      {(!executionTime && !totalTokens) && (
        <Text type="secondary">暂无统计数据</Text>
      )}
    </Card>
  );
};

export default StepStats;
