'use client'

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertTriangle } from 'lucide-react'

interface WeeklyForecast {
  week: number
  opening_balance: number
  inflows: number
  outflows: number
  net_change: number
  closing_balance: number
}

interface CashForecastChartProps {
  forecast: WeeklyForecast[]
  minCashThreshold?: number
}

function formatCurrency(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
  return `$${v.toFixed(0)}`
}

export function CashForecastChart({ forecast, minCashThreshold = 500_000 }: CashForecastChartProps) {
  if (!forecast.length) return null

  const hasRisk = forecast.some((w) => w.closing_balance < minCashThreshold)

  return (
    <Card className="bg-slate-900/50 border border-slate-700/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            13-Week Cash Forecast
          </CardTitle>
          {hasRisk && (
            <div className="flex items-center gap-1 text-red-400 text-xs">
              <AlertTriangle className="h-3 w-3" />
              Liquidity risk detected
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-[280px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={forecast} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <defs>
                <linearGradient id="closingBalance" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="inflowGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="outflowGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="week" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => `W${v}`} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={formatCurrency} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }}
                labelFormatter={(v) => `Week ${v}`}
                formatter={(value: number, name: string) => [formatCurrency(value), name]}
              />
              <ReferenceLine y={minCashThreshold} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Min Cash', fill: '#ef4444', fontSize: 10 }} />
              <Area type="monotone" dataKey="inflows" stroke="#3b82f6" fill="url(#inflowGrad)" strokeWidth={1.5} name="Inflows" />
              <Area type="monotone" dataKey="outflows" stroke="#ef4444" fill="url(#outflowGrad)" strokeWidth={1.5} name="Outflows" />
              <Area type="monotone" dataKey="closing_balance" stroke="#10b981" fill="url(#closingBalance)" strokeWidth={2} name="Closing Balance" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
