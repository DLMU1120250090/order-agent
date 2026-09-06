import { defineStore } from 'pinia'
import { ref } from 'vue'
import { memoryApi } from '@/api/memory'
import type { UserProfile, TripEpisode, DistillReport } from '@/types/memory'

export const useMemoryStore = defineStore('memory', () => {
  const profile = ref<UserProfile | null>(null)
  const episodes = ref<TripEpisode[]>([])
  const distillReport = ref<DistillReport | null>(null)
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isDistilling = ref(false)
  const showEditDrawer = ref(false)

  async function fetchProfile() {
    try {
      profile.value = await memoryApi.getProfile()
    } catch (err) {
      console.error('[MemoryStore] Failed to fetch profile:', err)
    }
  }

  async function updateProfile(payload: Partial<UserProfile>) {
    isSaving.value = true
    try {
      const updated = await memoryApi.updateProfile(payload)
      profile.value = updated
      showEditDrawer.value = false
      return updated
    } catch (err) {
      console.error('[MemoryStore] Failed to update profile:', err)
      throw err
    } finally {
      isSaving.value = false
    }
  }

  async function fetchEpisodes() {
    try {
      episodes.value = await memoryApi.listEpisodes(50)
    } catch (err) {
      console.error('[MemoryStore] Failed to fetch episodes:', err)
      episodes.value = []
    }
  }

  async function fetchDistillReport() {
    try {
      distillReport.value = await memoryApi.getDistillReport()
    } catch (err) {
      console.error('[MemoryStore] Failed to fetch distill report:', err)
    }
  }

  async function triggerDistill() {
    isDistilling.value = true
    try {
      const res = await memoryApi.triggerDistill()
      distillReport.value = res
      return res
    } catch (err) {
      console.error('[MemoryStore] Failed to trigger distill:', err)
      throw err
    } finally {
      isDistilling.value = false
    }
  }

  async function fetchAll() {
    isLoading.value = true
    try {
      await Promise.allSettled([
        fetchProfile(),
        fetchEpisodes(),
        fetchDistillReport(),
      ])
    } finally {
      isLoading.value = false
    }
  }

  return {
    profile,
    episodes,
    distillReport,
    isLoading,
    isSaving,
    isDistilling,
    showEditDrawer,
    fetchProfile,
    updateProfile,
    fetchEpisodes,
    fetchDistillReport,
    triggerDistill,
    fetchAll,
  }
})
