import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { orderApi } from '@/api/order'
import type { TravelOrder } from '@/types/order'

export const useOrderStore = defineStore('order', () => {
  const orders = ref<TravelOrder[]>([])
  const isLoading = ref(false)
  const selectedOrder = ref<TravelOrder | null>(null)
  const statusFilter = ref<string>('ALL')

  const filteredOrders = computed(() => {
    if (statusFilter.value === 'ALL') return orders.value
    return orders.value.filter(o => o.status === statusFilter.value)
  })

  async function fetchOrders() {
    isLoading.value = true
    try {
      const res = await orderApi.listOrders()
      orders.value = res || []
    } catch (err) {
      console.error('[OrderStore] Failed to list orders:', err)
      orders.value = []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchOrderDetail(orderNo: string) {
    try {
      const res = await orderApi.getOrder(orderNo)
      selectedOrder.value = res
      return res
    } catch (err) {
      console.error('[OrderStore] Failed to get order detail:', err)
      throw err
    }
  }

  return {
    orders,
    isLoading,
    selectedOrder,
    statusFilter,
    filteredOrders,
    fetchOrders,
    fetchOrderDetail,
  }
})
