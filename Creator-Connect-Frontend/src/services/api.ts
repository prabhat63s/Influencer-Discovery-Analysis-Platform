export async function apiRequest(url: string, options: RequestInit = {}) {
    const base = process.env.NEXT_PUBLIC_API_URL || "";

    const res = await fetch(base + url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const data = await res.json().catch(() => ({}));

    return {
        ok: res.ok,
        status: res.status,
        data
    };
}
