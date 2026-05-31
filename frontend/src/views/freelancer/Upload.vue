<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NH2, NText, NButton, NSpace, NUpload, NInput,
  NProgress, NList, NListItem, NTag, NSpin, NAlert, NEmpty
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import type { Deliverable } from '@/types'
import { getDeliverables, submitDeliverable, getContractDetail } from '@/api/contract'
import http from '@/api/index'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const taskId = route.params.id as string

const fileList = ref<UploadFileInfo[]>([])
const description = ref('')
const uploading = ref(false)
const uploadProgress = ref(0)
const submitting = ref(false)
const deliverables = ref<Deliverable[]>([])
const loading = ref(true)
const contractTitle = ref('')

async function loadDeliverables() {
  loading.value = true
  try {
    const [delivRes, contractRes] = await Promise.all([
      getDeliverables(taskId),
      getContractDetail(taskId)
    ])
    deliverables.value = delivRes.data
    contractTitle.value = contractRes.data.title
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

onMounted(loadDeliverables)

function handleCustomRequest({ file, onFinish, onError, onProgress }: any) {
  onProgress({ percent: 0 })
  onFinish()
}

async function handleSubmit() {
  if (fileList.value.length === 0) {
    message.warning('请先选择要上传的文件')
    return
  }
  uploading.value = true
  uploadProgress.value = 0

  try {
    const formData = new FormData()
    const file = fileList.value[0]
    if (file.file) {
      formData.append('file', file.file)
    }
    formData.append('description', description.value || '')

    const progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += 10
      }
    }, 200)

    const { data: deliverable } = await http.post<Deliverable>(
      `/v1/contracts/${taskId}/deliverables`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
        onUploadProgress(e) {
          if (e.total) {
            uploadProgress.value = Math.round((e.loaded / e.total) * 100)
          }
        }
      }
    )

    clearInterval(progressInterval)
    uploadProgress.value = 100

    message.success('文件上传成功，正在提交交付物...')
    uploading.value = false
    submitting.value = true

    await submitDeliverable(taskId, deliverable.id)
    message.success('交付物提交成功！AI 验收即将开始')

    fileList.value = []
    description.value = ''
    await loadDeliverables()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '上传失败，请重试')
  } finally {
    uploading.value = false
    submitting.value = false
    uploadProgress.value = 0
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="upload-page">
    <NH2>
      提交交付物
      <NText v-if="contractTitle" depth="3" style="font-size: 14px; margin-left: 8px">
        {{ contractTitle }}
      </NText>
    </NH2>

    <NSpin v-if="loading" size="large" style="display: flex; justify-content: center; padding: 48px" />

    <template v-else>
      <NCard title="上传文件" style="margin-bottom: 24px">
        <template #header-extra>
          <NText depth="3" style="font-size: 13px">合约ID: {{ taskId }}</NText>
        </template>

        <NUpload
          v-model:file-list="fileList"
          :max="1"
          :custom-request="handleCustomRequest"
          accept=".zip,.rar,.7z,.tar,.gz,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.png,.jpg,.jpeg,.gif,.svg,.mp4,.mp3,.py,.js,.ts,.java,.go,.rs,.html,.css"
          directory-dnd
          :disabled="uploading || submitting"
        >
          <NButton :disabled="uploading || submitting">
            选择文件或拖拽上传
          </NButton>
        </NUpload>

        <div style="margin-top: 16px">
          <NInput
            v-model:value="description"
            type="textarea"
            :rows="4"
            placeholder="请描述交付物内容、使用说明和注意事项..."
            :disabled="uploading || submitting"
          />
        </div>

        <div v-if="uploading" style="margin-top: 16px">
          <NText depth="3" style="display: block; margin-bottom: 8px">
            上传进度: {{ uploadProgress }}%
          </NText>
          <NProgress
            type="line"
            :percentage="uploadProgress"
            :show-indicator="false"
            :status="uploadProgress >= 100 ? 'success' : 'default'"
          />
        </div>

        <NSpace style="margin-top: 24px">
          <NButton
            type="primary"
            :loading="uploading || submitting"
            :disabled="fileList.length === 0"
            @click="handleSubmit"
          >
            {{ uploading ? '上传中...' : submitting ? '提交中...' : '提交交付物' }}
          </NButton>
          <NButton @click="router.back()" :disabled="uploading || submitting">
            返回
          </NButton>
        </NSpace>
      </NCard>

      <NCard title="已提交的交付物">
        <NEmpty v-if="deliverables.length === 0" description="暂无已提交的交付物" />

        <NList v-else bordered>
          <NListItem v-for="item in deliverables" :key="item.id">
            <NSpace align="center" justify="space-between" style="width: 100%">
              <div>
                <NText strong>{{ item.file_name }}</NText>
                <br />
                <NText depth="3" style="font-size: 13px">
                  {{ item.description || '无描述' }}
                </NText>
                <br />
                <NText depth="3" style="font-size: 12px">
                  提交时间: {{ formatDate(item.submitted_at) }}
                </NText>
              </div>
              <NSpace>
                <NButton
                  size="small"
                  tag="a"
                  :href="item.file_url"
                  target="_blank"
                  type="primary"
                  ghost
                >
                  下载
                </NButton>
                <NButton
                  size="small"
                  @click="router.push(`/task/${taskId}/acceptance`)"
                >
                  查看验收
                </NButton>
              </NSpace>
            </NSpace>
          </NListItem>
        </NList>
      </NCard>

      <NAlert type="info" style="margin-top: 16px">
        提交交付物后，AI 将自动进行验收评估。你可以在"验收报告"页面查看验收结果。
      </NAlert>
    </template>
  </div>
</template>

<style scoped>
.upload-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}
</style>
