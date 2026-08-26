import { createRouter, createWebHistory } from 'vue-router'

import FarmView from '@/views/FarmView.vue'
import MarketView from '@/views/MarketView.vue'
import PartnersView from '@/views/PartnersView.vue'
import GatheringView from '@/views/GatheringView.vue'
import CraftingView from '@/views/CraftingView.vue'
import MiningView from '@/views/MiningView.vue'
import DashboardView from '@/views/DashboardView.vue'
import CommissionsView from '@/views/CommissionsView.vue'
import PortalsView from '@/views/PortalsView.vue'
import GachaView from '@/views/GachaView.vue'

export default createRouter({
  history: createWebHistory('/red-leaf-town/'),
  routes: [
    {
      path: '/admin/crops',
      name: 'admin-crops',
      component: () => import('@/views/AdminCropsView.vue'),
      meta: { title: '作物数值', admin: true },
    },
    {
      path: '/admin/partners',
      name: 'admin-partners',
      component: () => import('@/views/AdminPartnersView.vue'),
      meta: { title: '伙伴管理', admin: true },
    },
    {
      path: '/admin/mail',
      name: 'admin-mail',
      component: () => import('@/views/AdminMailView.vue'),
      meta: { title: '镇邮局', admin: true },
    },
    {
      path: '/admin/story',
      name: 'admin-story',
      component: () => import('@/views/AdminStoryView.vue'),
      meta: { title: '剧情素材', admin: true },
    },
    { path: '/', name: 'dashboard', component: DashboardView, meta: { title: '总览' } },
    { path: '/farm', name: 'farm', component: FarmView, meta: { title: '农场' } },
    { path: '/gathering', name: 'gathering', component: GatheringView, meta: { title: '采集' } },
    { path: '/crafting', name: 'crafting', component: CraftingView, meta: { title: '加工' } },
    { path: '/mining', name: 'mining', component: MiningView, meta: { title: '矿产' } },
    // 水产还在第二里程碑的交付过程里，先只留 URL 入口，不进左侧菜单和 Dashboard。
    {
      path: '/aquatic',
      name: 'aquatic',
      component: () => import('@/views/AquaticView.vue'),
      meta: { title: '水产' },
    },
    { path: '/commissions', name: 'commissions', component: CommissionsView, meta: { title: '今日委托' } },
    { path: '/portals', name: 'portals', component: PortalsView, meta: { title: '传送门' } },
    { path: '/gacha', name: 'gacha', component: GachaView, meta: { title: '异界招募' } },
    { path: '/market', name: 'market', component: MarketView, meta: { title: '商店' } },
    { path: '/shop', redirect: { name: 'market' } },
    { path: '/inventory', redirect: { name: 'market', query: { tab: 'sell' } } },
    { path: '/partners/:partnerId?', name: 'partners', component: PartnersView, meta: { title: '伙伴仓库' } },
    { path: '/spirits/:partnerId?', redirect: (to) => ({ name: 'partners', params: { partnerId: to.params.partnerId } }) },
    { path: '/admin/spirits', redirect: { name: 'admin-partners' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
