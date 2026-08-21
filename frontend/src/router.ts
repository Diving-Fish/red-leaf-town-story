import { createRouter, createWebHistory } from 'vue-router'

import FarmView from '@/views/FarmView.vue'
import InventoryView from '@/views/InventoryView.vue'
import ShopView from '@/views/ShopView.vue'

export default createRouter({
  history: createWebHistory('/red-leaf-town/'),
  routes: [
    { path: '/', name: 'farm', component: FarmView, meta: { title: '农场' } },
    { path: '/shop', name: 'shop', component: ShopView, meta: { title: '种子商店' } },
    { path: '/inventory', name: 'inventory', component: InventoryView, meta: { title: '仓库' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
