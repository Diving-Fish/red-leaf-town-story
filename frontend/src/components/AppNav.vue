<script setup lang="ts">
import { computed } from 'vue'
import { Menu } from 'lucide-vue-next'

import { unlockedNavItems, type NavItem } from '@/lib/navigation'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ variant: 'rail' | 'bar' }>()
const emit = defineEmits<{ (event: 'navigate'): void; (event: 'more'): void }>()
const game = useGameStore()

const available = computed(() => unlockedNavItems(game.state || null))
const items = computed(() => (props.variant === 'bar' ? available.value.filter((item) => item.primary) : available.value))
const hiddenReady = computed(() =>
  available.value.filter((item) => !item.primary).reduce(
    (total, item) => total + (item.readyGroup ? game.readyCounts[item.readyGroup] : 0),
    0,
  ),
)

function badge(item: NavItem) {
  return item.readyGroup ? game.readyCounts[item.readyGroup] : 0
}
</script>

<template>
  <nav class="app-nav" :class="[`app-nav--${variant}`, { 'app-nav--tiles': variant === 'rail' }]" aria-label="游戏功能">
    <RouterLink v-for="item in items" :key="item.to" :to="item.to" @click="emit('navigate')">
      <span class="nav-icon">
        <component :is="item.icon" :size="20" />
        <i v-if="badge(item)" class="nav-badge">{{ badge(item) }}</i>
      </span>
      <span class="nav-label">{{ item.label }}</span>
    </RouterLink>
    <button v-if="variant === 'bar'" type="button" @click="emit('more')">
      <span class="nav-icon">
        <Menu :size="20" />
        <i v-if="hiddenReady" class="nav-badge">{{ hiddenReady }}</i>
      </span>
      <span class="nav-label">更多</span>
    </button>
  </nav>
</template>

<style scoped>
.nav-icon { position: relative; display: grid; place-items: center; }
.nav-badge {
  position: absolute;
  right: -9px;
  top: -6px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  color: #1d2419;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
  border-radius: 99px;
  background: var(--gold);
}
.app-nav--rail { display: grid; gap: 6px; }
.app-nav--rail a {
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 48px;
  padding: 0 14px;
  color: #abb6ab;
  border-radius: 12px;
  transition: .2s;
}
.app-nav--rail a:hover { color: var(--cream); background: #ffffff0a; }
.app-nav--rail a.router-link-active {
  color: #f6efe1;
  background: linear-gradient(90deg, rgba(119, 153, 91, .2), rgba(119, 153, 91, .07));
  box-shadow: inset 3px 0 var(--leaf);
}
/* 桌面与移动抽屉共用紧凑的功能按钮。 */
.app-nav--rail.app-nav--tiles {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-content: start;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 0;
}
.app-nav--rail.app-nav--tiles a {
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  min-height: 76px;
  padding: 12px 4px;
  color: #abb9ab;
  font-size: 12px;
  line-height: 1.2;
  text-align: center;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, .025);
}
.app-nav--rail.app-nav--tiles a:hover {
  color: var(--cream);
  border-color: #b4c59a50;
  background: #b4c59a0c;
}
.app-nav--rail.app-nav--tiles a.router-link-active {
  color: #e5f1cb;
  border-color: #9cb67a80;
  background: linear-gradient(150deg, #647e3c40, #35452b35);
  box-shadow: inset 0 1px #d0e7a51a;
}
.app-nav--tiles .nav-label { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.app-nav--tiles .nav-badge { font-size: 12px; }
.app-nav--bar { display: none; }
@media (max-width: 760px) {
  /* 抽屉里的导航在手机上改成网格瓷砖，12 个入口才放得下。 */
  .app-nav--rail { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .app-nav--rail a {
    flex-direction: column;
    justify-content: center;
    gap: 7px;
    min-height: 76px;
    padding: 10px 4px;
    font-size: 12px;
    line-height: 1.2;
    text-align: center;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, .02);
  }
  .app-nav--rail a.router-link-active {
    background: linear-gradient(160deg, rgba(119, 153, 91, .26), rgba(119, 153, 91, .08));
    border-color: color-mix(in srgb, var(--leaf) 45%, transparent);
    box-shadow: none;
  }
  .app-nav--rail .nav-label { display: block; width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .app-nav--bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 60;
    display: flex;
    padding: 6px 4px calc(6px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--line);
    background-color: #151e19;
  }
  .app-nav--bar a, .app-nav--bar button {
    flex: 1 1 0;
    min-width: 0;
    min-height: 52px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    color: #7e8a81;
    font-size: 12px;
    border: 0;
    background: transparent;
  }
  .app-nav--bar a.router-link-active { color: var(--leaf-bright); }
}
</style>
