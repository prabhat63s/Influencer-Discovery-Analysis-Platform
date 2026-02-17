
export type IndustryComparisonStatus = {
    status: "pending" | "processing" | "completed" | "skipped" | "failed";
    reason: string;
};

export type IndustryStandardsStatus = {
    conversation_id: string;
    status: "processing" | "completed" | "error" | "not_found";
    count: number;
    results: Array<Record<string, unknown>>;
    error?: string | null;
    industry_comparison?: IndustryComparisonStatus;
};

/**
 * Fetch industry standards analysis status and results
 */
export async function getIndustryStandards(
    conversationId: string
): Promise<IndustryStandardsStatus> {
    const base = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${base}/api/analysis/${encodeURIComponent(conversationId)}`;

    const res = await fetch(url, {
        method: "GET",
        headers: { accept: "application/json" },
    });

    if (!res.ok) {
        throw new Error(`Failed to fetch industry standards (${res.status})`);
    }

    return res.json();
}

export type IndustryComparisonInsights = {
    insights: string[];
    summary: string;
};

/**
 * Generate AI insights for industry standard comparison using Gemini
 */
export async function generateIndustryComparisonInsights(
    anchor: Record<string, unknown>,
    peers: Array<Record<string, unknown>>
): Promise<IndustryComparisonInsights> {
    const base = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${base}/api/industry-comparison/insights`;

    const res = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            accept: "application/json",
        },
        body: JSON.stringify({
            anchor,
            peers,
        }),
    });

    if (!res.ok) {
        throw new Error(`Failed to generate industry comparison insights (${res.status})`);
    }

    return res.json();
}

/**
 * Generate AI insights for internal comparison between top search results
 * (compares the results from the search query against each other, not against external industry peers)
 */
export async function generateInternalComparisonInsights(
    influencers: Array<Record<string, unknown>>
): Promise<IndustryComparisonInsights> {
    const base = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${base}/api/internal-comparison/insights`;

    const res = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            accept: "application/json",
        },
        body: JSON.stringify({
            influencers,
        }),
    });

    if (!res.ok) {
        throw new Error(`Failed to generate internal comparison insights (${res.status})`);
    }

    return res.json();
}
