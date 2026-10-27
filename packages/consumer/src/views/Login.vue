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
  if (!formRef.value) return
  try { if (await formRef.value.validate()) return } catch { return }

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
  <div class="akb-auth">
    <div class="akb-auth-shell">
      <section class="akb-auth-story">
        <div class="akb-auth-brand">
          AKB / TACTICAL ARCHIVE
        </div>
        <div class="akb-auth-copy">
          <small>OPERATION / PERSONAL KNOWLEDGE</small>
          <h1>每个答案，<br>都有来处。</h1>
          <p>追踪资料版本，定位原文证据。和韬韬一起，把知识整理得更清楚。</p>
        </div>
        <div
          class="akb-auth-portrait"
          aria-hidden="true"
        />
      </section>
      <section class="akb-auth-panel">
        <div class="akb-auth-code">
          01 / USER ACCESS
        </div>
        <h2>重新连接</h2>
        <p>进入你的私人知识空间</p>

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

          <div class="akb-auth-footer">
            没有账户？<router-link to="/register">
              立即注册
            </router-link>
          </div>
        </a-form>
      </section>
    </div>
  </div>
</template>
