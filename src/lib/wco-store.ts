import { create } from 'zustand'
import type { AnalysisReport, EvalResult, Recommendation, HealthResponse } from './wco-types'
import { getSampleData } from './wco-sample-data'

const BACKEND_URL = process.env.NEXT_PUBLIC_WCO_BACKEND_URL || 'http://localhost:8000'

interface WCOStore {
  // State
  analysisResult: AnalysisReport | null
  isAnalyzing: boolean
  error: string | null
  recommendations: Recommendation[]
  evaluations: EvalResult[]
  backendHealth: HealthResponse | null

  // Actions
  runAnalysis: () => Promise<void>
  evaluateRecommendation: (rec: Recommendation) => Promise<void>
  fetchRecommendations: () => Promise<void>
  fetchEvaluations: () => Promise<void>
  checkHealth: () => Promise<void>
  reset: () => void
}

export const useWCOStore = create<WCOStore>((set, get) => ({
  analysisResult: null,
  isAnalyzing: false,
  error: null,
  recommendations: [],
  evaluations: [],
  backendHealth: null,

  runAnalysis: async () => {
    set({ isAnalyzing: true, error: null })
    try {
      const sample = getSampleData()
      const res = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sample),
      })
      if (!res.ok) throw new Error(`Backend returned ${res.status}`)
      const data: AnalysisReport = await res.json()
      const recs: Recommendation[] = data.recommendations || []
      set({ analysisResult: data, recommendations: recs, isAnalyzing: false })
    } catch (err) {
      set({ error: (err as Error).message, isAnalyzing: false })
    }
  },

  evaluateRecommendation: async (rec: Recommendation) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recommendation: rec.recommendation,
          context: get().analysisResult?.problem || 'Working capital optimization',
          agent_name: rec.agent,
        }),
      })
      if (!res.ok) throw new Error(`Eval returned ${res.status}`)
      const evalResult: EvalResult = await res.json()
      set((s) => ({ evaluations: [...s.evaluations, evalResult] }))
    } catch {
      // silent fail for eval
    }
  },

  fetchRecommendations: async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/recommendations?limit=50`)
      if (!res.ok) return
      const data = await res.json()
      set({ recommendations: data.recommendations || [] })
    } catch {
      // silent
    }
  },

  fetchEvaluations: async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/evaluations?limit=50`)
      if (!res.ok) return
      const data = await res.json()
      set({ evaluations: data.evaluations || [] })
    } catch {
      // silent
    }
  },

  checkHealth: async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/health`)
      if (!res.ok) { set({ backendHealth: null }); return }
      const data: HealthResponse = await res.json()
      set({ backendHealth: data })
    } catch {
      set({ backendHealth: null })
    }
  },

  reset: () => {
    set({
      analysisResult: null,
      isAnalyzing: false,
      error: null,
      recommendations: [],
      evaluations: [],
    })
  },
}))
