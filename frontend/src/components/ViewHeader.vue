<script setup lang="ts">
defineProps<{ eyebrow: string; title: string }>()
</script>

<template>
  <header class="view-heading">
    <div>
      <p class="eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
    </div>
    <div v-if="$slots.chip" class="season-chip"><slot name="chip" /></div>
  </header>
</template>
