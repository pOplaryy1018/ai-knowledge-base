<script setup lang="ts">
/**
 * 消费者端根组件 ── 根据登录状态渲染登录页或主路由
 */
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="consumer-app">
    <RouterView />
  </div>
</template>

<style scoped>
.consumer-app {
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>
