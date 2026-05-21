<script setup lang="ts">
/** 知识库创建/编辑对话框 */
import { reactive, ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  editing: { id: string; name: string; description: string | null } | null
}>()

const emit = defineEmits<{
  close: []
  submit: [data: { name: string; description?: string }]
}>()

const formRef = ref<any>()
const form = reactive({ name: '', description: '' })
const loading = ref(false)

const rules: any = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }]}

watch(
  () => props.editing,
  (val) => {
    if (val) {
      form.name = val.name
      form.description = val.description || ''
    }
  },
)

watch(
  () => props.visible,
  (v) => {
    if (!v) {
      formRef.value?.resetFields()
      form.name = ''
      form.description = ''
    }
  },
)

async function handleSubmit() {
  try { await formRef.value?.validate() } catch { return }
  loading.value = true
  try {
    emit('submit', {
      name: form.name,
      description: form.description || undefined})
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-modal
    :visible="visible"
    :title="editing ? '编辑知识库' : '创建知识库'"
    :width="500"
    @cancel="$emit('close')"
  >
    <a-form
      ref="formRef"
      :model="form"
      :rules="rules"
      layout="horizontal"
    >
      <a-form-item
        label="名称"
        field="name"
      >
        <a-input
          v-model="form.name"
          placeholder="请输入知识库名称"
        />
      </a-form-item>
      <a-form-item
        label="描述"
        field="description"
      >
        <a-textarea
          v-model="form.description"
          :rows="3"
          placeholder="可选的描述信息"
        />
      </a-form-item>
    </a-form>
    <template #footer>
      <a-button @click="$emit('close')">
        取消
      </a-button>
      <a-button
        type="primary"
        :loading="loading"
        @click="handleSubmit"
      >
        {{ editing ? '保存' : '创建' }}
      </a-button>
    </template>
  </a-modal>
</template>
