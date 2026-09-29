import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import HomeView from '@/views/HomeView.vue'
import { ANALYSIS_PAGE_PATHS, beginAnalysisPageNavigation, dismissAnalysisPageNavigation, prepareAnalysisPage } from '@/composables/prepareAnalysisPage'

const routes = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'Home', component: HomeView },
      { path: 'dispersao-beneficio', component: () => import('@/views/BenefitDispersionView.vue') },
      { path: 'municipios', name: 'Municipalities', component: () => import('@/views/MunicipalView.vue'), meta: { pageLabel: 'Municípios' } },
      { path: 'estabelecimentos', name: 'Establishments', component: () => import('@/views/EstablishmentsView.vue'), meta: { pageLabel: 'Estabelecimentos' } },
      { path: 'estabelecimentos/:cnpj', name: 'EstablishmentDetail', component: () => import('@/views/CnpjDetailView.vue') },
      { path: 'analises', name: 'Analyses', component: () => import('@/views/AnalysesView.vue'), meta: { pageLabel: 'Análises' } },
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

router.beforeEach((to, from) => {
  if (ANALYSIS_PAGE_PATHS.includes(to.path) && to.path !== from.path) {
    beginAnalysisPageNavigation(to.path)
  } else if (!ANALYSIS_PAGE_PATHS.includes(to.path) && from.matched.length) {
    dismissAnalysisPageNavigation()
  }
})

router.beforeResolve(async (to, from) => {
  if (!ANALYSIS_PAGE_PATHS.includes(to.path) || to.path === from.path || !from.matched.length) return;
  try {
    await prepareAnalysisPage(to.path);
  } catch {
    return false;
  }
})

export default router
