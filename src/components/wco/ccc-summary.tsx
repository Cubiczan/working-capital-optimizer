'use client'

import { TrendingUp, TrendingDown, Minus, Clock, Package, CreditCard, DollarSign } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import type { CashConversionCycle } from '@/lib/wco-types'

interface CCCSummaryProps {
  ccc: CashConversionCycle
  benchmark?: { dso: number; dio: number; dpo: number; ccc: number }
}

const metrics = [
  { key: 'dso' as const, label: 'DSO', fullLabel: 'Days Sales Outstanding', icon: Clock, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20', benchmarkKey: 'dso' as const },
  { key: 'dio' as const, label: 'DIO', fullLabel: 'Days Inventory Outstanding', icon: Package, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20', benchmarkKey: 'dio' as const },
  { key: 'dpo' as const, label: 'DPO', fullLabel: 'Days Payable Outstanding', icon: CreditCard, color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/20', benchmarkKey: 'dpo' as const },
  { key: 'ccc' as const, label: 'CCC', fullLabel: 'Cash Conversion Cycle', icon: DollarSign, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', benchmarkKey: 'ccc' as const },
]

export function CCCSummary({ ccc, benchmark }: CCCSummaryProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((m) => {
        const value = ccc[m.key]
        const bench = benchmark?.[m.benchmarkKey]
        const diff = bench ? value - bench : 0
        const isWorse = m.key !== 'dpo' ? diff > 0 : diff < 0 // Higher DPO is good
        const Icon = m.icon

        return (
          <Card key={m.key} className={`${m.bg} ${m.border} border`}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {m.label}
                </span>
                <Icon className={`h-4 w-4 ${m.color}`} />
              </div>
              <div className={`text-2xl font-bold ${m.color}`}>
                {value.toFixed(1)}
                <span className="text-sm font-normal text-muted-foreground ml-1">days</span>
              </div>
              {bench && (
                <div className="flex items-center gap-1 mt-1">
                  {Math.abs(diff) < 0.5 ? (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  ) : isWorse ? (
                    <TrendingUp className="h-3 w-3 text-red-400" />
                  ) : (
                    <TrendingDown className="h-3 w-3 text-emerald-400" />
                  )}
                  <span className={`text-xs ${isWorse ? 'text-red-400' : Math.abs(diff) < 0.5 ? 'text-muted-foreground' : 'text-emerald-400'}`}>
                    {isWorse ? '+' : ''}{diff.toFixed(1)} vs {bench}d benchmark
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
