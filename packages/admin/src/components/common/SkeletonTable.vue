<script setup lang="ts">
/**
 * 表格骨架屏 — 模拟表格加载状态
 */
withDefaults(
  defineProps<{ rows?: number; cols?: number }>(),
  { rows: 5, cols: 4 },
)
</script>

<template>
  <div class="skeleton-table">
    <a-skeleton :animation="true">
      <template
        v-for="_n in rows"
        :key="_n"
      >
        <div class="skeleton-row">
          <div
            v-for="j in cols"
            :key="j"
            style="flex:1;height:20px;margin-right:24px"
          >
            <a-skeleton-line />
          </div>
        </div>
      </template>
    </a-skeleton>
  </div>
</template>

<style scoped>
.skeleton-table { padding: 16px 0; }
.skeleton-row { display: flex; padding: 12px 0; border-bottom: 1px solid #ebeef5; }
</style>
