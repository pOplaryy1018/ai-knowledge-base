<script setup lang="ts">
/**
 * 登录页面 — 用户名 + 密码表单，调用认证接口
 */
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'

import type { LoginRequest } from '@akb/shared'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const store = useUserStore()

const formRef = ref()
const form = reactive<LoginRequest>({ username: '', password: '' })
const loading = ref(false)

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度不能少于 3 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 位', trigger: 'blur' },
  ],
}

async function handleLogin() {
  try { await formRef.value?.validate() } catch { return }

  loading.value = true
  try {
    await store.login(form.username, form.password)
    Message.success('登录成功')
    const redirect = (route.query.redirect as string) || '/workspace/knowledge-bases'
    router.push(redirect)
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
        AI 知识库问答
      </h1>
      <p class="login-subtitle">
        登录后即可向 AI 助手提问
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
            long
            @click="handleLogin"
          >
            登 录
          </a-button>
        </a-form-item>

        <div class="login-footer">
          没有账户？<router-link to="/register">
            立即注册
          </router-link>
        </div>
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
  background: linear-gradient(135deg, #122E8A, #0F2570);
}
.login-card {
  width: 420px;
  padding: 48px 40px;
  background: var(--color-bg-card);
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
}
.login-title {
  text-align: center;
  font-size: 24px;
  color: var(--color-primary);
  margin: 0 0 8px;
  font-weight: 600;
}
.login-subtitle {
  text-align: center;
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin: 0 0 32px;
}
.login-footer {
  text-align: center;
  font-size: 14px;
  color: var(--color-text-tertiary);
}
.login-footer a {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
