<script setup lang="ts">
/**
 * 登录页面 ── 用户名 + 密码表单，调用认证接口
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// ── 表单数据 ──
const formRef = ref<any>()
const form = reactive({
  username: '',
  password: ''})
const loading = ref(false)

// ── 表单校验 ──
const rules: any = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度不能少于 3 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 位', trigger: 'blur' },
  ]}

// ── 提交登录 ──
async function handleLogin() {
  try { await formRef.value?.validate() } catch { return }

  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    Message.success('登录成功')
    router.push('/admin/dashboard')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
    Message.error(detail)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card">
      <h1 class="login-title">
        AI 知识库管理平台
      </h1>
      <p class="login-subtitle">
        请使用管理员账户登录
      </p>

      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        @keyup.enter="handleLogin"
      >
        <a-form-item
          label="用户名"
          field="username"
        >
          <a-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
          />
        </a-form-item>

        <a-form-item
          label="密码"
          field="password"
        >
          <a-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
          />
        </a-form-item>

        <a-form-item>
          <a-button
            type="primary"
            :loading="loading"
            size="large"
            class="login-btn"
            @click="handleLogin"
          >
            登 录
          </a-button>
        </a-form-item>
      </a-form>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 420px;
  padding: 48px 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
}
.login-title {
  text-align: center;
  font-size: 22px;
  color: #303133;
  margin: 0 0 8px;
}
.login-subtitle {
  text-align: center;
  font-size: 14px;
  color: #909399;
  margin: 0 0 32px;
}
.login-btn {
  width: 100%;
}
</style>
