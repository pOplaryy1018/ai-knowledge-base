<script setup lang="ts">
/**
 * 注册页面 — 用户名 + 密码 + 确认密码
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'

import { register as registerApi } from '@/api/auth'

const router = useRouter()

const formRef = ref()
const form = reactive({ username: '', password: '', confirmPassword: '' })
const loading = ref(false)

const validateConfirmPassword = (value: string, callback: (error?: string) => void) => {
  if (value !== form.password) {
    callback('两次输入的密码不一致')
  } else {
    callback()
  }
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度不能少于 3 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

async function handleRegister() {
  try { await formRef.value?.validate() } catch { return }

  loading.value = true
  try {
    await registerApi({ username: form.username, password: form.password })
    Message.success('注册成功，请登录')
    router.push('/login')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || '注册失败，请重试'
    Message.error(detail)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-wrapper">
    <div class="register-card">
      <h1 class="register-title">
        创建账户
      </h1>
      <p class="register-subtitle">
        注册后即可使用 AI 知识库问答
      </p>

      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        @keyup.enter="handleRegister"
      >
        <a-form-item
          label="用户名"
          field="username"
        >
          <a-input
            v-model="form.username"
            placeholder="请输入用户名（至少3位）"
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
            placeholder="请输入密码（至少6位）"
            size="large"
          />
        </a-form-item>

        <a-form-item
          label="确认密码"
          field="confirmPassword"
        >
          <a-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            size="large"
          />
        </a-form-item>

        <a-form-item>
          <a-button
            type="primary"
            :loading="loading"
            size="large"
            long
            @click="handleRegister"
          >
            注 册
          </a-button>
        </a-form-item>

        <div class="register-footer">
          已有账户？<router-link to="/login">
            返回登录
          </router-link>
        </div>
      </a-form>
    </div>
  </div>
</template>

<style scoped>
.register-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #122E8A, #0F2570);
}
.register-card {
  width: 420px;
  padding: 48px 40px;
  background: var(--color-bg-card);
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
}
.register-title {
  text-align: center;
  font-size: 24px;
  color: var(--color-primary);
  margin: 0 0 8px;
  font-weight: 600;
}
.register-subtitle {
  text-align: center;
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin: 0 0 32px;
}
.register-footer {
  text-align: center;
  font-size: 14px;
  color: var(--color-text-tertiary);
}
.register-footer a {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
