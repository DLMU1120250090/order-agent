import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { traceApi } from '@/api/trace'
import type { TraceRowOut, TraceEvent, TraceLabelRequest, TraceFilterParams } from '@/types/trace'

export const useTraceStore = defineStore('trace', () => {
  const traces = ref<TraceRowOut[]>([])
  const selectedTraceId = ref<string | null>(null)
  const currentTrace = ref<TraceRowOut | null>(null)
  const isLoadingList = ref(false)
  const isLoadingDetail = ref(false)

  // Filters
  const filterQuickRange = ref<'1h' | 'today' | '7d' | '30d'>('7d')
  const onlyUnlabeled = ref(false)
  const searchSessionId = ref('')
  const statusFilter = ref<'ALL' | 'SUCCESS' | 'FAILED'>('ALL')

  // Replay & Labeling
  const isReplaying = ref(false)
  const replayResult = ref<any | null>(null)
  const showReplayDrawer = ref(false)
  const showLabelModal = ref(false)
  const isLabeling = ref(false)
  const highlightedStepOrder = ref<number | null>(null)

  function highlightStep(stepOrder: number) {
    highlightedStepOrder.value = stepOrder
    setTimeout(() => {
      if (highlightedStepOrder.value === stepOrder) {
        highlightedStepOrder.value = null
      }
    }, 4000)
  }

  // Events of current selected trace
  const currentEvents = computed<TraceEvent[]>(() => {
    if (!currentTrace.value || !currentTrace.value.traceJson) return []
    let raw = currentTrace.value.traceJson
    if (typeof raw === 'string') {
      try {
        raw = JSON.parse(raw)
      } catch {
        return []
      }
    }
    if (Array.isArray(raw)) {
      return [...raw].sort((a, b) => (a.stepOrder || 0) - (b.stepOrder || 0))
    }
    if (typeof raw === 'object' && Array.isArray((raw as any).events)) {
      return [...(raw as any).events].sort((a, b) => (a.stepOrder || 0) - (b.stepOrder || 0))
    }
    return []
  })

  // Filtered Trace List in Frontend
  const filteredTraces = computed(() => {
    return traces.value.filter((t) => {
      if (onlyUnlabeled.value) {
        if (t.expectedIntent || t.expectedClarifyAction || t.expectedSlots) {
          return false
        }
      }
      if (statusFilter.value !== 'ALL') {
        if (t.status !== statusFilter.value) return false
      }
      if (searchSessionId.value.trim()) {
        const query = searchSessionId.value.trim().toLowerCase()
        const sid = (t.sessionId || '').toLowerCase()
        const tid = (t.traceId || '').toLowerCase()
        if (!sid.includes(query) && !tid.includes(query)) return false
      }
      return true
    })
  })

  // Summary Metrics of Current Trace
  const summaryMetrics = computed(() => {
    const evs = currentEvents.value
    let totalTokens = 0
    let totalLatency = currentTrace.value?.durationMs || 0
    const agents = new Set<string>()

    for (const e of evs) {
      if (e.totalTokens) totalTokens += e.totalTokens
      if (e.agentName) agents.add(e.agentName)
      if (!currentTrace.value?.durationMs && e.latencyMs) {
        totalLatency += e.latencyMs
      }
    }

    return {
      eventCount: evs.length,
      totalTokens,
      totalLatency,
      agents: Array.from(agents),
      hasError: currentTrace.value?.status === 'FAILED' || evs.some(e => !!e.errorMessage),
    }
  })

  // Fetch Trace List
  async function fetchTraces() {
    isLoadingList.value = true
    try {
      const now = new Date()
      let startAt: Date
      const endAt = now

      if (filterQuickRange.value === '1h') {
        startAt = new Date(now.getTime() - 60 * 60 * 1000)
      } else if (filterQuickRange.value === 'today') {
        startAt = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      } else if (filterQuickRange.value === '30d') {
        startAt = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      } else {
        // 7d default
        startAt = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      }

      const params: TraceFilterParams = {
        startAt: startAt.toISOString(),
        endAt: endAt.toISOString(),
        onlyUnlabeled: onlyUnlabeled.value,
        limit: 100,
      }

      const list = await traceApi.listTraces(params)
      traces.value = list || []

      // If previously selected trace is in list or exists, keep or select first
      if (traces.value.length > 0) {
        if (!selectedTraceId.value || !traces.value.some(t => t.traceId === selectedTraceId.value)) {
          await selectTrace(traces.value[0].traceId)
        }
      } else {
        selectedTraceId.value = null
        currentTrace.value = null
      }
    } catch (err) {
      console.error('[TraceStore] Failed to fetch traces:', err)
      traces.value = []
    } finally {
      isLoadingList.value = false
    }
  }

  // Select a Trace
  async function selectTrace(traceId: string) {
    if (!traceId) return
    selectedTraceId.value = traceId
    isLoadingDetail.value = true
    try {
      const detail = await traceApi.getTrace(traceId)
      currentTrace.value = detail
    } catch (err) {
      console.error('[TraceStore] Failed to get trace detail:', err)
    } finally {
      isLoadingDetail.value = false
    }
  }

  // Replay Trace
  async function runReplay(traceId?: string) {
    const tid = traceId || selectedTraceId.value
    if (!tid) return
    isReplaying.value = true
    replayResult.value = null
    showReplayDrawer.value = true
    try {
      const res = await traceApi.replayTrace(tid)
      replayResult.value = res
      return res
    } catch (err) {
      console.error('[TraceStore] Replay failed:', err)
      throw err
    } finally {
      isReplaying.value = false
    }
  }

  // Label Trace
  async function submitLabel(traceId: string, payload: TraceLabelRequest) {
    isLabeling.value = true
    try {
      await traceApi.labelTrace(traceId, payload)
      // Update locally
      if (currentTrace.value && currentTrace.value.traceId === traceId) {
        currentTrace.value.expectedIntent = payload.expectedIntent
        currentTrace.value.expectedClarifyAction = payload.expectedClarifyAction
        currentTrace.value.expectedSlots = payload.expectedSlots
        currentTrace.value.labelNote = payload.labelNote
        currentTrace.value.labeledAt = new Date().toISOString()
      }
      const item = traces.value.find(t => t.traceId === traceId)
      if (item) {
        item.expectedIntent = payload.expectedIntent
        item.expectedClarifyAction = payload.expectedClarifyAction
        item.expectedSlots = payload.expectedSlots
        item.labelNote = payload.labelNote
        item.labeledAt = new Date().toISOString()
      }
      showLabelModal.value = false
    } catch (err) {
      console.error('[TraceStore] Submit label failed:', err)
      throw err
    } finally {
      isLabeling.value = false
    }
  }

  return {
    traces,
    selectedTraceId,
    currentTrace,
    isLoadingList,
    isLoadingDetail,
    filterQuickRange,
    onlyUnlabeled,
    searchSessionId,
    statusFilter,
    isReplaying,
    replayResult,
    showReplayDrawer,
    showLabelModal,
    isLabeling,
    highlightedStepOrder,
    highlightStep,
    currentEvents,
    filteredTraces,
    summaryMetrics,
    fetchTraces,
    selectTrace,
    runReplay,
    submitLabel,
  }
})
