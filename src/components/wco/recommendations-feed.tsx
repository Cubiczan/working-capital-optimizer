'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Recommendation } from '@/lib/wco-types'

const AGENT_COLORS: Record<string, string> = {
  'AR Agent': 'border-l-blue-500',
  'AP Agent': 'border-l-purple-500',
  'Inventory Agent': 'border-l-amber-500',
  'CashFlow Agent': 'border-l-emerald-500',
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

interface RecommendationsFeedProps {
  recommendations: Recommendation[]
}

export function RecommendationsFeed({ recommendations }: RecommendationsFeedProps) {
  if (!recommendations.length) return null

  // Group by agent
  const grouped = recommendations.reduce<Record<string, Recommendation[]>>((acc, rec) => {
    const agent = rec.agent || 'Unknown'
    if (!acc[agent]) acc[agent] = []
    acc[agent].push(rec)
    return acc
  }, {})

  return (
    <Card className="bg-slate-900/50 border border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Recommendations
          </CardTitle>
          <Badge variant="secondary" className="text-xs">
            {recommendations.length} total
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-4">
        {Object.entries(grouped).map(([agent, recs]) => (
          <div key={agent}>
            <p className="text-xs font-semibold text-muted-foreground mb-2">{agent}</p>
            <div className="space-y-2">
              {recs.map((rec, i) => (
                <div
                  key={i}
                  className={`bg-slate-800/40 border-l-2 ${AGENT_COLORS[rec.agent] || 'border-l-slate-500'} rounded-r-lg p-3 space-y-1`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs text-slate-300 leading-relaxed">{rec.insight}</p>
                    <ConfidenceBadge confidence={rec.confidence} />
                  </div>
                  <p className="text-xs text-emerald-400 font-medium">{rec.recommendation}</p>
                  {rec.expected_impact && (
                    <p className="text-[11px] text-muted-foreground">{rec.expected_impact}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
