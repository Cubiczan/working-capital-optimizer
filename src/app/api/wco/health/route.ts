import { NextResponse } from 'next/server'

const BACKEND = process.env.WCO_BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/health`, { signal: AbortSignal.timeout(3000) })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ status: 'unreachable', version: '0.1.0', agents_ready: false, database_connected: false })
  }
}
