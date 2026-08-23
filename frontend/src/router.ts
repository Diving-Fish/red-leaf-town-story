import { createRouter, createWebHistory } from 'vue-router'

import FarmView from '@/views/FarmView.vue'
import InventoryView from '@/views/InventoryView.vue'
import ShopView from '@/views/ShopView.vue'
import PartnersView from '@/views/PartnersView.vue'
import GatheringView from '@/views/GatheringView.vue'
import CraftingView from '@/views/CraftingView.vue'
import MiningView from '@/views/MiningView.vue'
import DashboardView from '@/views/DashboardView.vue'

export default createRouter({
  history: createWebHistory('/red-leaf-town/'),
  routes: [
    {
      path: '/admin/partners',
      name: 'admin-partners',
      component: () => import('@/views/AdminPartnersView.vue'),
      meta: { title: '伙伴管理', admin: true },
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
    { path: '/shop', name: 'shop', component: ShopView, meta: { title: '种子商店' } },
    { path: '/inventory', name: 'inventory', component: InventoryView, meta: { title: '仓库' } },
    { path: '/partners/:partnerId?', name: 'partners', component: PartnersView, meta: { title: '伙伴仓库' } },
    { path: '/spirits/:partnerId?', redirect: (to) => ({ name: 'partners', params: { partnerId: to.params.partnerId } }) },
    { path: '/admin/spirits', redirect: { name: 'admin-partners' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
