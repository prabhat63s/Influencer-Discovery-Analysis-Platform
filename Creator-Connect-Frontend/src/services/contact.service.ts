
interface DemoRequestData {
    name: string;
    email: string;
}

export const requestDemo = async (data: DemoRequestData) => {
    // Use the relative path to hit the Next.js API route directly
    const endpoint = `/api/contact/demo`;

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `Request failed with status ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error("Error requesting demo:", error);
        throw error;
    }
};
