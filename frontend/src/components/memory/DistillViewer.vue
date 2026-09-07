<template>
  <div class="distill-viewer-container">
    <!-- Action Header -->
    <div class="distill-header">
      <div class="header-left">
        <div class="title-row">
          <el-icon><Compass /></el-icon>
          <span class="title-text">L3 长期偏好反思与蒸馏透视 (Offline Distillation)</span>
        </div>
        <p class="subtitle-text">
          由后台任务对近期历史出行经历（L2 Episodes）与评测反馈（Feedback）进行周期性提炼与反思，生成结构化长期记忆。
        </p>
      </div>

      <el-button
        type="primary"
        :loading="memoryStore.isDistilling"
        @click="handleTriggerDistill"
      >
        <el-icon><Refresh /></el-icon>
        手动触发偏好蒸馏
      </el-button>
    </div>

    <!-- Distill Report Body -->
    <div class="report-card">
      <div class="report-meta-bar">
        <span class="meta-tag">文档路径: memory/distill/user_{{ memoryStore.distillReport?.userId || 1 }}.md</span>
        <span class="meta-status">已同步至 Agent 上下文</span>
      </div>

      <div class="report-content">
        <div
          v-if="!memoryStore.distillReport?.content"
          class="empty-report"
        >
          暂无偏好蒸馏记录，点击右上角按钮即可立即触发生成喵~
        </div>

        <div v-else class="markdown-body">
          <div
            v-for="(para, idx) in formattedParagraphs"
            :key="idx"
            class="md-block"
          >
            <h1 v-if="para.type === 'h1'" class="md-h1">{{ para.text }}</h1>
            <h2 v-else-if="para.type === 'h2'" class="md-h2">{{ para.text }}</h2>
            <h3 v-else-if="para.type === 'h3'" class="md-h3">{{ para.text }}</h3>
            <ul v-else-if="para.type === 'list'" class="md-ul">
              <li v-for="(item, itemIdx) in para.items" :key="itemIdx">{{ item }}</li>
            </ul>
            <p v-else class="md-p">{{ para.text }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useMemoryStore } from '@/stores/memory'

const memoryStore = useMemoryStore()

async function handleTriggerDistill() {
  try {
    await memoryStore.triggerDistill()
    ElMessage.success('L3 偏好蒸馏执行完成，报告已刷新！')
  } catch (err: any) {
    ElMessage.error(err?.message || '蒸馏失败')
  }
}

interface MarkdownBlock {
  type: 'h1' | 'h2' | 'h3' | 'p' | 'list'
  text?: string
  items?: string[]
}

const formattedParagraphs = computed<MarkdownBlock[]>(() => {
  const raw = memoryStore.distillReport?.content || ''
  if (!raw) return []

  const lines = raw.split('\n')
  const blocks: MarkdownBlock[] = []
  let currentList: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      continue
    }

    if (trimmed.startsWith('# ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h1', text: trimmed.replace(/^#\s+/, '') })
    } else if (trimmed.startsWith('## ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h2', text: trimmed.replace(/^##\s+/, '') })
    } else if (trimmed.startsWith('### ')) {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'h3', text: trimmed.replace(/^###\s+/, '') })
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      currentList.push(trimmed.replace(/^[-*]\s+/, ''))
    } else {
      if (currentList.length > 0) {
        blocks.push({ type: 'list', items: [...currentList] })
        currentList = []
      }
      blocks.push({ type: 'p', text: trimmed })
    }
  }

  if (currentList.length > 0) {
    blocks.push({ type: 'list', items: [...currentList] })
  }

  return blocks
})
</script>

<style scoped>
.distill-viewer-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.distill-header {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.subtitle-text {
  font-size: 12px;
  color: #64748b;
  margin: 0;
  line-height: 1.45;
}

.report-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
}

.report-meta-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  padding: 8px 16px;
  font-size: 11.5px;
}

.meta-tag {
  font-family: monospace;
  color: #475569;
}

.meta-status {
  background: #dcfce7;
  color: #15803d;
  padding: 1px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

.report-content {
  padding: 24px;
  min-height: 300px;
}

.empty-report {
  text-align: center;
  color: #94a3b8;
  padding: 60px 0;
  font-size: 13px;
}

.markdown-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  line-height: 1.6;
  color: #1e293b;
}

.md-h1 {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 8px;
  margin: 0 0 4px 0;
}

.md-h2 {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 12px 0 2px 0;
}

.md-h3 {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin: 8px 0 2px 0;
}

.md-p {
  font-size: 13px;
  margin: 0;
  color: #334155;
}

.md-ul {
  margin: 4px 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #334155;
}
</style>
