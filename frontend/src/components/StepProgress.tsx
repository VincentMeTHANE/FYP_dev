import React from 'react';
import { Steps } from 'antd';

interface StepProgressProps {
  currentStep: number;
  onStepChange?: (step: number) => void;
  disabled?: boolean;
}

const steps = [
  { title: '询问问题', description: '生成相关问题' },
  { title: '生成大纲', description: '创建报告结构' },
  { title: '生成SERP', description: '搜索引擎查询' },
  { title: '执行搜索', description: '获取搜索结果' },
  { title: '搜索总结', description: '内容汇总' },
  { title: '生成报告', description: '最终报告' },
];

export const StepProgress: React.FC<StepProgressProps> = ({ currentStep, onStepChange, disabled = false }) => {
  return (
    <div style={{ padding: '24px', backgroundColor: '#fff', marginBottom: '24px', borderRadius: '8px' }}>
      <Steps
        current={currentStep - 1}
        onChange={disabled ? undefined : onStepChange}
        size="small"
        items={steps.map((step, index) => ({
          title: step.title,
          description: step.description,
          status: index + 1 < currentStep ? 'finish' : index + 1 === currentStep ? 'process' : 'wait',
        }))}
      />
    </div>
  );
};

export default StepProgress;
