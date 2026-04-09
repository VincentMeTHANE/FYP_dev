import React from 'react';
import { Card, Typography, Statistic, Row, Col, Table, Tag, Divider, Progress } from 'antd';
import {
  ClockCircleOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';

const { Text, Title } = Typography;

interface StepInfo {
  name: string;
  displayName: string;
  executionTime?: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  completed?: boolean;
}

interface FinalStatsProps {
  totalExecutionTime: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  stepTimes: Record<string, number>;
  tokenStats?: {
    collection: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    execution_time?: number;
  }[];
}

/**
 * 最终统计组件
 * 显示整个报告生成过程的统计数据
 */
export const FinalStats: React.FC<FinalStatsProps> = ({
  totalExecutionTime,
  totalPromptTokens,
  totalCompletionTokens,
  totalTokens,
  stepTimes,
  tokenStats
}) => {
  // 格式化时间
  const formatTime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds.toFixed(1)}秒`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = (seconds % 60).toFixed(0);
      return `${minutes}分${remainingSeconds}秒`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${hours}小时${minutes}分`;
    }
  };

  // 格式化数字（添加千分位）
  const formatNumber = (num: number): string => {
    return num.toLocaleString();
  };

  // 步骤名称映射
  const stepNameMap: Record<string, string> = {
    'report_ask_questions': '询问问题',
    'report_plan': '生成大纲',
    'report_serp': '生成SERP',
    'report_search': '执行搜索',
    'report_search_summary': '搜索总结'
  };

  // 将tokenStats转换为表格数据
  const tableData = tokenStats?.map((stat, index) => ({
    key: index,
    name: stepNameMap[stat.collection] || stat.collection,
    promptTokens: stat.prompt_tokens,
    completionTokens: stat.completion_tokens,
    totalTokens: stat.total_tokens,
    executionTime: stat.execution_time || 0
  })) || [];

  // 计算总执行时间（从stepTimes）
  const calculatedTotalTime = Object.values(stepTimes).reduce((sum, t) => sum + (t || 0), 0);

  return (
    <Card
      title={
        <span>
          <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '8px' }} />
          报告生成统计
        </span>
      }
      style={{ marginTop: '24px', borderColor: '#52c41a' }}
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ backgroundColor: '#e6f7ff', border: 'none' }}>
            <Statistic
              title={<Text strong>总耗时</Text>}
              value={formatTime(totalExecutionTime || calculatedTotalTime)}
              prefix={<ClockCircleOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff', fontSize: '20px' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ backgroundColor: '#f6ffed', border: 'none' }}>
            <Statistic
              title={<Text strong>总输入Token</Text>}
              value={formatNumber(totalPromptTokens)}
              prefix={<Text style={{ color: '#52c41a' }}>📥</Text>}
              valueStyle={{ color: '#52c41a', fontSize: '20px' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ backgroundColor: '#fff7e6', border: 'none' }}>
            <Statistic
              title={<Text strong>总输出Token</Text>}
              value={formatNumber(totalCompletionTokens)}
              prefix={<Text style={{ color: '#fa8c16' }}>📤</Text>}
              valueStyle={{ color: '#fa8c16', fontSize: '20px' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" style={{ backgroundColor: '#f9f0ff', border: 'none' }}>
            <Statistic
              title={<Text strong>Token总计</Text>}
              value={formatNumber(totalTokens)}
              prefix={<ThunderboltOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1', fontSize: '20px' }}
            />
          </Card>
        </Col>
      </Row>

      {tokenStats && tokenStats.length > 0 && (
        <>
          <Divider orientation="left">各步骤详情</Divider>
          <Table
            dataSource={tableData}
            pagination={false}
            size="small"
            columns={[
              {
                title: '步骤',
                dataIndex: 'name',
                key: 'name',
                width: 120
              },
              {
                title: '输入Token',
                dataIndex: 'promptTokens',
                key: 'promptTokens',
                render: (val: number) => formatNumber(val),
                width: 100
              },
              {
                title: '输出Token',
                dataIndex: 'completionTokens',
                key: 'completionTokens',
                render: (val: number) => formatNumber(val),
                width: 100
              },
              {
                title: '总Token',
                dataIndex: 'totalTokens',
                key: 'totalTokens',
                render: (val: number) => (
                  <Tag color="blue">{formatNumber(val)}</Tag>
                ),
                width: 120
              },
              {
                title: '耗时',
                dataIndex: 'executionTime',
                key: 'executionTime',
                render: (val: number) => formatTime(val),
                width: 100
              }
            ]}
          />
        </>
      )}

      {Object.keys(stepTimes).length > 0 && (
        <>
          <Divider orientation="left">步骤耗时分布</Divider>
          <div style={{ padding: '0 8px' }}>
            {Object.entries(stepTimes).map(([step, time]) => {
              const percentage = calculatedTotalTime > 0 ? (time / calculatedTotalTime) * 100 : 0;
              return (
                <div key={step} style={{ marginBottom: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <Text>{stepNameMap[step] || step}</Text>
                    <Text type="secondary">{formatTime(time)} ({percentage.toFixed(1)}%)</Text>
                  </div>
                  <Progress
                    percent={percentage}
                    size="small"
                    showInfo={false}
                    strokeColor="#1890ff"
                  />
                </div>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
};

export default FinalStats;