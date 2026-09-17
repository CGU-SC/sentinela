import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import HomeView from '@/views/HomeView.vue'

const routes = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'Home', component: HomeView },
      { path: 'dispersao-beneficio', component: () => import('@/views/BenefitDispersionView.vue') },
      { path: 'municipios', name: 'Municipalities', component: () => import('@/views/MunicipalView.vue') },
      { path: 'estabelecimentos', name: 'Establishments', component: () => import('@/views/EstablishmentsView.vue') },
      { path: 'estabelecimentos/:cnpj', name: 'EstablishmentDetail', component: () => import('@/views/CnpjDetailView.vue') },
      { path: 'analises', name: 'Analyses', component: () => import('@/views/AnalysesView.vue') },
      { path: 'alvos', name: 'Targets', component: () => import('@/views/TargetsView.vue') },
      
      // Redirecionamentos para legibilidade e retrocompatibilidade
      { path: 'municipio', redirect: '/municipios' },
      { path: 'cnpj', redirect: '/estabelecimentos' },
      { path: 'estabelecimento/:cnpj', redirect: to => `/estabelecimentos/${to.params.cnpj}` },
      { path: 'alvos/:pathMatch(.*)*', redirect: '/alvos' },

      { path: 'indicadores', redirect: '/estabelecimentos' },
      { path: 'regional', component: () => import('@/views/RegionalView.vue') },
      { path: 'listas', name: 'FarmaciaLists', component: () => import('@/views/lists/WatchlistView.vue') },
      { path: 'configuracoes', name: 'Settings', component: () => import('@/views/SettingsView.vue'), meta: { hideSidebar: true } },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
