'use client'

import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { EvalResult, EvalScore } from '@/lib/wco-types'

const DIMENSION_COLORS: Record<string, string> = {
  relevance: '#3b82f6',
  actionability: '#10b981',
  financial_impact: '#f59e0b',
  risk_awareness: '#8b5cf6',
}

function ScoreBar({ score }: { score: EvalResult }) {
  const data = score.scores.map((s: EvalScore) => ({ ...s, fill: DIMENSION_COLORS[s.dimension] || '#64748b' }))
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300 truncate max-w-[200px]">
          {score.recommendation_text.slice(0, 60)}...
        </span>
        <Badge variant={score.overall_score >= 7 ? 'default' : 'secondary'} className={`text-xs ${score.overall_score >= 7 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
          {score.overall_score.toFixed(1)}
        </Badge>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {data.map((d: EvalScore & { fill: string }) => (
          <div key={d.dimension} className="text-center">
            <div className="text-lg font-bold" style={{ color: d.fill }}>
              {d.score}
            </div>
            <div className="text-[10px] text-muted-foreground capitalize">
              {d.dimension.replace('_', ' ')}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface EvalScoresPanelProps {
  evaluations: EvalResult[]
}

export function EvalScoresPanel({ evaluations }: EvalScoresPanelProps) {
  if (!evaluations.length) return null

  const radarData = evaluations.length > 0
    ? ['relevance', 'actionability', 'financial_impact', 'risk_awareness'].map((dim) => {
        const scores = evaluations
          .map((e) => e.scores.find((s) => s.dimension === dim)?.score || 0)
        const avg = scores.reduce((a, b) => a + b, 0) / scores.length
        return { dimension: dim.replace('_', ' '), score: Math.round(avg * 10) / 10, fullMark: 10 }
      })
    : []

  const barData = evaluations.map((e) => ({
    agent: e.agent_name.replace(' Agent', ''),
    overall: e.overall_score,
    fill: e.overall_score >= 7 ? '#10b981' : e.overall_score >= 5 ? '#f59e0b' : '#ef4444',
  }))

  return (
    <Card className="bg-slate-900/50 border border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            LLM-as-Judge Evaluation
          </CardTitle>
          <Badge variant="secondary" className="text-xs">
            Avg: {evaluations.length > 0 ? (evaluations.reduce((a, e) => a + e.overall_score, 0) / evaluations.length).toFixed(1) : 'N/A'}/10
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-4">
        {/* Radar + Bar side by side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="dimension" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <PolarRadiusAxis angle={30} domain={[0, 10]} tick={false} />
                <Radar name="Avg Score" dataKey="score" stroke="#10b981" fill="#10b981" fillOpacity={0.2} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" domain={[0, 10]} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis type="category" dataKey="agent" tick={{ fill: '#94a3b8', fontSize: 11 }} width={80} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="overall" radius={[0, 4, 4, 0]}>
                  {barData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        {/* Individual eval cards */}
        <div className="space-y-2">
          {evaluations.slice(0, 5).map((score, i) => (
            <ScoreBar key={i} score={score} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
