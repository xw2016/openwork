// 全局应用状态
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const globalLoading = ref(false)
  const darkMode = ref<boolean>(
    localStorage.getItem('darkMode') === 'true'
  )

  function setGlobalLoading(val: boolean) {
    globalLoading.value = val
  }

  function toggleDarkMode() {
    darkMode.value = !darkMode.value
    localStorage.setItem('darkMode', String(darkMode.value))
  }

  return {
    globalLoading,
    darkMode,
    setGlobalLoading,
    toggleDarkMode,
  }
})
