import React, { useState, useCallback } from 'react';
import { Card, Input, Button, message, Spin, Space, Typography, Divider, List } from 'antd';
import { PlayCircleOutlined, SaveOutlined, RightOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { fetchAskQuestionsStream, updateQuestions } from '@/api';

const { Title, Text } = Typography;

interface Step1QuestionsProps {
  reportId: string;
  onNext: (reportId: string, questions: string) => void;
}

export const Step1Questions: React.FC<Step1QuestionsProps> = ({ reportId, onNext }) => {
  const [topic, setTopic] = useState<string>('');
  const [questions, setQuestions] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [editableQuestions, setEditableQuestions] = useState<string[]>([]);

  const handleGenerateQuestions = useCallback(async () => {
    if (!topic.trim()) {
      message.warning('请输入报告主题');
      return;
    }

    setLoading(true);
    setQuestions('');
    setEditableQuestions([]);

    try {
      await new Promise<void>((resolve, reject) => {
        let fullContent = '';

        fetchAskQuestionsStream(
          reportId,
          topic,
          (chunk) => {
            fullContent = chunk;
            setQuestions(chunk);
          },
          () => {
            setLoading(false);
            const lines = fullContent.split('\n').filter(line => line.trim());
            const parsedQuestions: string[] = [];
            lines.forEach(line => {
              const match = line.match(/^\d+[\.、]\s*(.+)/);
              if (match) {
                parsedQuestions.push(match[1].trim());
              }
            });
            if (parsedQuestions.length > 0) {
              setEditableQuestions(parsedQuestions);
            }
            resolve();
          },
          (error) => {
            setLoading(false);
            message.error('生成问题失败: ' + error.message);
            reject(error);
          }
        );
      });
    } catch (error) {
      console.error('Error generating questions:', error);
    }
  }, [topic, reportId]);

  const handleSaveQuestions = useCallback(async () => {
    if (!reportId) {
      message.error('报告ID不存在');
      return;
    }

    setSaveLoading(true);
    try {
      const questionsText = editableQuestions.length > 0
        ? editableQuestions.map((q, i) => `${i + 1}. ${q}`).join('\n')
        : questions;
      await updateQuestions(reportId, questionsText);
      message.success('问题已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaveLoading(false);
    }
  }, [reportId, editableQuestions, questions]);

  const handleAddQuestion = useCallback(() => {
    setEditableQuestions(prev => [...prev, '']);
  }, []);

  const handleUpdateQuestion = useCallback((index: number, value: string) => {
    setEditableQuestions(prev => {
      const updated = [...prev];
      updated[index] = value;
      return updated;
    });
  }, []);

  const handleDeleteQuestion = useCallback((index: number) => {
    setEditableQuestions(prev => prev.filter((_, i) => i !== index));
  }, []);

  const handleNext = useCallback(() => {
    const questionsText = editableQuestions.length > 0
      ? editableQuestions.map((q, i) => `${i + 1}. ${q}`).join('\n')
      : questions;
    onNext(reportId, questionsText);
  }, [reportId, questions, editableQuestions, onNext]);

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={4}>第一步：询问问题</Title>
        <Text type="secondary">请输入报告主题，系统将生成相关的研究问题</Text>
        <Divider />

        <div style={{ marginBottom: '24px' }}>
          <Text type="secondary" style={{ marginBottom: '8px', display: 'block' }}>报告主题</Text>
          <Input
            placeholder="请输入报告主题，例如：人工智能在医疗领域的应用"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            size="large"
            style={{ marginTop: '8px' }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleGenerateQuestions}
            loading={loading}
            style={{ marginTop: '16px' }}
            size="large"
          >
            生成问题
          </Button>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Spin size="large" />
            <div style={{ marginTop: '16px' }}><Text type="secondary">正在生成相关问题...</Text></div>
          </div>
        )}

        {questions && !loading && (
          <>
            <Divider>生成的问题</Divider>

            <div style={{ marginBottom: '24px' }}>
              <Space style={{ marginBottom: '16px' }}>
                <Button icon={<PlusOutlined />} onClick={handleAddQuestion}>添加问题</Button>
                <Button icon={<SaveOutlined />} type="primary" onClick={handleSaveQuestions} loading={saveLoading}>保存修改</Button>
              </Space>

              <List
                dataSource={editableQuestions}
                renderItem={(item: string, index: number) => (
                  <List.Item
                    actions={[
                      <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteQuestion(index)} key="delete" />
                    ]}
                  >
                    <List.Item.Meta
                      title={<span style={{ color: '#1890ff' }}>问题 {index + 1}</span>}
                      description={
                        <Input.TextArea
                          value={item}
                          onChange={(e) => handleUpdateQuestion(index, e.target.value)}
                          autoSize={{ minRows: 1, maxRows: 3 }}
                          style={{ marginTop: '8px' }}
                        />
                      }
                    />
                  </List.Item>
                )}
              />
            </div>

            <div style={{ marginBottom: '24px' }}>
              <Text type="secondary" style={{ marginBottom: '8px', display: 'block' }}>原始Markdown内容</Text>
              <Card size="small" style={{ backgroundColor: '#f5f5f5' }}>
                <MarkdownRenderer content={questions} scrollToBottom={false} />
              </Card>
            </div>

            <Button
              type="primary"
              size="large"
              icon={<RightOutlined />}
              onClick={handleNext}
              style={{ float: 'right' }}
            >
              下一步：生成大纲
            </Button>
          </>
        )}
      </Card>
    </div>
  );
};

export default Step1Questions;
