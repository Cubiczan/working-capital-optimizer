'use client'

import { useEffect, useState } from 'react'
import { Play, RotateCcw, Activity, Wifi, WifiOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWCOStore } from '@/lib/wco-store'
import { CCCSummary } from '@/components/wco/ccc-summary'
import { CashForecastChart } from '@/components/wco/cash-forecast-chart'
import { AgentPipeline } from '@/components/wco/agent-pipeline'
import { RecommendationsFeed } from '@/components/wco/recommendations-feed'
import { EvalScoresPanel } from '@/components/wco/eval-scores-panel'
import type { TurnResult, WeeklyForecast } from '@/lib/wco-types'

export default function Home() {
  const {
    analysisResult, isAnalyzing, error,
    recommendations, evaluations, backendHealth,
    runAnalysis, checkHealth, reset,
  } = useWCOStore()

  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    checkHealth()
    const interval = setInterval(checkHealth, 15000)
    return () => clearInterval(interval)
  }, [checkHealth])

  const handleRun = () => {
    if (!mounted) return
    reset()
    runAnalysis()
  }

  const turns: TurnResult[] = analysisResult?.turns || []
  const forecast: WeeklyForecast[] = []
  const minCashThreshold = 500_000

  // Extract forecast from cashflow agent raw data if available
  if (analysisResult) {
    const cashflowTurn = turns.find((t) => t.capability === 'cashflow')
    if (cashflowTurn?.raw_compress_response) {
      try {
        const jsonStr = cashflowTurn.raw_compress_response.match(/\{[\s\S]*\}/)?.[0] || ''
        const parsed = JSON.parse(jsonStr)
        if (parsed.weekly_forecast) forecast.push(...parsed.weekly_forecast)
      } catch { /* no-op */ }
    }
  }

  const isOnline = backendHealth?.status === 'ok'

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white font-bold text-xs">
                  W
                </div>
                <h1 className="text-sm font-semibold tracking-tight">Working Capital Optimizer</h1>
              </div>
              <span className="hidden sm:inline text-xs text-muted-foreground border-l border-slate-700 pl-3">
                Multi-Agent AI for CFO Intelligence
              </span>
            </div>
            <div className="flex items-center gap-3">
              {/* Backend status */}
              <div className="flex items-center gap-1.5 text-xs">
                {isOnline ? (
                  <Wifi className="h-3 w-3 text-emerald-400" />
                ) : (
                  <WifiOff className="h-3 w-3 text-red-400" />
                )}
                <span className={isOnline ? 'text-emerald-400' : 'text-red-400'}>
                  {isOnline ? 'Backend Connected' : 'Backend Offline'}
                </span>
              </div>
              <Button
                size="sm"
                onClick={handleRun}
                disabled={isAnalyzing}
                className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
              >
                {isAnalyzing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {isAnalyzing ? 'Analyzing...' : 'Run Analysis'}
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-sm text-red-400">
            Analysis failed: {error}. Make sure the backend is running on port 8000.
          </div>
        )}

        {/* CCC Summary */}
        {analysisResult?.cash_conversion_cycle ? (
          <CCCSummary
            ccc={analysisResult.cash_conversion_cycle}
            benchmark={{ dso: 45, dio: 75, dpo: 50, ccc: 60 }}
          />
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {['DSO', 'DIO', 'DPO', 'CCC'].map((label) => (
              <div key={label} className="h-[96px] rounded-xl bg-slate-800/30 border border-slate-700/30 flex items-center justify-center">
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-lg font-bold text-slate-600">—</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 13-Week Chart + Agent Pipeline */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3">
            {forecast.length > 0 ? (
              <CashForecastChart forecast={forecast} minCashThreshold={minCashThreshold} />
            ) : (
              <div className="h-[350px] rounded-xl bg-slate-800/20 border border-slate-700/30 flex items-center justify-center">
                <div className="text-center text-muted-foreground">
                  <Activity className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">13-Week Cash Forecast</p>
                  <p className="text-xs">Run analysis to generate</p>
                </div>
              </div>
            )}
          </div>
          <div className="lg:col-span-2">
            <AgentPipeline turns={turns} isAnalyzing={isAnalyzing} />
          </div>
        </div>

        {/* Recommendations + Eval */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RecommendationsFeed recommendations={recommendations} />
          <EvalScoresPanel evaluations={evaluations} />
        </div>

        {/* Footer */}
        <footer className="text-center py-6 text-xs text-muted-foreground border-t border-slate-800">
          <p>Working Capital Optimizer — Google Cloud Rapid Agent Hackathon — Arize Resources Track</p>
          <p className="mt-1">Traced with OpenInference &middot; Observed by Arize Phoenix Cloud &middot; Powered by Gemini 2.5 Flash</p>
        </footer>
      </main>
    </div>
  )
}
