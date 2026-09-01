<script setup lang="ts">
import { Swords } from 'lucide-vue-next'

import DelveStrike from '@/components/DelveStrike.vue'
import type { DelveBattleLog } from '@/types'

/**
 * 战斗结束到结算卡出现之间的过渡。战斗一分出胜负，服务端返回的路线状态就已经指向
 * 下一个节点了，所以这段时间必须有人占住位置，否则会先闪一下下一节点的事件卡。
 */
defineProps<{ strike: DelveBattleLog | null; friendly: boolean; replaying: boolean }>()

const emit = defineEmits<{ (event: 'skip'): void }>()
</script>

<template>
  <article class="settling-card surface-card">
    <header class="settling-heading">
      <span class="settling-icon"><Swords :size="21" /></span>
      <div>
        <small class="ui-kicker">战斗结束</small>
        <h2 class="ui-section-title">正在结算</h2>
      </div>
    </header>

    <div class="strike-stage">
      <DelveStrike v-if="strike" :key="`${strike.actor}:${strike.text}`" :log="strike" :friendly="friendly" />
      <p v-else class="strike-waiting"><i /><span>正在收拢这一节点的结果…</span></p>
    </div>

    <button v-if="replaying" class="text-button skip-button" @click="emit('skip')">跳过结算</button>
  </article>
</template>

<style scoped>
.settling-card { display: grid; gap: 13px; padding: 20px; border-color: color-mix(in srgb, var(--autumn) 28%, var(--line)); }
.settling-heading { display: flex; align-items: center; gap: 12px; }
.settling-icon { width: 42px; height: 42px; display: grid; place-items: center; color: #f0c48e; border-radius: 14px 5px 14px 5px; background: #d79a6820; }
.settling-heading .ui-section-title { margin: 3px 0 0; }
.strike-stage { display: grid; gap: 8px; min-height: 84px; }
.strike-waiting { display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 84px; margin: 0; color: #8b978c; font-size: var(--font-copy); border: 1px dashed #ffffff12; border-radius: 4px 16px 4px 16px; }
.strike-waiting i { display: block; width: 13px; height: 13px; border: 2px solid #ffffff1f; border-top-color: var(--gold); border-radius: 50%; animation: settle-spin .7s linear infinite; }
.skip-button { justify-self: end; color: #8b978c; }
@keyframes settle-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .strike-waiting i { animation-duration: 2.4s; }
}
</style>
