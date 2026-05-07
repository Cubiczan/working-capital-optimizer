/** TypeScript types for the WCO agent mesh. */

export interface ARInvoice {
  invoice_id: string
  customer_id: string
  customer_name: string
  amount: number
  issue_date: string
  due_date: string
  payment_terms_days: number
  days_outstanding: number
  aging_bucket: string
  payment_status: string
}

export interface APInvoice {
  invoice_id: string
  vendor_id: string
  vendor_name: string
  amount: number
  invoice_date: string
  due_date: string
  payment_terms: string
  payment_terms_days: number
  discount_available: boolean
  discount_pct: number
  discount_deadline: string | null
  category: string
}

export interface SKU {
  sku_id: string
  name: string
  quantity_on_hand: number
  unit_cost: number
  lead_time_days: number
  avg_monthly_demand: number
  std_monthly_demand: number
  category: string
  annual_revenue: number
}

export interface ExpansionStep {
  step_number: number
  description: string
  domain: string
  data_required: string[]
  expected_output: string
}

export interface CompressionStep {
  insight: string
  recommendation: string
  expected_impact: string
  confidence: 'high' | 'medium' | 'low'
}

export interface GroundingCheck {
  data_points_referenced: number
  calculation_trace: string
  is_grounded: boolean
}

export interface ReasoningTrace {
  steps: string[]
  assumptions: string[]
  data_gaps: string[]
}

export interface TurnResult {
  agent_name: string
  capability: string
  expansion_steps: ExpansionStep[]
  compression_steps: CompressionStep[]
  grounding_check: GroundingCheck | null
  reasoning_trace: ReasoningTrace | null
  duration_ms: number
  trace_id: string
}

export interface Recommendation {
  agent: string
  capability: string
  insight: string
  recommendation: string
  expected_impact: string
  confidence: string
}

export interface CashConversionCycle {
  dso: number
  dio: number
  dpo: number
  ccc: number
}

export interface WeeklyForecast {
  week: number
  opening_balance: number
  inflows: number
  outflows: number
  net_change: number
  closing_balance: number
}

export interface AnalysisReport {
  problem: string
  duration_ms: number
  total_duration_ms: number
  status: string
  cash_conversion_cycle: CashConversionCycle
  turns: TurnResult[]
  recommendations: Recommendation[]
}

export interface EvalScore {
  dimension: string
  score: number
  justification: string
}

export interface EvalResult {
  id: string
  recommendation_id: string | null
  agent_name: string
  recommendation_text: string
  context_summary: string
  scores: EvalScore[]
  overall_score: number
  created_at: string
}

export interface AnalyzeRequest {
  ar_invoices: ARInvoice[]
  ap_invoices: APInvoice[]
  skus: SKU[]
  opening_cash_balance: number
  monthly_revenue: number
  monthly_cogs: number
  problem_description: string
  cost_of_capital: number
  carrying_cost_rate: number
  target_service_level: number
  min_cash_threshold: number
}

export interface HealthResponse {
  status: string
  version: string
  agents_ready: boolean
  database_connected: boolean
}
