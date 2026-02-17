import { useState, useEffect } from "react";
import { CreatorProfile } from "@/types/creator.types";
import {
    searchCreators,
    normalizeSearchResults,
    saveSearchToLocalStorage,
    loadSearchFromLocalStorage,
    buildFollowersRange,
    type SearchResult,
} from "@/services/creatorSearch.service";

export const useCreatorSearch = () => {
    const [filterFollowers, setFilterFollowers] = useState([33]);
    const [engagementRate, setEngagementRate] = useState([25]);
    const [selectedCreator, setSelectedCreator] = useState<CreatorProfile | null>(null);
    const [promptText, setPromptText] = useState("");

    // Form state for Ask AI
    const [resultLimit, setResultLimit] = useState("50");
    const [niche, setNiche] = useState("Any");
    const [location, setLocation] = useState("");
    const [minFollowers, setMinFollowers] = useState("");
    const [maxFollowers, setMaxFollowers] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchResults, setSearchResults] = useState<CreatorProfile[]>([]);
    const [lastQuery, setLastQuery] = useState("Influencers");
    const [hasSearched, setHasSearched] = useState(false);
    const [conversationId, setConversationId] = useState<string | null>(null);

    // Load search results from localStorage on mount
    useEffect(() => {
        const savedSearch = loadSearchFromLocalStorage();
        if (savedSearch) {
            setSearchResults(savedSearch.results || []);
            setLastQuery(savedSearch.query || "Influencers");
            setHasSearched(savedSearch.results && savedSearch.results.length > 0);
        }
    }, []);

    // Auto-generate prompt based on form inputs
    useEffect(() => {
        const parts = [];

        parts.push(`Find me influencers`);

        if (niche && niche !== "Any") {
            parts.push(`in the ${niche} niche`);
        }

        if (location) {
            parts.push(`from ${location}`);
        }

        if (minFollowers || maxFollowers) {
            if (minFollowers && maxFollowers) {
                parts.push(`with followers between ${minFollowers} and ${maxFollowers}`);
            } else if (minFollowers) {
                parts.push(`with at least ${minFollowers} followers`);
            } else if (maxFollowers) {
                parts.push(`with up to ${maxFollowers} followers`);
            }
        }

        if (resultLimit && resultLimit !== "50") {
            parts.push(`(limit: ${resultLimit} results)`);
        }

        const generatedPrompt = parts.join(" ") + ".";
        setPromptText(generatedPrompt);
    }, [resultLimit, niche, location, minFollowers, maxFollowers]);

    // Handle Ask AI button click
    const handleAskAI = async () => {
        if (!promptText.trim()) {
            setError("Please enter a prompt");
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            // Call the search API
            const data = await searchCreators({
                query: promptText,
                filters: {
                    niche,
                    location,
                    minFollowers,
                    maxFollowers,
                },
            });

            console.log("API Response:", data);

            // Check if more details are required
            if (data?.complete === false) {
                setError(data?.message || data?.next_question || "More details are required.");
                return;
            }

            // Normalize results
            const rawResults = normalizeSearchResults(data);
            console.log("Normalized results:", rawResults);

            const queryText = String(data?.final_prompt || promptText || "Influencers");

            // Save to state
            setSearchResults(rawResults);
            setLastQuery(queryText);
            setHasSearched(true);

            // Capture conversation_id if available (so sidebar can fetch benchmarks/peers later)
            if (data?.conversation_id) {
                setConversationId(data.conversation_id);
            }

            // Save to localStorage
            const followersRange = buildFollowersRange(minFollowers, maxFollowers);
            const searchData: SearchResult = {
                results: rawResults,
                query: queryText,
                timestamp: new Date().toISOString(),
                filters: {
                    niche: niche !== "Any" ? niche : null,
                    location: location || null,
                    followersRange: followersRange || null,
                },
            };
            saveSearchToLocalStorage(searchData);

            if (rawResults.length === 0) {
                setError(data?.message || "No results found.");
            }
        } catch (err) {
            console.error("Error calling API:", err);
            setError(err instanceof Error ? err.message : "Failed to fetch results");
        } finally {
            setIsLoading(false);
        }
    };

    return {
        filterFollowers,
        setFilterFollowers,
        engagementRate,
        setEngagementRate,
        selectedCreator,
        setSelectedCreator,
        promptText,
        setPromptText,
        resultLimit,
        setResultLimit,
        niche,
        setNiche,
        location,
        setLocation,
        minFollowers,
        setMinFollowers,
        maxFollowers,
        setMaxFollowers,
        isLoading,
        error,
        searchResults,
        lastQuery,
        hasSearched,
        handleAskAI,
        conversationId
    };
};
