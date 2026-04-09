import React, { useState, useCallback } from 'react';
import { Card, Button, message, Spin, Space, Typography, Divider, Tag } from 'antd';
import { PlayCircleOutlined, RightOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import JsonViewer from '@/components/JsonViewer';
import type { ChapterInfo, SerpQuery } from '@/types';
import { fetchSerpStream, getTaskIds } from '@/api';

const { Title, Text } = Typography;

interface Step3SerpProps {
  reportId: string;
  chapters: ChapterInfo[];
  onNext: (reportId: string, allTasks: { task_id: string; query: string; researchGoal: string }[], executionTime?: number, tokenUsage?: { prompt: number; completion: number; total: number }) => void;
  onBack?: () => void;
}

interface ChapterSerpData {
  chapter: ChapterInfo;
  queries: SerpQuery[];
  loading: boolean;
  complete: boolean;
  error?: string;
  executionTime?: number;
}

export const Step3Serp: React.FC<Step3SerpProps> = ({ reportId, chapters, onNext, onBack }) => {
  const [chapterData, setChapterData] = useState<Record<string, ChapterSerpData>>(() => {
    const initial: Record<string, ChapterSerpData> = {};
    chapters.forEach(chapter => {
      initial[chapter.split_id] = { chapter, queries: [], loading: false, complete: false };
    });
    return initial;
  });
  const [allComplete, setAllComplete] = useState(false);
  const [totalExecutionTime, setTotalExecutionTime] = useState<number>(0);

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

  const handleGenerateSerp = useCallback(async (splitId: string) => {
    const startTime = Date.now();
    setChapterData(prev => ({ ...prev, [splitId]: { ...prev[splitId], loading: true, error: undefined } }));

    try {
      await new Promise<void>((resolve, reject) => {
        let fullContent = '';
        fetchSerpStream(
          reportId,
          splitId,
          (chunk) => { fullContent = chunk; },
          () => {
            try {
              const elapsed = (Date.now() - startTime) / 1000;
              const cleaned = fullContent.replace(/```json\n?/g, '').replace(/\n?```/g, '').trim();
              const parsed = JSON.parse(cleaned);
              const queries: SerpQuery[] = Array.isArray(parsed) ? parsed : [];
              setChapterData(prev => ({
                ...prev,
                [splitId]: { ...prev[splitId], queries, loading: false, complete: true, executionTime: elapsed }
              }));
              resolve();
            } catch {
              reject(new Error('解析SERP数据失败'));
            }
          },
          (error) => {
            setChapterData(prev => ({ ...prev, [splitId]: { ...prev[splitId], loading: false, complete: true, error: error.message } }));
            reject(error);
          }
        );
      });
    } catch (error) {
      console.error('Error generating SERP:', error);
    }
  }, [reportId]);

  const handleGenerateAllSerp = useCallback(async () => {
    const startTime = Date.now();
    for (const chapter of chapters) {
      await handleGenerateSerp(chapter.split_id);
    }
    setTotalExecutionTime((Date.now() - startTime) / 1000);
    setAllComplete(true);
    message.success('所有章节的SERP已生成');
  }, [chapters, handleGenerateSerp]);

  const handleDeleteQuery = useCallback((splitId: string, index: number) => {
    setChapterData(prev => ({
      ...prev,
      [splitId]: { ...prev[splitId], queries: prev[splitId].queries.filter((_, i) => i !== index) },
    }));
  }, []);

  const handleNext = useCallback(async () => {
    const allTasks: { task_id: string; query: string; researchGoal: string }[] = [];
    for (const [splitId] of Object.entries(chapterData)) {
      try {
        const tasks = await getTaskIds(splitId);
        tasks.forEach(task => {
          if (task.task_id) {
            allTasks.push({ task_id: task.task_id, query: task.query || '', researchGoal: task.researchGoal || '' });
          }
        });
      } catch (error) {
        console.error('Error getting task IDs:', error);
      }
    }
    if (allTasks.length === 0) {
      message.warning('没有找到任何搜索任务');
      return;
    }
    onNext(reportId, allTasks, totalExecutionTime);
  }, [reportId, chapterData, onNext, totalExecutionTime]);

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第三步：生成SERP</Title>
        <Text type="secondary">为每个章节生成搜索引擎查询列表</Text>
        <Divider />

        <Space style={{ marginBottom: '24px' }}>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleGenerateAllSerp}
            loading={Object.values(chapterData).some(d => d.loading)} disabled={chapters.length === 0}>
            为所有章节生成SERP
          </Button>
          {allComplete && totalExecutionTime > 0 && (
            <Tag icon={<ClockCircleOutlined />} color="blue">
              总耗时: {formatTime(totalExecutionTime)}
            </Tag>
          )}
        </Space>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {chapters.map((chapter, chapterIndex) => {
            const data = chapterData[chapter.split_id];
            if (!data) return null;
            return (
              <Card key={chapter.split_id} size="small" title={`章节 ${chapterIndex + 1}：${chapter.sectionTitle}`}>
                <Space style={{ marginBottom: '16px' }}>
                  <Button icon={<PlayCircleOutlined />} onClick={() => handleGenerateSerp(chapter.split_id)} loading={data.loading}>
                    生成此章节SERP
                  </Button>
                  {data.complete && !data.loading && <Tag color="success" icon={<CheckCircleOutlined />}>已完成</Tag>}
                  {data.executionTime && <Tag icon={<ClockCircleOutlined />}>{formatTime(data.executionTime)}</Tag>}
                </Space>

                {data.loading && <div style={{ textAlign: 'center', padding: '20px' }}><Spin /><div style={{ marginTop: '8px' }}><Text type="secondary">正在生成查询列表...</Text></div></div>}

                {data.complete && !data.loading && data.queries.length > 0 && (
                  <div>
                    <Text type="secondary" style={{ marginBottom: '12px', display: 'block' }}>生成的查询列表（共 {data.queries.length} 项）：</Text>
                    <JsonViewer data={data.queries} deletable onDelete={(index) => handleDeleteQuery(chapter.split_id, index)} />
                  </div>
                )}

                {data.complete && !data.loading && data.queries.length === 0 && !data.error && <Text type="secondary">暂无查询数据</Text>}
                {data.error && <Text type="danger">{data.error}</Text>}
              </Card>
            );
          })}
        </div>

        <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between' }}>
          {onBack && <Button onClick={onBack}>上一步</Button>}
          <Button type="primary" size="large" icon={<RightOutlined />} onClick={handleNext}
            style={{ marginLeft: 'auto' }} disabled={!allComplete || Object.values(chapterData).some(d => !d.complete)}>
            下一步：执行搜索
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default Step3Serp;
