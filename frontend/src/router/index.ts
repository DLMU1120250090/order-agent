import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '@/views/Chat.vue'
import MemoryView from '@/views/Memory.vue'
import TraceView from '@/views/Trace.vue'
import EvaluationView from '@/views/Evaluation.vue'
import OrderView from '@/views/Order.vue'

const routes = [
  {
    path: '/',
    redirect: '/travel/chat',
  },
  {
    path: '/travel',
    redirect: '/travel/chat',
  },
  {
    path: '/travel/chat',
    name: 'chat',
    component: ChatView,
  },
  {
    path: '/travel/memory',
    alias: ['/memory'],
    name: 'memory',
    component: MemoryView,
  },
  {
    path: '/travel/profile',
    redirect: '/travel/memory',
  },
  {
    path: '/admin/traces',
    alias: ['/traces'],
    name: 'trace',
    component: TraceView,
  },
  {
    path: '/admin/evaluations',
    name: 'evaluation',
    component: EvaluationView,
  },
  {
    path: '/travel/orders',
    name: 'orders',
    component: OrderView,
  },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
