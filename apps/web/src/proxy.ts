import { NextRequest, NextResponse } from "next/server";
export function proxy(request: NextRequest) {
  const host = request.headers.get("host");
  const origin = request.headers.get("origin");
  // Next may add its own X-Forwarded-* headers internally; never use them to
  // replace the actual Host. Reject contradictory forwarded authority.
  if (
    host !== "127.0.0.1:3000" ||
    (origin !== null && origin !== "http://127.0.0.1:3000") ||
    request.headers.has("forwarded") ||
    (request.headers.has("x-forwarded-host") &&
      request.headers.get("x-forwarded-host") !== host) ||
    (request.headers.has("x-forwarded-port") &&
      request.headers.get("x-forwarded-port") !== "3000")
  ) {
    return new NextResponse("Invalid local frontend authority.", {
      status: 400,
    });
  }
  return NextResponse.next();
}
