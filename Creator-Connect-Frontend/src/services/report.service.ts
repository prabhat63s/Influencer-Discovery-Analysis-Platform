interface ReportParams {
    influencerId: string;
    conversationId: string | null;
    fileHash?: string;
}

export async function generateUnifiedReport(options: ReportParams) {
    const { influencerId, fileHash, conversationId } = options;

    const endpoint = `/api/report/generate/dynamic`;

    const payload: Record<string, unknown> = {
        influencer_id: influencerId,
        ...(fileHash ? { file_hash: fileHash } : {}),
        ...(conversationId ? { conversation_id: conversationId } : {}),
    };

    const base = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${base}${endpoint}`;

    console.debug("generateUnifiedReport -> endpoint:", url);
    console.debug("generateUnifiedReport -> payload:", payload);

    try {
        const headers: Record<string, string> = {
            "Content-Type": "application/json",
        };

        // Use localStorage for auth token
        const authToken = localStorage.getItem('authToken') || "valid_token";
        if (authToken) {
            headers.Authorization = `Bearer ${authToken}`;
        }

        const resp = await fetch(url, {
            method: "POST",
            headers,
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            const clone = resp.clone();
            let text = "";
            try {
                const errJson = await clone.json();
                text = JSON.stringify(errJson);
            } catch {
                try {
                    text = await clone.text();
                } catch {
                    text = "";
                }
            }
            throw new Error(`Report generation failed (${resp.status}): ${text}`);
        }

        const contentType = resp.headers.get("content-type") || "";

        if (contentType.includes("application/pdf") || resp.headers.get("content-disposition")) {
            const blob = await resp.blob();
            const cd = resp.headers.get("content-disposition") || "";
            const filenameMatch = cd.match(/filename\*?=(?:UTF-8'')?["']?([^;"']+)["']?/i);
            const filename = filenameMatch ? decodeURIComponent(filenameMatch[1]) : `report_${Date.now()}.pdf`;

            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(blobUrl);

            return { ok: true, filename, size: blob.size };
        }

        const data = await resp.json();
        console.debug("generateUnifiedReport -> json response:", data);

        const maybeUrl = (data && (data.download_url as string | undefined)) || undefined;

        if (maybeUrl) {
            let downloadUrl: string;
            if (maybeUrl.startsWith("http://") || maybeUrl.startsWith("https://")) {
                downloadUrl = maybeUrl;
            } else if (maybeUrl.startsWith("/")) {
                downloadUrl = `${base}${maybeUrl}`;
            } else {
                downloadUrl = `${base}/${maybeUrl}`;
            }

            console.debug("generateUnifiedReport -> downloading from:", downloadUrl);

            const downloadHeaders: Record<string, string> = {};
            const authToken = localStorage.getItem('authToken') || "valid_token";
            if (authToken) {
                downloadHeaders.Authorization = `Bearer ${authToken}`;
            }

            const downloadResp = await fetch(downloadUrl, {
                method: "GET",
                headers: downloadHeaders,
            });

            if (!downloadResp.ok) {
                const text = await downloadResp.text().catch(() => "");
                throw new Error(`Download failed (${downloadResp.status}): ${text || "no body"}`);
            }

            const blob = await downloadResp.blob();
            const cd = downloadResp.headers.get("content-disposition") || "";
            const filenameMatch = cd.match(/filename\*?=(?:UTF-8'')?["']?([^;"']+)["']?/i);
            const filename = filenameMatch && filenameMatch[1]
                ? decodeURIComponent(filenameMatch[1])
                : data.report_name || `report_${Date.now()}.pdf`;

            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(blobUrl);

            return { ok: true, filename, size: blob.size };
        }

        return data;
    } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err ?? "Unknown error"));
        console.error("generateUnifiedReport -> request failed", {
            endpoint: url,
            payload,
            error: error.message,
        });
        throw error;
    }
}
