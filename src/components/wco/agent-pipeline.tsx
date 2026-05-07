'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Clock, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { TurnResult, CompressionStep } from '@/lib/wco-types'

const AGENT_META: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  'accounts_receivable': { label: 'AR Agent', color: 'text-blue-400', bg: 'bg-blue-500/10', icon: '🔄' },
  'accounts_payable': { label: 'AP Agent', color: 'text-purple-400', bg: 'bg-purple-500/10', icon: '💳' },
  'inventory': { label: 'Inventory Agent', color: 'text-amber-400', bg: 'bg-amber-500/10', icon: '📦' },
  'cashflow': { label: 'Cash Flow Agent', color: 'text-emerald-400', bg: 'bg-emerald-500/10', icon: '💰' },
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const variants: Record<string, string> = {
    high: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    medium: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    low: 'bg-red-500/20 text-red-400 border-red-500/30',
  }
  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${variants[confidence] || variants.medium}`}>
      {confidence}
    </Badge>
  )
}

function TurnCard({ turn }: { turn: TurnResult }) {
  const [expanded, setExpanded] = useState(false)
  const meta = AGENT_META[turn.capability] || AGENT_META.cashflow

  return (
    <Card className={`${meta.bg} border border-slate-700/50 transition-all`}>
      <CardHeader className="py-3 px-4 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">{meta.icon}</span>
            <span className={`font-semibold text-sm ${meta.color}`}>{turn.agent_name}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {turn.duration_ms.toFixed(0)}ms
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Zap className="h-3 w-3" />
              {turn.compression_steps.length} recs
            </div>
            {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
          </div>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0 px-4 pb-4 space-y-3">
          {/* Expansion Steps */}
          {turn.expansion_steps.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1.5">ANALYSIS STEPS</p>
              <div className="space-y-1">
                {turn.expansion_steps.map((step, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="text-muted-foreground font-mono mt-0.5 shrink-0">{i + 1}.</span>
                    <span className="text-slate-300">{step.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Compression Steps */}
          {turn.compression_steps.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1.5">RECOMMENDATIONS</p>
              <div className="space-y-2">
                {turn.compression_steps.map((step: CompressionStep, i: number) => (
                  <div key={i} className="bg-slate-800/50 rounded-lg p-3 space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs text-slate-200">{step.insight}</p>
                      <ConfidenceBadge confidence={step.confidence} />
                    </div>
                    <p className="text-xs text-emerald-400">{step.recommendation}</p>
                    {step.expected_impact && (
                      <p className="text-xs text-muted-foreground">Impact: {step.expected_impact}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Grounding */}
          {turn.grounding_check && (
            <div className="flex items-center gap-2 text-xs">
              <span className={turn.grounding_check.is_grounded ? 'text-emerald-400' : 'text-red-400'}>
                {turn.grounding_check.is_grounded ? '✓ Grounded' : '⚠ Not grounded'}
              </span>
              <span className="text-muted-foreground">
                ({turn.grounding_check.data_points_referenced} data points)
              </span>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

interface AgentPipelineProps {
  turns: TurnResult[]
  isAnalyzing: boolean
}

export function AgentPipeline({ turns, isAnalyzing }: AgentPipelineProps) {
  return (
    <div>
      <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
        Agent Pipeline
        {isAnalyzing && (
          <span className="ml-2 text-blue-400 animate-pulse">Analyzing...</span>
        )}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {turns.map((turn, i) => (
          <TurnCard key={i} turn={turn} />
        ))}
        {turns.length === 0 && !isAnalyzing && (
          <div className="col-span-2 text-center py-8 text-muted-foreground text-sm">
            Run an analysis to see agent results
          </div>
        )}
      </div>
    </div>
  )
}
