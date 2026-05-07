import { NextResponse } from 'next/server'

const BACKEND = process.env.WCO_BACKEND_URL || 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/evaluations?limit=50`)
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ evaluations: [] }, { status: 502 })
  }
}
