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
  if (!formRef.value) return
  try { if (await formRef.value.validate()) return } catch { return }

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
  <div class="akb-auth">
    <div class="akb-auth-shell">
      <section class="akb-auth-story">
        <div class="akb-auth-brand">
          AKB / TACTICAL ARCHIVE
        </div>
        <div class="akb-auth-copy">
          <small>OPERATION / PERSONAL KNOWLEDGE</small>
          <h1>从第一份资料，<br>开始归档。</h1>
          <p>建立自己的资料空间，让每个回答都能回到原文。</p>
        </div>
        <div
          class="akb-auth-portrait"
          aria-hidden="true"
        />
      </section>
      <section class="akb-auth-panel">
        <div class="akb-auth-code">
          00 / CREATE ACCESS
        </div>
        <h2>创建账户</h2>
        <p>注册后即可使用知识库问答</p>

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

          <div class="akb-auth-footer">
            已有账户？<router-link to="/login">
              返回登录
            </router-link>
          </div>
        </a-form>
      </section>
    </div>
  </div>
</template>
