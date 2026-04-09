import React, { useState, useCallback, useEffect } from 'react';
import { Card, Button, message, Spin, Space, Typography, Divider, Input, List, Tag } from 'antd';
import { PlayCircleOutlined, SaveOutlined, RightOutlined, CheckOutlined, ClockCircleOutlined } from '@ant-design/icons';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import StreamDisplay from '@/components/StreamDisplay';
import {
  fetchPlanStream,
  splitPlan,
  updatePlan,
  getPlanDetail,
} from '@/api';
import type { ChapterInfo } from '@/types';

const { Title, Text } = Typography;

interface Step2PlanProps {
  reportId: string;
  title: string;
  onNext: (reportId: string, chapters: ChapterInfo[], executionTime?: number, tokenUsage?: { prompt: number; completion: number; total: number }) => void;
  onBack?: () => void;
}

export const Step2Plan: React.FC<Step2PlanProps> = ({
  reportId,
  title,
  onNext,
  onBack,
}) => {
  const [plan, setPlan] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [splitLoading, setSplitLoading] = useState(false);
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [editablePlan, setEditablePlan] = useState<string>('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | undefined>();

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

  const handleSplit = useCallback(async () => {
    setSplitLoading(true);
    try {
      const result = await splitPlan(reportId);
      setChapters(result.response);
      message.success(`大纲已拆分为 ${result.chapters_count} 个章节`);
    } catch {
      message.error('拆分大纲失败');
    } finally {
      setSplitLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    const loadExistingPlan = async () => {
      try {
        const existingPlan = await getPlanDetail(reportId);
        if (existingPlan.plan) {
          setPlan(existingPlan.plan);
          setEditablePlan(existingPlan.plan);
          await handleSplit();
        }
      } catch {
        // ignore
      }
    };
    loadExistingPlan();
  }, [reportId]);

  const handleGeneratePlan = useCallback(async () => {
    const startTime = Date.now();
    setLoading(true);
    setPlan('');
    setChapters([]);
    setExecutionTime(undefined);

    try {
      await new Promise<void>((resolve, reject) => {
        fetchPlanStream(
          reportId,
          (chunk) => {
            setPlan(chunk);
            if (!isEditMode) {
              setEditablePlan(chunk);
            }
          },
          () => {
            const elapsed = (Date.now() - startTime) / 1000;
            setExecutionTime(elapsed);
            setLoading(false);
            message.success('大纲生成完成');
            resolve();
          },
          (error) => {
            setLoading(false);
            message.error('生成大纲失败: ' + error.message);
            reject(error);
          }
        );
      });
      await handleSplit();
    } catch (error) {
      console.error('Error generating plan:', error);
    }
  }, [reportId, isEditMode, handleSplit]);

  const handleSavePlan = useCallback(async () => {
    if (!reportId) {
      message.error('报告ID不存在');
      return;
    }

    setSaveLoading(true);
    try {
      await updatePlan(reportId, editablePlan);
      setPlan(editablePlan);
      setIsEditMode(false);
      message.success('大纲已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaveLoading(false);
    }
  }, [reportId, editablePlan]);

  const handleNext = useCallback(() => {
    if (chapters.length === 0) {
      message.warning('请先生成并拆分大纲');
      return;
    }
    onNext(reportId, chapters, executionTime);
  }, [reportId, chapters, onNext, executionTime]);

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第二步：生成大纲</Title>
        <Text type="secondary">基于报告主题生成研究报告大纲</Text>
        <Divider />

        <Card size="small" style={{ marginBottom: '24px', backgroundColor: '#f0f5ff' }}>
          <Text type="secondary">报告主题：</Text>
          <Text>{title}</Text>
        </Card>

        <Space style={{ marginBottom: '16px' }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleGeneratePlan}
            loading={loading}
            disabled={!reportId}
          >
            {plan ? '重新生成大纲' : '生成大纲'}
          </Button>

          {plan && !loading && (
            <Button icon={<SaveOutlined />} onClick={() => setIsEditMode(!isEditMode)}>
              {isEditMode ? '取消编辑' : '编辑大纲'}
            </Button>
          )}

          {plan && !loading && (
            <Button type="default" icon={<CheckOutlined />} onClick={handleSplit} loading={splitLoading}>
              重新拆分
            </Button>
          )}
        </Space>

        {loading && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Spin size="large" />
            <div style={{ marginTop: '16px' }}><Text type="secondary">正在生成大纲...</Text></div>
          </div>
        )}

        {plan && !loading && (
          <>
            {executionTime && (
              <div style={{ marginBottom: '16px' }}>
                <Tag icon={<ClockCircleOutlined />} color="blue">
                  生成耗时: {formatTime(executionTime)}
                </Tag>
              </div>
            )}

            <StreamDisplay title="报告大纲" content={plan} loading={loading} onSave={handleSavePlan} saveLoading={saveLoading}>
              {isEditMode ? (
                <Input.TextArea
                  value={editablePlan}
                  onChange={(e) => setEditablePlan(e.target.value)}
                  autoSize={{ minRows: 10, maxRows: 30 }}
                  style={{ fontFamily: 'monospace' }}
                />
              ) : (
                <MarkdownRenderer content={plan} scrollToBottom={true} />
              )}
            </StreamDisplay>

            {chapters.length > 0 && (
              <>
                <Divider>章节拆分结果</Divider>
                <List
                  bordered
                  dataSource={chapters}
                  renderItem={(chapter: ChapterInfo, index: number) => (
                    <List.Item>
                      <List.Item.Meta
                        title={<span style={{ color: '#1890ff' }}>第 {index + 1} 章：{chapter.sectionTitle}</span>}
                        description={<Text type="secondary" ellipsis={{ rows: 2 }}>{chapter.content.substring(0, 100)}...</Text>}
                      />
                    </List.Item>
                  )}
                />
              </>
            )}

            <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between' }}>
              {onBack && <Button onClick={onBack}>上一步</Button>}
              <Button
                type="primary"
                size="large"
                icon={<RightOutlined />}
                onClick={handleNext}
                style={{ marginLeft: 'auto' }}
                disabled={chapters.length === 0}
              >
                下一步：生成SERP
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

export default Step2Plan;
