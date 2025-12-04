import { NextResponse } from "next/server";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || "http://localhost:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const seriesId = searchParams.get("id");
  const startDate = searchParams.get("start");
  const endDate = searchParams.get("end");

  if (!seriesId) {
    return NextResponse.json({ error: "Series ID is required" }, { status: 400 });
  }

  try {
    const params = new URLSearchParams();
    if (startDate) params.set("start", startDate);
    if (endDate) params.set("end", endDate);
    const query = params.toString() ? `?${params.toString()}` : "";
    
    const response = await fetch(`${PYTHON_BACKEND_URL}/api/series/${seriesId}${query}`);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      return NextResponse.json(
        { error: error.detail || `Backend returned ${response.status}` },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching series data:", error);
    return NextResponse.json(
      { error: "Failed to connect to Python backend. Is it running?" },
      { status: 502 }
    );
  }
}








