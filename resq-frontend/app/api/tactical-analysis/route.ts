/**
 * Proxy for POST /api/tactical-analysis with a long timeout.
 * Tactical analysis (VLM + Overpass) can take 60–120+ seconds; the default
 * Next.js rewrite proxy can close the connection. This route forwards to
 * the backend with a 5-minute timeout.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000/api/v1/tactical-analysis";
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export async function POST(request: NextRequest) {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return NextResponse.json(
      { detail: "Invalid request body" },
      { status: 400 }
    );
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    const data = await res.text();
    const contentType = res.headers.get("content-type") ?? "application/json";

    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": contentType },
    });
  } catch (err) {
    clearTimeout(timeoutId);
    const message = err instanceof Error ? err.message : "Proxy request failed";
    const isTimeout = message.includes("abort") || message.includes("timeout");
    return NextResponse.json(
      {
        detail: isTimeout
          ? "Tactical analysis timed out. The backend may still be processing; try again in a minute."
          : message,
      },
      { status: 504 }
    );
  }
}