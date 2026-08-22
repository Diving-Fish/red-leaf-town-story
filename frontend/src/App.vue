<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  Archive,
  BatteryCharging,
  ChevronRight,
  Coins,
  Copy,
  Leaf,
  LogOut,
  Map,
  Menu,
  RefreshCw,
  ShoppingBasket,
  Sparkles,
  Sprout,
  Trees,
  Hammer,
  UserRound,
  X,
} from 'lucide-vue-next'

import { useGameStore } from '@/stores/game'

const game = useGameStore()
const route = useRoute()
const accountOpen = ref(false)
const navOpen = ref(false)
const bindingCommand = ref('')
let pollTimer = 0

const isAdminRoute = computed(() => route.meta.admin === true)
const routeTitle = computed(() => String(route.meta.title || '红叶镇'))
const levelProgress = computed(() => {
  const player = game.player
  if (!player || !player.next_level_xp) return 100
  const currentFloor = player.current_level_xp
  return Math.max(2, Math.min(100, ((player.experience - currentFloor) / (player.next_level_xp - currentFloor)) * 100))
})
const loginUrl = computed(() => `/api/oauth/red-leaf-town/start?next=${encodeURIComponent('/red-leaf-town/')}`)
const navItems = [
  { to: '/', label: '农场', icon: Sprout },
  { to: '/gathering', label: '采集', icon: Trees },
  { to: '/crafting', label: '加工', icon: Hammer },
  { to: '/shop', label: '种子商店', icon: ShoppingBasket },
  { to: '/inventory', label: '仓库', icon: Archive },
  { to: '/partners', label: '伙伴', icon: Sparkles },
]

onMounted(async () => {
  if (isAdminRoute.value) return
  await game.initialize()
  pollTimer = window.setInterval(() => game.refresh(true), 15_000)
})
onBeforeUnmount(() => window.clearInterval(pollTimer))

async function generateBindingCode() {
  const result = await game.createBindingCode()
  if (result) bindingCommand.value = result.command
}

async function copyBindingCommand() {
  if (!bindingCommand.value) return
  await navigator.clipboard.writeText(bindingCommand.value)
  game.showNotice('指令已复制')
}
</script>

<template>
  <RouterView v-if="isAdminRoute" />

  <div v-else-if="game.status === 'checking'" class="splash-screen">
    <div class="brand-seal"><Leaf :size="42" /></div>
    <h1>红叶镇物语</h1>
    <p>正在沿着山路前往小镇……</p>
    <span class="loading-line"><i /></span>
  </div>

  <main v-else-if="game.status === 'guest' || game.status === 'error'" class="login-screen">
    <div class="login-landscape" aria-hidden="true">
      <i class="hill hill-one" /><i class="hill hill-two" /><i class="sun" />
    </div>
    <section class="login-card">
      <div class="brand-seal"><Leaf :size="38" /></div>
      <p class="eyebrow">WELCOME TO</p>
      <h1>红叶镇物语</h1>
      <p class="login-copy">在山谷的红叶落下之前，经营一片属于你的土地。离开时，时间仍会继续流动。</p>
      <p v-if="game.error" class="error-banner">{{ game.error }}</p>
      <a class="oauth-button" :href="loginUrl">
        <UserRound :size="19" />
        使用水鱼账号登录
        <ChevronRight :size="18" />
      </a>
      <small>每个水鱼账号对应一位红叶镇居民</small>
    </section>
  </main>

  <div v-else-if="game.state && game.player" class="game-shell">
    <aside class="sidebar" :class="{ open: navOpen }">
      <div class="sidebar-brand">
        <div class="brand-seal brand-seal--small"><Leaf :size="24" /></div>
        <div><strong>红叶镇物语</strong><small>RED LEAF TOWN</small></div>
        <button class="icon-button mobile-close" @click="navOpen = false"><X :size="20" /></button>
      </div>
      <nav>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" @click="navOpen = false">
          <component :is="item.icon" :size="20" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="coming-soon">
        <Map :size="18" />
        <div><strong>小镇还在扩建</strong><span>畜牧与工坊将随等级开放</span></div>
      </div>
      <button class="profile-button" @click="accountOpen = true">
        <span class="avatar">{{ game.player.display_name.slice(0, 1) }}</span>
        <span><strong>{{ game.player.display_name }}</strong><small>Lv.{{ game.player.level }} · 小镇居民</small></span>
        <ChevronRight :size="17" />
      </button>
    </aside>

    <div class="main-column">
      <header class="topbar">
        <button class="icon-button menu-button" @click="navOpen = true"><Menu :size="21" /></button>
        <div class="page-location"><small>当前位置</small><strong>{{ routeTitle }}</strong></div>
        <div class="resource-strip">
          <span class="resource-pill coins"><Coins :size="17" /><strong>{{ game.player.coins }}</strong><small>金币</small></span>
          <span class="resource-pill stamina"><BatteryCharging :size="17" /><strong>{{ game.player.stamina }}/{{ game.player.stamina_cap }}</strong><small>体力</small></span>
        </div>
        <button class="icon-button refresh-button" :disabled="game.busy" @click="game.refresh()"><RefreshCw :size="18" /></button>
      </header>

      <div class="level-ribbon">
        <span>等级 {{ game.player.level }}</span>
        <div class="level-track"><i :style="{ width: `${levelProgress}%` }" /></div>
        <small>{{ game.player.next_level_xp ? `${game.player.experience} / ${game.player.next_level_xp} XP` : '已达当前上限' }}</small>
      </div>

      <div class="page-scroll"><RouterView /></div>
    </div>

    <nav class="mobile-nav">
      <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
        <component :is="item.icon" :size="20" /><span>{{ item.label }}</span>
      </RouterLink>
      <button @click="accountOpen = true"><UserRound :size="20" /><span>账户</span></button>
    </nav>

    <div v-if="accountOpen" class="modal-backdrop" @click.self="accountOpen = false">
      <section class="account-modal">
        <button class="icon-button modal-close" @click="accountOpen = false"><X :size="20" /></button>
        <div class="account-hero">
          <span class="avatar avatar--large">{{ game.player.display_name.slice(0, 1) }}</span>
          <div><p class="eyebrow">TOWN RESIDENT</p><h2>{{ game.player.display_name }}</h2><span>居民编号 {{ game.player.player_id.slice(0, 8) }}</span></div>
        </div>
        <div class="account-section">
          <h3>QQ Bot 绑定</h3>
          <p>绑定后可以在群聊里查询农场状态。官方 Bot 使用 OpenID，不保存或依赖 QQ 号。</p>
          <p v-if="game.account?.bindings.length" class="bound-chip">已绑定：{{ game.account.bindings.join('、') }}</p>
          <template v-if="bindingCommand">
            <div class="command-box"><code>{{ bindingCommand }}</code><button @click="copyBindingCommand"><Copy :size="16" /></button></div>
            <small>请在 10 分钟内把这条指令发送给机器人。</small>
          </template>
          <button v-else class="secondary-button" :disabled="game.busy" @click="generateBindingCode">生成 QQ 绑定指令</button>
        </div>
        <button class="logout-button" @click="game.logout(); accountOpen = false"><LogOut :size="17" />退出水鱼账号</button>
      </section>
    </div>
  </div>

  <Transition name="toast"><div v-if="game.notice" class="toast">{{ game.notice }}</div></Transition>
</template>
