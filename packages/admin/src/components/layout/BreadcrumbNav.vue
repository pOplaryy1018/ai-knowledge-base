<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const breadcrumbs = computed(() => {
  return route.matched
    .filter((r) => r.meta?.title && !r.meta.hidden)
    .map((r) => ({
      title: r.meta.title as string,
      path: r.path}))
})
</script>

<template>
  <a-breadcrumb separator="/">
    <a-breadcrumb-item
      v-for="(item, index) in breadcrumbs"
      :key="item.path"
    >
      <template v-if="index < breadcrumbs.length - 1">
        <router-link
          :to="item.path"
          class="breadcrumb-link"
        >
          {{ item.title }}
        </router-link>
      </template>
      <template v-else>
        <span class="breadcrumb-current">{{ item.title }}</span>
      </template>
    </a-breadcrumb-item>
  </a-breadcrumb>
</template>

<style scoped>
.breadcrumb-link {
  color: var(--akb-text-secondary);
  text-decoration: none;
  font-weight: 400;
}

.breadcrumb-link:hover {
  color: var(--akb-primary);
}

.breadcrumb-current {
  color: var(--akb-text);
  font-weight: 500;
}
</style>
