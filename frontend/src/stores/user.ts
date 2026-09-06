import { defineStore } from 'pinia'
import { ref } from 'vue'

const USER_ID_KEY = 'travel.userId'

export const useUserStore = defineStore('user', () => {
  const userId = ref<number>(parseInt(localStorage.getItem(USER_ID_KEY) || '1', 10) || 1)

  function setUserId(id: number | string) {
    const parsed = Math.max(1, parseInt(String(id), 10) || 1)
    userId.value = parsed
    localStorage.setItem(USER_ID_KEY, String(parsed))
  }

  return {
    userId,
    setUserId,
  }
})
