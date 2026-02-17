import { apiRequest } from "./api";

/*
  Unified service function:

  mode = "normal" → /api/results  
  mode = "prompt" → /api/results/dynamic/prompt  
  BOTH handled inside one function.

  Includes:
  - conversationId support
  - automatic fallback for prompt mode (optional export)
*/

export async function getInfluencerResults(
    mode: "normal" | "prompt",
    influencerId: string,
    conversationId?: string
) {
    const base = process.env.NEXT_PUBLIC_API_URL || "";

    // ---------------------------
    // NORMAL MODE → /api/results
    // ---------------------------
    if (mode === "normal") {
        return apiRequest(`/api/results?influencer_id=${influencerId}`, {});
    }

    // --------------------------------------
    // PROMPT MODE → /api/results/dynamic/prompt
    // --------------------------------------
    const params = new URLSearchParams({ influencer_id: influencerId });
    if (conversationId) {
        params.set("conversation_id", conversationId);
    }
    const url =
        base && base.length > 0
            ? `${base}/api/results/dynamic/prompt?${params.toString()}`
            : `/api/results/dynamic/prompt?${params.toString()}`;

    const res = await fetch(url, {
        method: "GET",
        headers: { accept: "application/json" },
    });

    if (!res.ok) {
        throw new Error(`Failed to fetch prompt results (${res.status})`);
    }

    return res.json();
}

/* ------------------------------------------------------------
   OPTIONAL: helper wrapper with automatic fallback
-------------------------------------------------------------*/
export async function getInfluencerWithFallback(
    influencerId: string,
    conversationId?: string
) {
    try {
        // Try prompt mode first
        return await getInfluencerResults("prompt", influencerId, conversationId);
    } catch {
        console.warn("Prompt results unavailable → fallback to normal results");

        const normal = await getInfluencerResults("normal", influencerId);

        // /api/results returns { data: {...} }
        return normal.data;
    }
}
