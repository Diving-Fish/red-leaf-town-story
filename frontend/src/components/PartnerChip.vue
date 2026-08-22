<script setup lang="ts">
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import type { OwnedPartner } from '@/types'

withDefaults(defineProps<{ partner?: OwnedPartner | null; title?: string; subtitle?: string; size?: number }>(), {
  size: 32,
})
</script>

<template>
  <span class="partner-chip">
    <PartnerAvatar :artwork="partner?.artwork" :crop="partner?.avatar_crop" :name="partner?.name" :size="size" />
    <span class="partner-chip-copy">
      <strong>{{ partner?.name || title }}</strong>
      <small v-if="subtitle">{{ subtitle }}</small>
    </span>
  </span>
</template>

<style scoped>
.partner-chip { min-width: 0; display: flex; align-items: center; gap: 9px; text-align: left; }
.partner-chip-copy { min-width: 0; }
.partner-chip strong, .partner-chip small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.partner-chip strong { font-size: 13px; }
.partner-chip small { margin-top: 2px; color: #7b867d; font-size: 12px; }
</style>
